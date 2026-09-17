"""Allgemeine Metriken (beide Specs) aus FightData."""

from __future__ import annotations

import statistics
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from .. import spells
from .casts import (
    Cancelled,
    Cast,
    GapStats,
    ReactionStats,
    active_time_s,
    casts_per_window,
    count_by_ability,
    find_gaps,
    parse_casts,
    player_casts,
    reaction_times,
)
from .loader import FightData
from .rows import MetricRow
from .spec import SpecInfo, detect_spec

TRINKET_SLOTS = (12, 13)
# Brust, Beine, Füße, Handgelenk, Ringe, Rücken, Waffe
ENCHANTABLE_SLOTS = (4, 6, 7, 8, 10, 11, 14, 15)


@dataclass
class GearSnapshot:
    ilvl: float | None = None
    intellect: int | None = None
    crit: int | None = None
    haste: int | None = None
    mastery: int | None = None
    versatility: int | None = None
    trinkets: list[tuple[int, int]] = field(default_factory=list)  # (item id, ilvl)
    enchants: int = 0
    set_pieces: int = 0
    talents: list[int] = field(default_factory=list)  # Talent-IDs (für Diff-Anzeige)


@dataclass
class GeneralMetrics:
    spec: SpecInfo
    duration_s: float
    total_damage: int
    dps: float
    parse_percent: float | None
    ilvl: float | None
    casts_total: int
    casts_per_30s: list[int]
    casts_by_ability: Counter[int]
    gaps: GapStats
    cancelled: list[Cancelled]
    reaction: ReactionStats
    potions_s: list[float]
    deaths: int
    active_time_s: float
    gear: GearSnapshot
    casts: list[Cast]  # Spieler-Casts (gefiltert), Basis für Spec-Metriken
    all_casts: list[Cast]  # inkl. Utility

    @property
    def active_pct(self) -> float:
        return 100.0 * self.active_time_s / self.duration_s if self.duration_s else 0.0

    @property
    def cancelled_by_ability(self) -> Counter[int]:
        return Counter(c.ability for c in self.cancelled)

    def rows(self) -> list[MetricRow]:
        """Kernmetriken (beide Specs) im gemeinsamen Zeilenformat."""
        r = self.reaction
        # Letztes Fenster ist kürzer und verzerrt den Median
        windows = sorted(self.casts_per_30s[:-1] or self.casts_per_30s)
        return [
            MetricRow("general.dps", "DPS", self.dps, "", "higher", damage=self.total_damage),
            MetricRow("general.damage", "Gesamtschaden", self.total_damage, "m", "higher",
                      damage=self.total_damage),
            MetricRow("general.casts", "Spieler-Casts", self.casts_total, "", "higher"),
            MetricRow("general.casts_30s_median", "Casts / 30 s (Median)",
                      statistics.median(windows) if windows else None, "", "higher"),
            MetricRow("general.gaps_count", "Lücken > 2,5 s", self.gaps.count, "", "lower"),
            MetricRow("general.gaps_total", "Lücken gesamt", self.gaps.total_s, "s", "lower"),
            MetricRow("general.cancelled", "Abgebrochene Casts", len(self.cancelled), "", "lower"),
            MetricRow("general.reaction_median", "Reaktion nach Instant (Median)",
                      r.median_s, "s", "lower"),
            MetricRow("general.reaction_p90", "Reaktion nach Instant (P90)", r.p90_s, "s", "lower"),
            MetricRow("general.gcd", "GCD (geschätzt)", r.gcd_estimate_s, "s", "neutral",
                      compare=False),
            MetricRow("general.active_pct", "Aktivzeit", self.active_pct, "%", "higher"),
            MetricRow("general.potions", "Kampftränke", len(self.potions_s), "", "higher",
                      detail=", ".join(f"{s:.0f} s" for s in self.potions_s)),
            MetricRow("general.deaths", "Tode", self.deaths, "", "lower"),
            MetricRow("general.parse", "Parse", self.parse_percent, "%", "neutral", compare=False),
            MetricRow("general.ilvl", "Ilvl", self.ilvl, "", "neutral", compare=False),
        ]

    def gear_rows(self) -> list[MetricRow]:
        g = self.gear
        return [
            MetricRow("gear.ilvl", "Ilvl", g.ilvl, "", "neutral", compare=False),
            MetricRow("gear.int", "Int", g.intellect, "", "neutral", compare=False),
            MetricRow("gear.crit", "Crit", g.crit, "", "neutral", compare=False),
            MetricRow("gear.haste", "Haste", g.haste, "", "neutral", compare=False),
            MetricRow("gear.mastery", "Mastery", g.mastery, "", "neutral", compare=False),
            MetricRow("gear.vers", "Vers", g.versatility, "", "neutral", compare=False),
            MetricRow("gear.set", "Set-Teile", g.set_pieces, "", "neutral", compare=False),
            MetricRow("gear.enchants", "Enchants", g.enchants, "", "neutral", compare=False),
            MetricRow("gear.trinkets", "Trinkets", None, "", "neutral", compare=False,
                      detail=", ".join(f"{i} ({lvl})" for i, lvl in g.trinkets) or "–"),
        ]


