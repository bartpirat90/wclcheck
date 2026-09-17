"""Spec-Metriken für Demonology (Diabolist).

Die Rotationsregeln und alle Sollwerte stehen in `rules_demo.py`; hier wird nur
gemessen. Näherungen sind im Docstring der jeweiligen Funktion und im Label der
Ausgabezeile gekennzeichnet:

- **Aktive Wild Imps / Dreadstalker**: Despawn-Events gibt es in der WCL-API nicht.
  Ein Pet gilt vom Summon-Event bis zu seinem letzten Schadensereignis plus einer
  Karenz (`rules_demo.IMP_BOLT_GRACE_MS`) als aktiv.
- **Ziele pro Cast**: Casts von Pets liefert die API nicht. Für Fel Firebolt steht in
  der DamageDone-Tabelle ein `uses`-Feld (= Casts), das exakt benutzt wird; für Mind
  Sear und Burning Cleave werden Treffer desselben Pets innerhalb von
  `rules_demo.MULTI_TARGET_CLUSTER_MS` zu einem Cast zusammengefasst.
- **Shards zum Zeitpunkt der Implosion**: Implosion kostet nichts und trägt daher
  keine `classResources`. Der Shard-Stand wird aus den Ankern der kostenpflichtigen
  Casts plus den `resourcechange`-Events fortgeschrieben.
- **Core-Overcap**: `refreshbuff` auf Demonic Core, während die Stacks bereits auf
  dem Maximum stehen.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from .. import spells
from . import rules_demo as rules
from .casts import Cast
from .loader import FightData
from .metrics import GeneralMetrics
from .rows import MetricRow

log = logging.getLogger("wclcheck.demo")

SOUL_SHARD_RESOURCE_TYPE = 7
MAX_SHARDS = 5.0

Span = tuple[int, int]


# --------------------------------------------------------------------------- Hilfen


def _table_entry(
    damage_table: Sequence[dict[str, Any]], guid: int, *, sub_only: bool = False
) -> dict[str, Any] | None:
    """Posten aus der DamageDone-Tabelle.

    `sub_only=True` sucht ausschließlich in den `subentries`. Das ist nötig, wenn ein
    Sammelposten mehrere Fähigkeiten bündelt (Shadow Bolt 686 enthält Infernal Bolt,
    Hand of Gul'dan 105174 enthält Ruination).
    """
    if not sub_only:
        for e in damage_table:
            if e.get("guid") == guid:
                return e
    for e in damage_table:
        for s in e.get("subentries") or []:
            if s.get("guid") == guid:
                return s
    return None


def table_damage(
    damage_table: Sequence[dict[str, Any]], *guids: int, sub_only: bool = False
) -> int:
    total = 0
    for guid in guids:
        entry = _table_entry(damage_table, guid, sub_only=sub_only)
        if entry is None:
            continue
        total += int(entry.get("total") or 0)
    return total


def table_uses_hits(
    damage_table: Sequence[dict[str, Any]], guid: int, *, sub_only: bool = False
) -> tuple[int | None, int]:
    """(`uses`, `hitCount`) eines Postens. `uses` = Casts, fehlt bei manchen Pets."""
    entry = _table_entry(damage_table, guid, sub_only=sub_only)
    if entry is None:
        return None, 0
    uses = entry.get("uses")
    return (None if uses is None else int(uses)), int(entry.get("hitCount") or 0)


@dataclass
class CoreTrack:
    """Verlauf der Demonic-Core-Stacks plus Overcap-Zähler."""

    timeline: list[tuple[int, int]] = field(default_factory=list)  # (ts, Stacks danach)
    max_seen: int = 0
    overcap: int = 0

    def stacks_before(self, ts: int) -> int:
        """Stacks unmittelbar VOR dem Zeitpunkt (Events auf derselben ms zählen nicht)."""
        stacks = 0
        for t, value in self.timeline:
            if t >= ts:
                break
            stacks = value
        return stacks

    def stacks_at_end(self, ts: int) -> int:
        stacks = 0
        for t, value in self.timeline:
            if t > ts:
                break
            stacks = value
        return stacks


def track_core(
    buff_events: Iterable[dict[str, Any]],
    buff_id: int = spells.DEMONIC_CORE_BUFF,
    max_stacks: int = rules.DEMONIC_CORE_MAX_STACKS,
) -> CoreTrack:
    """Stack-Verlauf eines Spieler-Buffs aus apply/applystack/removestack/remove.

    `refreshbuff` auf bereits maximalen Stacks gilt als Overcap (Näherung: der Proc
    wird verworfen, weil die Stacks nicht weiter steigen können).
    """
    track = CoreTrack()
    stacks = 0
    for ev in buff_events:
        if ev.get("abilityGameID") != buff_id:
            continue
        kind = ev.get("type")
        if kind == "refreshbuff":
            if stacks >= max_stacks:
                track.overcap += 1
            continue
        if kind == "applybuff":
            stacks = max(stacks, 1)
        elif kind == "applybuffstack":
            stacks = int(ev.get("stack") or stacks + 1)
        elif kind == "removebuffstack":
            stacks = int(ev.get("stack") or max(0, stacks - 1))
        elif kind == "removebuff":
            stacks = 0
        else:
            continue
        track.max_seen = max(track.max_seen, stacks)
        track.timeline.append((ev["timestamp"], stacks))
    return track


def buff_windows(
    buff_events: Iterable[dict[str, Any]], buff_id: int, fight_end: int
) -> list[Span]:
    """Fenster (applybuff -> removebuff) eines Spieler-Buffs; offene enden am Fightende."""
    windows: list[Span] = []
    start: int | None = None
    for ev in buff_events:
        if ev.get("abilityGameID") != buff_id:
            continue
        kind = ev.get("type")
        if kind == "applybuff" and start is None:
            start = ev["timestamp"]
        elif kind == "removebuff" and start is not None:
            windows.append((start, ev["timestamp"]))
            start = None
    if start is not None:
        windows.append((start, fight_end))
    return windows


def shard_timeline(
    cast_events: Iterable[dict[str, Any]],
    resource_events: Iterable[dict[str, Any]],
    actor_id: int,
) -> list[tuple[int, float]]:
    """Shard-Stand über die Zeit: (Zeitstempel, Shards nach dem Ereignis).

    Kostenpflichtige Casts tragen `classResources` mit dem Stand VOR dem Cast und
    liefern damit harte Anker; dazwischen wird mit den `resourcechange`-Events
    fortgeschrieben. `resourceChange` ist dort in ganzen Shards angegeben,
    `classResources.amount` dagegen in Zehnteln.
    """
    steps: list[tuple[int, int, float, float]] = []  # (ts, sort, a, b)
    for ev in cast_events:
        if ev.get("sourceID") != actor_id or ev.get("type") != "cast":
            continue
        for res in ev.get("classResources") or []:
            if res.get("type") != SOUL_SHARD_RESOURCE_TYPE:
                continue
            amount = res.get("amount")
            if amount is None:
                continue
            steps.append((ev["timestamp"], 1, amount / 10.0, (res.get("cost") or 0) / 10.0))
    for ev in resource_events:
        if ev.get("resourceChangeType") != SOUL_SHARD_RESOURCE_TYPE:
            continue
        steps.append((ev["timestamp"], 0, float(ev.get("resourceChange") or 0), 0.0))
    steps.sort(key=lambda s: (s[0], s[1]))

    out: list[tuple[int, float]] = []
    current = 0.0
    for ts, sort, a, b in steps:
        if sort == 0:  # resourcechange
            current = min(MAX_SHARDS, current + a)
        else:  # Cast mit Anker
            current = max(0.0, a - b)
        out.append((ts, current))
    return out


def shards_before(timeline: Sequence[tuple[int, float]], ts: int) -> float | None:
    """Shard-Stand unmittelbar vor einem Zeitpunkt."""
    if not timeline:
        return None
    value: float | None = None
    for t, v in timeline:
        if t >= ts:
            break
        value = v
    return value


def pet_spans(
    summon_events: Iterable[dict[str, Any]],
    damage_events: Iterable[dict[str, Any]] | None,
    summon_abilities: Iterable[int],
    *,
    damage_ability: int | None = None,
    grace_ms: int = rules.IMP_BOLT_GRACE_MS,
    max_lifetime_ms: int = rules.IMP_MAX_LIFETIME_MS,
) -> list[Span]:
    """Näherung der Lebensdauer beschworener Pets: Summon bis letzter Treffer + Karenz.

    Despawn-Events liefert die API nicht. Ein Pet wird über (targetID, targetInstance)
    des Summon-Events mit (sourceID, sourceInstance) seiner Schadensereignisse verknüpft.
    """
    wanted = set(summon_abilities)
    last_hit: dict[tuple[int, int], int] = {}
    for ev in damage_events or []:
        if damage_ability is not None and ev.get("abilityGameID") != damage_ability:
            continue
        key = (ev.get("sourceID"), ev.get("sourceInstance", 1))
        ts = ev["timestamp"]
        if ts > last_hit.get(key, 0):
            last_hit[key] = ts
    spans: list[Span] = []
    for ev in summon_events:
        if ev.get("abilityGameID") not in wanted:
            continue
        start = ev["timestamp"]
        end = last_hit.get((ev.get("targetID"), ev.get("targetInstance", 1)))
        end = start if end is None else end
        spans.append((start, min(end + grace_ms, start + max_lifetime_ms)))
    spans.sort()
    return spans


def active_at(spans: Iterable[Span], ts: int) -> int:
    return sum(1 for a, b in spans if a <= ts <= b)


def mean_active(spans: Sequence[Span], start: int, end: int) -> float:
    """Mittlere Anzahl aktiver Pets über ein Fenster (Abtastung alle 0,5 s)."""
    step = rules.ACTIVE_SAMPLE_MS
    n = max(1, (end - start) // step)
    return sum(active_at(spans, start + i * step) for i in range(n)) / n


def drifts(times_ms: Sequence[int], cooldown_s: float) -> list[float]:
    """Verlorene Sekunden je Cast-Paar: Abstand minus Cooldown, unterhalb der
    Toleranz auf 0 gesetzt."""
    out: list[float] = []
    for a, b in zip(times_ms, times_ms[1:], strict=False):
        lost = (b - a) / 1000.0 - cooldown_s
        out.append(lost if lost > rules.DRIFT_TOLERANCE_S else 0.0)
    return out


def targets_per_cast(
    damage_events: Iterable[dict[str, Any]] | None,
    ability_id: int,
    cluster_ms: int = rules.MULTI_TARGET_CLUSTER_MS,
) -> tuple[int, int]:
    """(Treffer, geschätzte Casts) – Näherung über Treffer-Cluster je Pet-Instanz."""
    evs = sorted(
        (e for e in damage_events or [] if e.get("abilityGameID") == ability_id),
        key=lambda e: e["timestamp"],
    )
    casts = 0
    last: dict[tuple[int, int], int] = {}
    for ev in evs:
        key = (ev.get("sourceID"), ev.get("sourceInstance", 1))
        ts = ev["timestamp"]
        if key not in last or ts - last[key] > cluster_ms:
            casts += 1
        last[key] = ts
    return len(evs), casts


def _ratio(a: float | int | None, b: float | int | None) -> float | None:
    if a is None or not b:
        return None
    return a / b


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


# --------------------------------------------------------------------------- Metriken


@dataclass
class TyrantWindow:
    """Ein Tyrant-Cast mit seinem 15-s-Fenster und dem zugehörigen Argus-Portal."""

    at_s: float
    drift_s: float  # verlorene Sekunden zum vorherigen Cast (0 beim ersten)
    hog_casts: int
    implosions: int
    # None, wenn `FightData.damage_events` nicht geladen wurde (Pet-Lebensdauer unbekannt)
    demons_at_cast: int | None
    demons_mean: float | None
    portal_hog: int
    portal_ruination: int  # Ruination ist eine verstärkte HoG und zählt fürs Portal mit
    portal_demons: int
    portal_len_s: float | None


@dataclass
class DemoMetrics:
    """Alle Demonology-Metriken eines Fights. Werte, die Damage-Events brauchen,
    sind None, wenn `FightData.damage_events` nicht geladen wurde."""

    duration_s: float
    # Opener
    first_tyrant_s: float | None
    opener: list[tuple[float, int]]  # (Sekunde, Spell-ID) der ersten 10 Casts
    # Tyrant
    tyrant_casts: int
    tyrant_expected: int
    tyrant_times_s: list[float]
    tyrant_drift_s: float
    tyrant_damage: int
    tyrant_hits: int
    windows: list[TyrantWindow]
    # Dominion of Argus
    dominion_damage: int
    dominion_demons: int
    dominion_portals: int
    # Hand of Gul'dan
    hog_casts: int
    hog_low_shard: int
    hog_shards_mean: float | None
    hog_imps: int
    hog_damage: int
    firebolts_hog: int | None
    firebolt_hits_hog: int
    firebolts_inner: int | None
    firebolt_hits_inner: int
    inner_demon_imps: int
    # Demonbolt / Cores
    demonbolt_casts: int
    demonbolt_hardcasts: int
    demonbolt_damage: int
    core_stacks_mean: float | None
    core_overcap: int
    core_max_seen: int
    cores_at_end: int
    # Implosion
    implosion_casts: int
    imps_per_implosion: float | None
    implosion_low_imp: int
    implosion_shards_mean: float | None
    implosion_low_shard: int
    implosions_in_tyrant: int
    implosion_damage: int
    isolated_implosion_damage: int
    # Cooldowns
    dreadstalker_casts: int
    dreadstalker_expected: int
    dreadstalker_drift_s: float
    dreadstalker_damage: int
    grimoire_casts: int
    grimoire_expected: int
    grimoire_drift_s: float
    grimoire_damage: int
    # Diabolist
    ruination_casts: int
    ruination_expected: int
    ruination_damage: int
    infernal_bolt_casts: int
    infernal_bolt_expected: int
    infernal_bolt_damage: int
    ritual_procs: int
    ritual_damage: int
    # Filler / Multi-Target
    shadow_bolt_casts: int
    shadow_bolt_damage: int
    filler_pct: float
    targets_inner_demons: float | None
    targets_mind_sear: float | None
    targets_burning_cleave: float | None
    # Ressourcen
    shard_waste: int

    def rows(self) -> list[MetricRow]:
        w = self.windows
        opener = " → ".join(spells.name(a) for _, a in self.opener)
        return [
            # -------------------------------------------------------------- Opener
            MetricRow(
                "demo.opener.first_tyrant", "Erster Tyrant", self.first_tyrant_s, "s", "lower"
            ),
            MetricRow(
                "demo.opener.sequence", "Opener (erste 10 Casts)", None, "", "neutral",
                detail=opener, compare=False,
            ),
            # -------------------------------------------------------------- Tyrant
            MetricRow(
                "demo.tyrant.casts", "Tyrant-Casts", self.tyrant_casts, "", "higher",
                damage=self.tyrant_damage,
                detail="Soll {} · {}".format(
                    self.tyrant_expected,
                    " / ".join(f"{t:.0f} s" for t in self.tyrant_times_s) or "–",
                ),
            ),
            MetricRow(
                "demo.tyrant.drift", "Tyrant-Drift zum CD", self.tyrant_drift_s, "s", "lower"
            ),
            MetricRow(
                "demo.tyrant.damage", "Tyrant-Schaden", self.tyrant_damage, "m", "higher",
                damage=self.tyrant_damage,
            ),
            MetricRow(
                "demo.tyrant.hits_per_cast", "Tyrant-Treffer pro Cast",
                _ratio(self.tyrant_hits, self.tyrant_casts), "x", "higher",
            ),
            MetricRow(
                "demo.tyrant.demons", "Dämonen im Tyrant-Fenster (Näherung)",
                _mean([x.demons_mean for x in w if x.demons_mean is not None]), "x", "higher",
                detail=" / ".join(
                    "–" if x.demons_at_cast is None else str(x.demons_at_cast) for x in w
                ),
            ),
            MetricRow(
                "demo.tyrant.hog", "HoG im Tyrant-Fenster",
                _mean([float(x.hog_casts) for x in w]), "x", "higher",
                detail=" / ".join(str(x.hog_casts) for x in w),
            ),
            # ---------------------------------------------------- Dominion of Argus
            MetricRow(
                "demo.dominion.damage", "Dominion of Argus – Schaden",
                self.dominion_damage, "m", "higher", damage=self.dominion_damage,
            ),
            MetricRow(
                "demo.dominion.demons", "Argus-Dämonen gesamt", self.dominion_demons, "",
                "higher", damage=self.dominion_damage,
                detail=" / ".join(str(x.portal_demons) for x in w),
            ),
            MetricRow(
                "demo.dominion.demons_per_tyrant", "Argus-Dämonen pro Tyrant",
                _ratio(self.dominion_demons, self.dominion_portals), "x", "higher",
            ),
            MetricRow(
                "demo.dominion.hog_per_portal", "HoG pro Portalfenster",
                _mean([float(x.portal_hog) for x in w]), "x", "higher",
                detail=" / ".join(str(x.portal_hog) for x in w),
            ),
            # -------------------------------------------------------- Hand of Gul'dan
            MetricRow(
                "demo.hog.casts", "Hand of Gul'dan", self.hog_casts, "", "higher",
                damage=self.hog_damage,
            ),
            MetricRow(
                "demo.hog.low_shard", "HoG unter 3 Shards", self.hog_low_shard, "", "lower"
            ),
            MetricRow(
                "demo.hog.shards", "Shards beim HoG-Cast", self.hog_shards_mean, "x", "neutral"
            ),
            MetricRow(
                "demo.hog.imps_per_cast", "Imps pro HoG",
                _ratio(self.hog_imps, self.hog_casts), "x", "higher",
            ),
            MetricRow(
                "demo.hog.firebolts", "Wild-Imp-Feuerblitze HoG", self.firebolts_hog, "",
                "higher", detail=f"{self.firebolt_hits_hog} Treffer",
            ),
            MetricRow(
                "demo.inner.firebolts", "Wild-Imp-Feuerblitze Inner Demons",
                self.firebolts_inner, "", "higher",
                detail=f"{self.firebolt_hits_inner} Treffer / {self.inner_demon_imps} Imps",
            ),
            # ----------------------------------------------------------- Demonbolt
            MetricRow(
                "demo.demonbolt.casts", "Demonbolt", self.demonbolt_casts, "", "higher",
                damage=self.demonbolt_damage,
            ),
            MetricRow(
                "demo.demonbolt.hardcast_pct", "Demonbolt-Hardcasts",
                100.0 * self.demonbolt_hardcasts / self.demonbolt_casts
                if self.demonbolt_casts else None,
                "%", "lower", detail=f"{self.demonbolt_hardcasts} Casts",
            ),
            MetricRow(
                "demo.demonbolt.cores", "Cores beim Demonbolt", self.core_stacks_mean, "x",
                "neutral",
            ),
            MetricRow(
                "demo.core.overcap", "Demonic-Core-Overcap (Näherung)", self.core_overcap, "",
                "lower", detail=f"Maximum {self.core_max_seen} Stacks",
            ),
            MetricRow("demo.core.at_end", "Cores am Kampfende", self.cores_at_end, "", "lower"),
            # ----------------------------------------------------------- Implosion
            MetricRow(
                "demo.implosion.casts", "Implosion", self.implosion_casts, "", "higher",
                damage=self.implosion_damage + self.isolated_implosion_damage,
            ),
            MetricRow(
                "demo.implosion.imps", "Imps pro Implosion (Näherung)",
                self.imps_per_implosion, "x", "higher",
                detail=f"{self.implosion_low_imp} unter {rules.IMPLOSION_MIN_IMPS}",
            ),
            MetricRow(
                "demo.implosion.shards", "Shards bei Implosion", self.implosion_shards_mean,
                "x", "higher", detail=f"{self.implosion_low_shard} unter 3",
            ),
            MetricRow(
                "demo.implosion.in_tyrant", "Implosionen im Tyrant-Fenster",
                self.implosions_in_tyrant, "", "neutral",
            ),
            MetricRow(
                "demo.implosion.damage", "Implosion + Isolated – Schaden",
                self.implosion_damage + self.isolated_implosion_damage, "m", "higher",
                damage=self.implosion_damage + self.isolated_implosion_damage,
                detail=f"davon Isolated {self.isolated_implosion_damage / 1e6:.2f}m",
            ),
            # ----------------------------------------------------------- Cooldowns
            MetricRow(
                "demo.dreadstalkers.casts", "Call Dreadstalkers", self.dreadstalker_casts, "",
                "higher", damage=self.dreadstalker_damage,
                detail=f"Soll {self.dreadstalker_expected}",
            ),
            MetricRow(
                "demo.dreadstalkers.drift", "Dreadstalker-Drift zum CD",
                self.dreadstalker_drift_s, "s", "lower",
            ),
            MetricRow(
                "demo.grimoire.casts", "Grimoire: Imp Lord", self.grimoire_casts, "", "higher",
                damage=self.grimoire_damage, detail=f"Soll {self.grimoire_expected}",
            ),
            MetricRow(
                "demo.grimoire.drift", "Grimoire-Drift zum CD", self.grimoire_drift_s, "s",
                "lower",
            ),
            # ----------------------------------------------------------- Diabolist
            MetricRow(
                "demo.ruination.casts", "Ruination", self.ruination_casts, "", "higher",
                damage=self.ruination_damage,
                detail=f"Soll {self.ruination_expected} ({rules.RUINATION_SOURCE})",
            ),
            MetricRow(
                "demo.infernal_bolt.casts", "Infernal Bolt", self.infernal_bolt_casts, "",
                "higher", damage=self.infernal_bolt_damage,
                detail=f"Soll {self.infernal_bolt_expected} ({rules.INFERNAL_BOLT_SOURCE})",
            ),
            MetricRow(
                "demo.ritual.procs", "Diabolic-Ritual-Procs", self.ritual_procs, "", "higher",
                damage=self.ritual_damage,
            ),
            MetricRow(
                "demo.ritual.damage_per_proc", "Diabolic Ritual – Schaden pro Proc",
                _ratio(self.ritual_damage, self.ritual_procs), "k", "higher",
                damage=self.ritual_damage,
                detail=f"gesamt {self.ritual_damage / 1e6:.2f}m",
            ),
            # ------------------------------------------------------ Filler / Ziele
            MetricRow(
                "demo.shadow_bolt.casts", "Shadow Bolt", self.shadow_bolt_casts, "", "neutral",
                damage=self.shadow_bolt_damage,
            ),
            MetricRow(
                "demo.filler.pct", "Shadow-Bolt-Filleranteil", self.filler_pct, "%", "lower"
            ),
            MetricRow(
                "demo.targets.inner_demons", "Ziele pro Cast – Fel Firebolt (Inner Demons)",
                self.targets_inner_demons, "x", "higher",
            ),
            MetricRow(
                "demo.targets.mind_sear", "Ziele pro Cast – Mind Sear (Näherung)",
                self.targets_mind_sear, "x", "higher",
            ),
            MetricRow(
                "demo.targets.burning_cleave", "Ziele pro Cast – Burning Cleave (Näherung)",
                self.targets_burning_cleave, "x", "higher",
            ),
            MetricRow(
                "demo.shards.waste", "Verschwendete Shards", self.shard_waste, "", "lower"
            ),
        ]


def _times(casts: Iterable[Cast], ability: int) -> list[int]:
    return [c.t for c in casts if c.ability == ability]


def _count_summons(summon_events: Iterable[dict[str, Any]], abilities: Iterable[int]) -> int:
    wanted = set(abilities)
    return sum(1 for e in summon_events if e.get("abilityGameID") in wanted)


def compute_demo(data: FightData, general: GeneralMetrics) -> DemoMetrics:
    """Alle Demonology-(Diabolist-)Metriken eines Fights."""
    fight = data.fight
    start, end = fight.startTime, fight.endTime
    casts = general.casts
    by = general.casts_by_ability
    # Ohne DamageDone-Events lässt sich die Pet-Lebensdauer nicht schätzen.
    has_damage = data.damage_events is not None
    table = data.damage_table
    tbl_names = data.ability_names

    def rel(ts: int) -> float:
        return (ts - start) / 1000.0

    # --- Unbekannte Summon-/Buff-IDs loggen, nicht raten
    known_summons = (
        {spells.WILD_IMP_HOG_SUMMON, spells.WILD_IMP_INNER_DEMONS_SUMMON,
         spells.SUMMON_DEMONIC_TYRANT, spells.GRIMOIRE_IMP_LORD, spells.SUMMON_GLOOMHOUND,
         spells.SUMMON_CHARHOUND}
        | spells.CALL_DREADSTALKERS_SUMMON
        | spells.DIABOLIC_RITUAL_SUMMONS
        | spells.ARGUS_SUMMONS
    )
    seen_summons = {e.get("abilityGameID") for e in data.summon_events}
    for aid in seen_summons - known_summons - spells.UTILITY:
        log.warning(
            "Unbekannte Summon-ID %s (%s) – bitte in spells.py eintragen.",
            aid, spells.name(aid, tbl_names),
        )

    # --- Tyrant
    tyrant_times = _times(casts, spells.SUMMON_DEMONIC_TYRANT)
    tyrant_drift = drifts(tyrant_times, rules.TYRANT_COOLDOWN_S)
    tyrant_damage = table_damage(table, spells.SUMMON_DEMONIC_TYRANT)
    _, tyrant_hits = table_uses_hits(table, spells.SUMMON_DEMONIC_TYRANT)

    # --- Pets (Näherung über Summon + letzter Treffer)
    hog_spans = pet_spans(
        data.summon_events, data.damage_events, [spells.WILD_IMP_HOG_SUMMON],
        damage_ability=spells.FEL_FIREBOLT,
    )
    inner_spans = pet_spans(
        data.summon_events, data.damage_events, [spells.WILD_IMP_INNER_DEMONS_SUMMON],
        damage_ability=spells.FEL_FIREBOLT,
    )
    dread_spans = pet_spans(
        data.summon_events, data.damage_events, spells.CALL_DREADSTALKERS_SUMMON
    )
    demon_spans = hog_spans + inner_spans + dread_spans

    # --- Dominion-Portalfenster
    portals = buff_windows(data.buff_events, spells.DOMINION_OF_ARGUS_PORTAL_BUFF, end)
    argus = [
        e["timestamp"] for e in data.summon_events
        if e.get("abilityGameID") in spells.ARGUS_SUMMONS
    ]

    hog_casts = [c for c in casts if c.ability == spells.HAND_OF_GULDAN]
    ruination_casts = [c for c in casts if c.ability == spells.RUINATION]
    implosion_casts = [c for c in casts if c.ability == spells.IMPLOSION]
    window_ms = int(rules.TYRANT_WINDOW_S * 1000)

    windows: list[TyrantWindow] = []
    for i, t in enumerate(tyrant_times):
        w_end = min(t + window_ms, end)
        portal = next((p for p in portals if p[0] <= t + 1000 and p[1] > t), None)
        fallback = (t, min(t + int(rules.DOMINION_PORTAL_S * 1000), end))
        p_start, p_end = portal if portal else fallback
        windows.append(
            TyrantWindow(
                at_s=rel(t),
                drift_s=tyrant_drift[i - 1] if i else 0.0,
                hog_casts=sum(1 for c in hog_casts if t <= c.t < w_end),
                implosions=sum(1 for c in implosion_casts if t <= c.t < w_end),
                demons_at_cast=active_at(demon_spans, t) if has_damage else None,
                demons_mean=mean_active(demon_spans, t, w_end) if has_damage else None,
                portal_hog=sum(1 for c in hog_casts if p_start <= c.t <= p_end),
                portal_ruination=sum(1 for c in ruination_casts if p_start <= c.t <= p_end),
                portal_demons=sum(1 for a in argus if p_start <= a <= p_end),
                portal_len_s=(p_end - p_start) / 1000.0 if portal else None,
            )
        )

    # --- Hand of Gul'dan
    hog_shards = [c.shards for c in hog_casts if c.shards is not None]
    hog_imps = _count_summons(data.summon_events, [spells.WILD_IMP_HOG_SUMMON])
    inner_imps = _count_summons(data.summon_events, [spells.WILD_IMP_INNER_DEMONS_SUMMON])
    fb_hog_uses, fb_hog_hits = table_uses_hits(table, spells.WILD_IMP_HOG_SUMMON)
    fb_inner_uses, fb_inner_hits = table_uses_hits(table, spells.WILD_IMP_INNER_DEMONS_SUMMON)

    # --- Demonic Core
    core = track_core(data.buff_events)
    demonbolts = [c for c in casts if c.ability == spells.DEMONBOLT]
    core_at_cast = [float(core.stacks_before(c.t)) for c in demonbolts]

    # --- Shards
    shards = shard_timeline(data.cast_events, data.resource_events, data.actor.id)
    impl_shards = [shards_before(shards, c.t) for c in implosion_casts]
    impl_shards_known = [s for s in impl_shards if s is not None]

    # --- Imps pro Implosion (Näherung)
    impl_imps = (
        [active_at(hog_spans + inner_spans, c.t) for c in implosion_casts] if has_damage else []
    )

    # --- Diabolic Ritual / Ruination
    pit_lords = _count_summons(data.summon_events, [spells.SUMMON_PIT_LORD])
    mothers = _count_summons(data.summon_events, [spells.SUMMON_MOTHER_OF_CHAOS])
    ritual_procs = _count_summons(data.summon_events, spells.DIABOLIC_RITUAL_SUMMONS)

    # --- Multi-Target
    ms_hits, ms_casts = targets_per_cast(data.damage_events, spells.MIND_SEAR)
    bc_hits, bc_casts = targets_per_cast(data.damage_events, spells.BURNING_CLEAVE)

    dread_times = _times(casts, spells.CALL_DREADSTALKERS)
    grim_times = _times(casts, spells.GRIMOIRE_IMP_LORD)
    duration = fight.duration_s

    return DemoMetrics(
        duration_s=duration,
        first_tyrant_s=rel(tyrant_times[0]) if tyrant_times else None,
        opener=[(rel(c.t), c.ability) for c in casts[:10]],
        tyrant_casts=len(tyrant_times),
        tyrant_expected=rules.expected_casts(duration, rules.TYRANT_COOLDOWN_S),
        tyrant_times_s=[rel(t) for t in tyrant_times],
        tyrant_drift_s=sum(tyrant_drift),
        tyrant_damage=tyrant_damage,
        tyrant_hits=tyrant_hits,
        windows=windows,
        dominion_damage=table_damage(table, spells.DOMINION_OF_ARGUS),
        dominion_demons=len(argus),
        dominion_portals=len(portals),
        hog_casts=len(hog_casts),
        hog_low_shard=sum(1 for s in hog_shards if s < rules.HOG_MIN_SHARDS),
        hog_shards_mean=_mean(hog_shards),
        hog_imps=hog_imps,
        hog_damage=table_damage(table, spells.HAND_OF_GULDAN_DAMAGE, sub_only=True),
        firebolts_hog=fb_hog_uses,
        firebolt_hits_hog=fb_hog_hits,
        firebolts_inner=fb_inner_uses,
        firebolt_hits_inner=fb_inner_hits,
        inner_demon_imps=inner_imps,
        demonbolt_casts=len(demonbolts),
        demonbolt_hardcasts=sum(1 for c in demonbolts if not c.instant),
        demonbolt_damage=table_damage(table, spells.DEMONBOLT),
        core_stacks_mean=_mean(core_at_cast),
        core_overcap=core.overcap,
        core_max_seen=core.max_seen,
        cores_at_end=core.stacks_at_end(end),
        implosion_casts=len(implosion_casts),
        imps_per_implosion=_mean([float(x) for x in impl_imps]) if has_damage else None,
        implosion_low_imp=sum(1 for x in impl_imps if x < rules.IMPLOSION_MIN_IMPS),
        implosion_shards_mean=_mean(impl_shards_known),
        implosion_low_shard=sum(1 for s in impl_shards_known if s < rules.IMPLOSION_MIN_SHARDS),
        implosions_in_tyrant=sum(x.implosions for x in windows),
        implosion_damage=table_damage(table, spells.IMPLOSION_DAMAGE),
        isolated_implosion_damage=table_damage(table, spells.ISOLATED_IMPLOSION),
        dreadstalker_casts=len(dread_times),
        dreadstalker_expected=rules.expected_casts(duration, rules.DREADSTALKER_COOLDOWN_S),
        dreadstalker_drift_s=sum(drifts(dread_times, rules.DREADSTALKER_COOLDOWN_S)),
        dreadstalker_damage=table_damage(table, spells.CALL_DREADSTALKERS),
        grimoire_casts=len(grim_times),
        grimoire_expected=rules.expected_casts(duration, rules.GRIMOIRE_COOLDOWN_S),
        grimoire_drift_s=sum(drifts(grim_times, rules.GRIMOIRE_COOLDOWN_S)),
        grimoire_damage=table_damage(table, spells.GRIMOIRE_IMP_LORD),
        ruination_casts=by[spells.RUINATION],
        ruination_expected=pit_lords,
        ruination_damage=table_damage(table, spells.RUINATION_DAMAGE, sub_only=True),
        infernal_bolt_casts=by[spells.INFERNAL_BOLT],
        infernal_bolt_expected=mothers,
        infernal_bolt_damage=table_damage(table, spells.INFERNAL_BOLT_DAMAGE, sub_only=True),
        ritual_procs=ritual_procs,
        ritual_damage=table_damage(table, spells.DIABOLIC_RITUAL),
        shadow_bolt_casts=by[spells.SHADOW_BOLT],
        shadow_bolt_damage=table_damage(table, spells.SHADOW_BOLT_DAMAGE, sub_only=True),
        filler_pct=100.0 * by[spells.SHADOW_BOLT] / general.casts_total
        if general.casts_total else 0.0,
        targets_inner_demons=_ratio(fb_inner_hits, fb_inner_uses),
        targets_mind_sear=_ratio(ms_hits, ms_casts),
        targets_burning_cleave=_ratio(bc_hits, bc_casts),
        shard_waste=sum(
            int(e.get("waste") or 0)
            for e in data.resource_events
            if e.get("resourceChangeType") == SOUL_SHARD_RESOURCE_TYPE
        ),
    )