def _stat(ci: dict[str, Any], key: str) -> int | None:
    """Summary.combatantInfo.stats = {"Intellect": {"min": x, "max": y}, ...}."""
    entry = (ci.get("stats") or {}).get(key)
    if not entry:
        return None
    return entry.get("max", entry.get("min"))


def gear_snapshot(data: FightData) -> GearSnapshot:
    ci = data.combatant_info
    gear = ci.get("gear") or []
    by_slot = {g.get("slot", i): g for i, g in enumerate(gear)}
    snap = GearSnapshot(
        ilvl=_stat(ci, "Item Level") or _ilvl_from_casts(data.cast_events),
        intellect=_stat(ci, "Intellect"),
        crit=_stat(ci, "Crit"),
        haste=_stat(ci, "Haste"),
        mastery=_stat(ci, "Mastery"),
        versatility=_stat(ci, "Versatility"),
    )
    for slot in TRINKET_SLOTS:
        item = by_slot.get(slot)
        if item and item.get("id"):
            snap.trinkets.append((item["id"], item.get("itemLevel", 0)))
    snap.enchants = sum(
        1 for slot in ENCHANTABLE_SLOTS if by_slot.get(slot, {}).get("permanentEnchant")
    )
    set_ids = Counter(g.get("setID") for g in gear if g.get("setID"))
    snap.set_pieces = max(set_ids.values()) if set_ids else 0
    talents = ci.get("talentTree") or ci.get("talents") or []
    snap.talents = sorted(t.get("id") for t in talents if t.get("id"))
    return snap


def _ilvl_from_casts(events: list[dict[str, Any]]) -> float | None:
    for ev in events:
        if ev.get("itemLevel"):
            return float(ev["itemLevel"])
    return None


def potion_times(data: FightData) -> list[float]:
    start = data.fight.startTime
    return [
        (ev["timestamp"] - start) / 1000.0
        for ev in data.buff_events
        if ev.get("type") == "applybuff" and ev.get("abilityGameID") in spells.COMBAT_POTION_BUFFS
    ]


def compute_general(data: FightData) -> GeneralMetrics:
    fight = data.fight
    all_casts, cancelled = parse_casts(data.cast_events, data.actor.id)
    casts = player_casts(all_casts, data.ability_names)
    spec = detect_spec(c.ability for c in casts)
    duration_s = fight.duration_s
    total_damage = data.total_damage
    reaction = reaction_times(casts)
    gear = gear_snapshot(data)
    return GeneralMetrics(
        spec=spec,
        duration_s=duration_s,
        total_damage=total_damage,
        dps=total_damage / duration_s if duration_s else 0.0,
        parse_percent=data.parse_percent,
        ilvl=gear.ilvl,
        casts_total=len(casts),
        casts_per_30s=casts_per_window(casts, fight.startTime, fight.endTime),
        casts_by_ability=count_by_ability(casts),
        gaps=find_gaps(casts, fight.startTime),
        cancelled=[c for c in cancelled if c.ability not in spells.EXCLUDED_FROM_PLAYER_CASTS],
        reaction=reaction,
        potions_s=potion_times(data),
        deaths=len(data.deaths),
        active_time_s=active_time_s(casts, duration_s, reaction.gcd_estimate_s),
        gear=gear,
        casts=casts,
        all_casts=all_casts,
    )
