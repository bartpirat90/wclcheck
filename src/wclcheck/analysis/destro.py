"""Spec-Metriken Destruction (Hellcaller): Wither, Shadowburn, Chaos Bolt, Havoc, Shards.

Alle Regeln und Konstanten stehen in `rules_destro.py`. Gematcht wird ausschließlich über
Spell-IDs aus `spells.py`.

Bekannte Näherungen (im jeweiligen `detail` der Ausgabe gekennzeichnet):

- **Shard-Overcap**: Destro erzeugt im Log keine `resourcechange`-Events für die
  Shard-Generierung (nur „Summon Overfiend" mit Betrag 0). Der Shard-Stand ist deshalb nur
  an den Snapshots der Spender-Casts (`classResources`) bekannt, also punktuell.
- **Refresh-Timing Wither**: Die Ablaufzeit wird modelliert (letzter apply/refresh + Dauer,
  Pandemic verlängert um die Restdauer, gedeckelt bei 130 %). In die Auswertung gehen alle
  Wither-Debuff-Events ein – also auch die von Havoc geklonten und die von Soul Fire
  ausgelösten Auffrischungen, nicht nur die 1:1 zu einem Wither-Cast gehörenden.
- **Kill-Reset Shadowburn**: Der Cast kennt nur die Actor-ID des Ziels, nicht die Instanz.
  Ein Cast gilt als Kill-Reset, wenn ein Gegner *dieser Actor-ID* innerhalb von 5 s stirbt.
- **Zeit auf voller Ladung**: Ladungsmodell mit geschätzter Recharge-Zeit (s. rules_destro).
- **Shards beim Havoc-Cast**: Havoc kostet keine Shards und liefert daher keinen Snapshot;
  benutzt wird der letzte bekannte Stand (Snapshot des vorherigen Spenders minus Kosten).
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from .. import spells
from . import rules_destro as rules
from .casts import Cast
from .loader import FightData
from .metrics import GeneralMetrics
from .rows import MetricRow

log = logging.getLogger("wclcheck.destro")

Interval = tuple[int, int]  # (start_ms, end_ms), absolute Zeitstempel

_OPEN_TYPES = frozenset({"applybuff", "refreshbuff", "applydebuff", "refreshdebuff"})
_CLOSE_TYPES = frozenset({"removebuff", "removedebuff"})


# --------------------------------------------------------------------------- Intervalle
def aura_intervals(
    events: Iterable[dict], ability_id: int, start_ms: int, end_ms: int
) -> list[Interval]:
    """Aktiv-Intervalle einer Aura (Buff oder Debuff) auf *einem* Träger.

    Regeln: apply/refresh öffnet, remove schließt. Fallen an derselben Millisekunde
    apply und remove zusammen (WCL protokolliert das beim Austausch einer Aura), bleibt
    die Aura aktiv. Ein remove ohne vorheriges apply gilt ab Kampfbeginn (Pre-Pull),
    eine offene Aura läuft bis Kampfende.
    """
    by_ts: dict[int, set[str]] = defaultdict(set)
    for ev in events:
        if ev.get("abilityGameID") != ability_id:
            continue
        kind = ev.get("type")
        if kind in _OPEN_TYPES or kind in _CLOSE_TYPES:
            by_ts[ev["timestamp"]].add(kind)

    out: list[Interval] = []
    active_since: int | None = None
    for ts in sorted(by_ts):
        kinds = by_ts[ts]
        if kinds & _OPEN_TYPES:
            if active_since is None:
                active_since = ts
        elif kinds & _CLOSE_TYPES:
            out.append((active_since if active_since is not None else start_ms, ts))
            active_since = None
    if active_since is not None:
        out.append((active_since, end_ms))
    return [(max(a, start_ms), min(b, end_ms)) for a, b in out if min(b, end_ms) > max(a, start_ms)]


def debuff_intervals_by_target(
    events: Sequence[dict], ability_id: int, start_ms: int, end_ms: int
) -> dict[tuple[int, int | None], list[Interval]]:
    """Aktiv-Intervalle eines Debuffs, getrennt nach (targetID, targetInstance)."""
    per_target: dict[tuple[int, int | None], list[dict]] = defaultdict(list)
    for ev in events:
        if ev.get("abilityGameID") == ability_id:
            per_target[(ev.get("targetID", -1), ev.get("targetInstance"))].append(ev)
    return {
        key: aura_intervals(evs, ability_id, start_ms, end_ms)
        for key, evs in per_target.items()
    }


def merge(intervals: Iterable[Interval]) -> list[Interval]:
    """Vereinigt überlappende Intervalle."""
    out: list[Interval] = []
    for a, b in sorted(intervals):
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def total_ms(intervals: Iterable[Interval]) -> int:
    return sum(b - a for a, b in merge(intervals))


def in_any(t: int, intervals: Sequence[Interval]) -> bool:
    return any(a <= t <= b for a, b in intervals)


# --------------------------------------------------------------------------- Wither
@dataclass
class WitherRefreshStats:
    """Klassifikation aller Wither-Auffrischungen (Näherung, s. Modulkopf)."""

    refreshes: int = 0
    pandemic: int = 0  # Restdauer ≤ 30 % der Dauer = richtig getimt
    too_early: int = 0  # Restdauer > 50 % der Dauer
    expired: int = 0  # Neuauftrag, nachdem der DoT abgelaufen war
    remaining_s: list[float] = field(default_factory=list)

    @property
    def total(self) -> int:
        """Alle bewerteten Auffrischungen inkl. der abgelaufenen Neuaufträge."""
        return self.refreshes + self.expired

    def _pct(self, n: int) -> float | None:
        return 100.0 * n / self.total if self.total else None

    @property
    def pandemic_pct(self) -> float | None:
        return self._pct(self.pandemic)

    @property
    def too_early_pct(self) -> float | None:
        return self._pct(self.too_early)

    @property
    def expired_pct(self) -> float | None:
        return self._pct(self.expired)


def classify_wither_refreshes(
    events: Sequence[dict],
    ability_id: int = spells.WITHER_DEBUFF,
    duration_s: float = rules.WITHER_DURATION_S,
) -> WitherRefreshStats:
    """Restdauer beim Refresh je Ziel, Modell: Ablauf = letzter apply/refresh + Dauer.

    Pandemic verlängert um die Restdauer, gedeckelt bei `duration_s * 1,3`.
    Ein `applydebuff`, das kein laufendes Intervall hat, obwohl das Ziel den DoT schon
    einmal hatte, zählt als „abgelaufen".
    """
    stats = WitherRefreshStats()
    max_s = duration_s * (1.0 + rules.PANDEMIC_FRACTION)
    by_target: dict[tuple[int, int | None], dict[int, set[str]]] = defaultdict(
        lambda: defaultdict(set)
    )
    for ev in events:
        if ev.get("abilityGameID") != ability_id:
            continue
        kind = ev.get("type")
        if kind in _OPEN_TYPES or kind in _CLOSE_TYPES:
            by_target[(ev.get("targetID", -1), ev.get("targetInstance"))][ev["timestamp"]].add(kind)

    for groups in by_target.values():
        expiry: float | None = None  # absolute ms
        seen = False
        for ts in sorted(groups):
            kinds = groups[ts]
            if kinds & _OPEN_TYPES:
                if expiry is None:
                    if seen:
                        stats.expired += 1
                    seen = True
                    expiry = ts + duration_s * 1000.0
                else:
                    remaining = max(0.0, (expiry - ts) / 1000.0)
                    stats.refreshes += 1
                    stats.remaining_s.append(remaining)
                    if remaining <= rules.PANDEMIC_WINDOW_S:
                        stats.pandemic += 1
                    elif remaining > rules.REFRESH_TOO_EARLY_S:
                        stats.too_early += 1
                    expiry = ts + min(duration_s + remaining, max_s) * 1000.0
            elif kinds & _CLOSE_TYPES:
                expiry = None
    return stats


# --------------------------------------------------------------------------- Ladungen
def charge_cap_time_s(
    cast_times_ms: Sequence[int],
    charges: int,
    recharge_s: float,
    start_ms: int,
    end_ms: int,
    refunds_ms: Sequence[int] = (),
) -> float:
    """Zeit, in der die Fähigkeit auf voller Ladungszahl stand (= verschenkte Recharge).

    Kontinuierliches Ladungsmodell: Ladungen füllen sich linear mit `recharge_s` pro
    Ladung. `refunds_ms` sind Zeitpunkte, an denen eine Ladung außer der Reihe
    zurückkommt (Shadowburn-Kill-Reset).
    """
    if recharge_s <= 0:
        return 0.0
    timeline = sorted(
        [(t, 0) for t in cast_times_ms] + [(t, 1) for t in refunds_ms]
    )  # 0 = Cast (vor einem Refund derselben ms), 1 = Refund
    current = float(charges)
    prev = start_ms
    capped_s = 0.0

    def advance(now: int) -> None:
        nonlocal current, capped_s, prev
        dt = (now - prev) / 1000.0
        if dt > 0:
            needed = (charges - current) * recharge_s
            if dt >= needed:
                capped_s += dt - needed
                current = float(charges)
            else:
                current += dt / recharge_s
        prev = now

    for ts, kind in timeline:
        if ts < start_ms or ts > end_ms:
            continue
        advance(ts)
        if kind == 0:
            current = max(0.0, current - 1.0)
        else:
            current = min(float(charges), current + 1.0)
    advance(end_ms)
    return capped_s


# --------------------------------------------------------------------------- Kill-Resets
def kill_reset_casts(
    casts: Sequence[Cast], deaths: Sequence[dict], window_s: float = rules.KILL_RESET_WINDOW_S
) -> tuple[list[Cast], list[int]]:
    """Shadowburn-Casts auf Ziele, die kurz danach sterben.

    Rückgabe: (Casts mit Kill-Reset, Zeitpunkte der zugehörigen Tode ohne Dubletten).
    Näherung: Der Cast kennt nur die Actor-ID, nicht die Instanz des Gegners.
    """
    window_ms = int(window_s * 1000)
    hits: list[Cast] = []
    used: set[tuple[int, int | None, int]] = set()
    for cast in casts:
        for death in deaths:
            if death.get("targetID") != cast.target:
                continue
            dt = death["timestamp"] - cast.t
            if 0 <= dt <= window_ms:
                hits.append(cast)
                used.add((death["targetID"], death.get("targetInstance"), death["timestamp"]))
                break
    return hits, sorted(ts for _, _, ts in used)


# --------------------------------------------------------------------------- Shards
@dataclass
class ShardOvercap:
    """Näherung des Shard-Overcaps aus den Snapshots der Spender-Casts."""

    time_at_cap_s: float = 0.0
    lost_shards: int = 0
    cap_snapshots: int = 0
    snapshots: int = 0


def shard_overcap(
    casts: Sequence[Cast], cap: float = rules.SOUL_SHARD_MAX
) -> ShardOvercap:
    """Zeit auf vollen Shards und verlorene Shards zwischen 5,0-Snapshot und nächstem Spender.

    Der Shard-Stand ist nur an Spender-Casts bekannt (`classResources`). Ein Snapshot mit
    dem Maximalwert belegt, dass der Spieler zu diesem Zeitpunkt am Cap stand; das Fenster
    bis zum nächsten Spender gilt als Cap-Zeit, jeder Builder-Cast darin als verlorener
    Shard. Reine Näherung, kein exakter Wert.
    """
    out = ShardOvercap()
    spender_idx = [
        i
        for i, c in enumerate(casts)
        if c.ability in spells.DESTRO_SPENDERS and c.shards is not None
    ]
    out.snapshots = len(spender_idx)
    for pos, i in enumerate(spender_idx):
        if (casts[i].shards or 0.0) < cap:
            continue
        out.cap_snapshots += 1
        if pos + 1 >= len(spender_idx):
            continue
        j = spender_idx[pos + 1]
        out.time_at_cap_s += (casts[j].t - casts[i].t) / 1000.0
        out.lost_shards += sum(
            1 for c in casts[i + 1 : j] if c.ability in spells.DESTRO_BUILDERS
        )
    return out


def last_known_shards(casts: Sequence[Cast], index: int) -> float | None:
    """Letzter bekannter Shard-Stand vor `casts[index]` (Snapshot minus Kosten)."""
    for k in range(index - 1, -1, -1):
        prev = casts[k]
        if prev.shards is None:
            continue
        return max(0.0, prev.shards - (prev.shard_cost or 0.0))
    return None


# --------------------------------------------------------------------------- Drift
def cooldown_drift_s(cast_times_ms: Sequence[int], cd_s: float) -> float:
    """Summierte Verspätung gegenüber dem Cooldown zwischen aufeinanderfolgenden Casts."""
    times = sorted(cast_times_ms)
    return sum(
        max(0.0, (b - a) / 1000.0 - cd_s) for a, b in zip(times, times[1:], strict=False)
    )


def possible_casts(duration_s: float, cd_s: float) -> int:
    return int(duration_s // cd_s) + 1 if cd_s > 0 else 0


# --------------------------------------------------------------------------- Metriken
@dataclass
class DestroMetrics:
    duration_s: float
    total_casts: int

    # Wither
    wither_casts: int = 0
    wither_uptime_pct: float = 0.0
    wither_uptime_best_pct: float = 0.0
    wither_refresh: WitherRefreshStats = field(default_factory=WitherRefreshStats)
    wither_damage: int = 0
    blackened_soul_damage: int | None = None

    # Shadowburn
    shadowburn_casts: int = 0
    shadowburn_damage: int = 0
    shadowburn_kill_resets: int = 0
    shadowburn_cap_time_s: float = 0.0
    shadowburn_recharge_s: float = rules.SHADOWBURN_RECHARGE_S

    # Chaos Bolt
    chaos_bolt_casts: int = 0
    chaos_bolt_damage: int = 0
    chaos_bolt_in_malevolence: int = 0
    chaos_bolt_with_havoc: int = 0

    # Conflagrate
    conflagrate_casts: int = 0
    conflagrate_damage: int = 0
    conflagrate_cap_time_s: float = 0.0

    # Soul Fire
    soul_fire_casts: int = 0
    soul_fire_damage: int = 0
    soul_fire_possible: int = 0
    soul_fire_with_backdraft: int = 0

    # Malevolence / Infernal
    malevolence_casts: int = 0
    malevolence_damage: int = 0
    malevolence_drift_s: float = 0.0
    malevolence_possible: int = 0
    malevolence_uptime_pct: float = 0.0
    spenders_in_malevolence: int = 0
    infernal_casts: int = 0
    infernal_damage: int = 0
    infernal_drift_s: float = 0.0
    infernal_possible: int = 0

    # Havoc
    havoc_casts: int = 0
    havoc_uptime_pct: float = 0.0
    havoc_shards: list[float] = field(default_factory=list)
    havoc_entry_ok: int = 0

    # Shards / Filler
    overcap: ShardOvercap = field(default_factory=ShardOvercap)
    incinerate_casts: int = 0
    incinerate_damage: int = 0

    # Zeitpunkte (relativ zum Kampfbeginn) für die Detailausgabe
    malevolence_times_s: list[float] = field(default_factory=list)
    infernal_times_s: list[float] = field(default_factory=list)
    havoc_times_s: list[float] = field(default_factory=list)

    @property
    def incinerate_share_pct(self) -> float | None:
        return 100.0 * self.incinerate_casts / self.total_casts if self.total_casts else None

    @property
    def soul_fire_cd_usage_pct(self) -> float | None:
        if not self.soul_fire_possible:
            return None
        return 100.0 * self.soul_fire_casts / self.soul_fire_possible

    @property
    def soul_fire_backdraft_pct(self) -> float | None:
        if not self.soul_fire_casts:
            return None
        return 100.0 * self.soul_fire_with_backdraft / self.soul_fire_casts

    @property
    def havoc_entry_ok_pct(self) -> float | None:
        if not self.havoc_shards:
            return None
        return 100.0 * self.havoc_entry_ok / len(self.havoc_shards)

    @property
    def avg_havoc_shards(self) -> float | None:
        return sum(self.havoc_shards) / len(self.havoc_shards) if self.havoc_shards else None

    def rows(self) -> list[MetricRow]:  # noqa: C901 - reine Aufzählung
        """Alle Destro-Metriken im gemeinsamen Zeilenformat."""
        approx = "Näherung"
        w = self.wither_refresh
        return [
            # ------------------------------------------------------------- Wither
            MetricRow("destro.wither.uptime", "Wither-Uptime (mind. ein Ziel)",
                      self.wither_uptime_pct, "%", "higher", damage=self.wither_damage,
                      detail=f"bestes Einzelziel {self.wither_uptime_best_pct:.0f} %"),
            MetricRow("destro.wither.casts", "Wither-Casts", self.wither_casts, "", "neutral"),
            MetricRow("destro.wither.refresh_pandemic", "Wither-Refresh im Pandemic-Fenster",
                      w.pandemic_pct, "%", "higher",
                      detail=f"{w.pandemic}/{w.total} Auffrischungen ({approx})"),
            MetricRow("destro.wither.refresh_early", "Wither-Refresh zu früh",
                      w.too_early_pct, "%", "lower",
                      detail=f"{w.too_early}/{w.total} Auffrischungen ({approx})"),
            MetricRow("destro.wither.expired", "Wither abgelaufen",
                      w.expired_pct, "%", "lower",
                      detail=f"{w.expired} Neuaufträge nach Ablauf ({approx})"),
            MetricRow("destro.wither.damage", "Wither-Schaden (inkl. Blackened Soul)",
                      self.wither_damage, "m", "higher", damage=self.wither_damage),
            MetricRow("destro.wither.blackened_soul", "Blackened-Soul-Schaden",
                      self.blackened_soul_damage, "m", "higher",
                      damage=self.blackened_soul_damage,
                      detail="" if self.blackened_soul_damage is not None
                      else "nur mit damage_events ermittelbar"),
            # ------------------------------------------------------------- Shadowburn
            MetricRow("destro.shadowburn.casts", "Shadowburn-Casts", self.shadowburn_casts,
                      "", "higher", damage=self.shadowburn_damage),
            MetricRow("destro.shadowburn.damage", "Shadowburn-Schaden", self.shadowburn_damage,
                      "m", "higher", damage=self.shadowburn_damage),
            MetricRow("destro.shadowburn.kill_resets", "Shadowburn mit Kill-Reset",
                      self.shadowburn_kill_resets, "", "higher", detail=approx),
            MetricRow("destro.shadowburn.cap_time", "Shadowburn: Zeit auf 2 Ladungen",
                      self.shadowburn_cap_time_s, "s", "lower",
                      detail=f"Recharge {self.shadowburn_recharge_s:.1f} s ({approx})"),
            # ------------------------------------------------------------- Chaos Bolt
            MetricRow("destro.chaos_bolt.casts", "Chaos-Bolt-Casts", self.chaos_bolt_casts,
                      "", "higher", damage=self.chaos_bolt_damage),
            MetricRow("destro.chaos_bolt.damage", "Chaos-Bolt-Schaden", self.chaos_bolt_damage,
                      "m", "higher", damage=self.chaos_bolt_damage),
            MetricRow("destro.chaos_bolt.in_malevolence", "Chaos Bolt im Malevolence-Fenster",
                      self.chaos_bolt_in_malevolence, "", "higher",
                      detail=f"Malevolence-Uptime {self.malevolence_uptime_pct:.0f} %"),
            MetricRow("destro.chaos_bolt.with_havoc", "Chaos Bolt mit Havoc aktiv",
                      self.chaos_bolt_with_havoc, "", "higher"),
            # ------------------------------------------------------------- Conflagrate
            MetricRow("destro.conflagrate.casts", "Conflagrate-Casts", self.conflagrate_casts,
                      "", "higher", damage=self.conflagrate_damage),
            MetricRow("destro.conflagrate.cap_time", "Conflagrate: Zeit auf 2 Ladungen",
                      self.conflagrate_cap_time_s, "s", "lower",
                      detail=f"Recharge {rules.CONFLAGRATE_RECHARGE_S:.1f} s ({approx})"),
            # ------------------------------------------------------------- Soul Fire
            MetricRow("destro.soul_fire.casts", "Soul-Fire-Casts", self.soul_fire_casts,
                      "", "higher", damage=self.soul_fire_damage),
            MetricRow("destro.soul_fire.cd_usage", "Soul Fire: Anteil der möglichen Casts",
                      self.soul_fire_cd_usage_pct, "%", "higher",
                      detail=f"{self.soul_fire_casts}/{self.soul_fire_possible} bei CD "
                             f"{rules.SOUL_FIRE_CD_S:.0f} s ({approx}, CD geschätzt)"),
            MetricRow("destro.soul_fire.backdraft", "Soul Fire mit Backdraft",
                      self.soul_fire_backdraft_pct, "%", "higher",
                      detail=f"{self.soul_fire_with_backdraft}/{self.soul_fire_casts}"),
            # ------------------------------------------------------------- Cooldowns
            MetricRow("destro.malevolence.casts", "Malevolence-Casts", self.malevolence_casts,
                      "", "higher", damage=self.malevolence_damage,
                      detail=", ".join(f"{s:.0f} s" for s in self.malevolence_times_s)),
            MetricRow("destro.malevolence.drift", "Malevolence: Drift zum Cooldown",
                      self.malevolence_drift_s, "s", "lower",
                      detail=f"CD {rules.MALEVOLENCE_CD_S:.0f} s"),
            MetricRow("destro.malevolence.spenders", "Spender im Malevolence-Fenster",
                      self.spenders_in_malevolence, "", "higher"),
            MetricRow("destro.infernal.casts", "Summon-Infernal-Casts", self.infernal_casts,
                      "", "higher", damage=self.infernal_damage,
                      detail=", ".join(f"{s:.0f} s" for s in self.infernal_times_s)),
            MetricRow("destro.infernal.drift", "Infernal: Drift zum Cooldown",
                      self.infernal_drift_s, "s", "lower",
                      detail=f"CD {rules.INFERNAL_CD_S:.0f} s"),
            # ------------------------------------------------------------- Havoc
            MetricRow("destro.havoc.casts", "Havoc-Casts", self.havoc_casts, "", "higher",
                      detail=", ".join(f"{s:.0f} s" for s in self.havoc_times_s)),
            MetricRow("destro.havoc.uptime", "Havoc-Uptime", self.havoc_uptime_pct, "%",
                      "higher"),
            MetricRow("destro.havoc.shards", "Shards beim Havoc-Cast (Ø)",
                      self.avg_havoc_shards, "x", "neutral",
                      detail=", ".join(f"{s:.1f}" for s in self.havoc_shards)
                      + " (letzter bekannter Stand, untere Schranke)"),
            MetricRow("destro.havoc.entry_ok",
                      f"Havoc-Eintritt mit {rules.HAVOC_ENTRY_SHARDS[0]:.1f}"
                      f"–{rules.HAVOC_ENTRY_SHARDS[1]:.1f} Shards",
                      self.havoc_entry_ok_pct, "%", "higher", detail=approx),
            # ------------------------------------------------------------- Shards / Filler
            MetricRow("destro.shards.cap_time", "Zeit auf 5 Shards",
                      self.overcap.time_at_cap_s, "s", "lower",
                      detail=f"{self.overcap.cap_snapshots}/{self.overcap.snapshots} "
                             f"Spender-Snapshots am Cap ({approx})"),
            MetricRow("destro.shards.lost", "Verlorene Shards (Overcap)",
                      self.overcap.lost_shards, "", "lower", detail=approx),
            MetricRow("destro.incinerate.casts", "Incinerate-Casts", self.incinerate_casts,
                      "", "neutral", damage=self.incinerate_damage),
            MetricRow("destro.incinerate.share", "Incinerate-Anteil an allen Casts",
                      self.incinerate_share_pct, "%", "lower"),
        ]


def _damage_from_events(data: FightData, *ability_ids: int) -> int | None:
    """Schaden einzelner Ability-IDs aus den Damage-Events (None ohne geladene Events)."""
    if data.damage_events is None:
        return None
    wanted = set(ability_ids)
    return int(
        sum(
            ev.get("amount", 0) + ev.get("absorbed", 0)
            for ev in data.damage_events
            if ev.get("abilityGameID") in wanted
        )
    )


def compute_destro(data: FightData, general: GeneralMetrics) -> DestroMetrics:
    """Berechnet alle Destruction-(Hellcaller-)Metriken eines Kampfes."""
    fight = data.fight
    start, end = fight.startTime, fight.endTime
    span_ms = max(1, end - start)
    casts = general.casts  # ohne Utility und ohne Havoc
    all_casts = general.all_casts
    by = general.casts_by_ability

    m = DestroMetrics(duration_s=general.duration_s, total_casts=general.casts_total)

    def times(ability: int, source: Sequence[Cast] = casts) -> list[int]:
        return [c.t for c in source if c.ability == ability]

    def rel(ts: Iterable[int]) -> list[float]:
        return [(t - start) / 1000.0 for t in ts]

    # ------------------------------------------------------------------ Auren
    havoc_intervals = merge(
        iv
        for ivs in debuff_intervals_by_target(
            data.debuff_events, spells.HAVOC_DEBUFF, start, end
        ).values()
        for iv in ivs
    )
    malevolence_intervals = aura_intervals(data.buff_events, spells.MALEVOLENCE_BUFF, start, end)
    backdraft_intervals = aura_intervals(data.buff_events, spells.BACKDRAFT_BUFF, start, end)
    wither_by_target = debuff_intervals_by_target(
        data.debuff_events, spells.WITHER_DEBUFF, start, end
    )

    # ------------------------------------------------------------------ Wither
    m.wither_casts = by[spells.WITHER]
    m.wither_uptime_pct = 100.0 * total_ms(
        iv for ivs in wither_by_target.values() for iv in ivs
    ) / span_ms
    m.wither_uptime_best_pct = (
        100.0 * max(total_ms(ivs) for ivs in wither_by_target.values()) / span_ms
        if wither_by_target
        else 0.0
    )
    m.wither_refresh = classify_wither_refreshes(data.debuff_events)
    # Die DamageDone-Tabelle fasst Wither-Direktschaden, DoT und Blackened Soul unter der
    # Cast-ID 445468 zusammen; getrennt geht nur über die Damage-Events.
    m.wither_damage = data.damage_of(
        spells.WITHER_DIRECT_DAMAGE, spells.WITHER_DOT_DAMAGE, spells.BLACKENED_SOUL_DAMAGE
    )
    m.blackened_soul_damage = _damage_from_events(data, spells.BLACKENED_SOUL_DAMAGE)
    if m.blackened_soul_damage is None:
        log.info(
            "Blackened-Soul-Schaden (ID %s) nur aus damage_events trennbar; "
            "FightData ohne with_damage_events geladen.",
            spells.BLACKENED_SOUL_DAMAGE,
        )

    # ------------------------------------------------------------------ Shadowburn
    shadowburn_casts = [c for c in casts if c.ability == spells.SHADOWBURN]
    m.shadowburn_casts = len(shadowburn_casts)
    m.shadowburn_damage = data.damage_of(spells.SHADOWBURN)
    resets, refunds = kill_reset_casts(shadowburn_casts, data.enemy_death_events)
    m.shadowburn_kill_resets = len(resets)
    m.shadowburn_recharge_s = rules.SHADOWBURN_RECHARGE_S
    m.shadowburn_cap_time_s = charge_cap_time_s(
        [c.t for c in shadowburn_casts],
        rules.SHADOWBURN_CHARGES,
        rules.SHADOWBURN_RECHARGE_S,
        start,
        end,
        refunds,
    )

    # ------------------------------------------------------------------ Chaos Bolt
    chaos_bolts = [c for c in casts if c.ability == spells.CHAOS_BOLT]
    m.chaos_bolt_casts = len(chaos_bolts)
    # Nur der eigene Chaos Bolt; der Chaos Bolt des Overfiends (434589, in der Tabelle unter
    # 434587 "Summon Overfiend") ist Pet-Schaden und bleibt draußen.
    m.chaos_bolt_damage = data.damage_of(spells.CHAOS_BOLT)
    m.chaos_bolt_in_malevolence = sum(1 for c in chaos_bolts if in_any(c.t, malevolence_intervals))
    m.chaos_bolt_with_havoc = sum(1 for c in chaos_bolts if in_any(c.t, havoc_intervals))

    # ------------------------------------------------------------------ Conflagrate
    m.conflagrate_casts = by[spells.CONFLAGRATE]
    m.conflagrate_damage = data.damage_of(spells.CONFLAGRATE)
    m.conflagrate_cap_time_s = charge_cap_time_s(
        times(spells.CONFLAGRATE),
        rules.CONFLAGRATE_CHARGES,
        rules.CONFLAGRATE_RECHARGE_S,
        start,
        end,
    )

    # ------------------------------------------------------------------ Soul Fire
    soul_fires = [c for c in casts if c.ability == spells.SOUL_FIRE]
    m.soul_fire_casts = len(soul_fires)
    m.soul_fire_damage = data.damage_of(spells.SOUL_FIRE)
    m.soul_fire_possible = possible_casts(general.duration_s, rules.SOUL_FIRE_CD_S)
    # Backdraft wird beim Beginn des Hardcasts verbraucht, deshalb `start` statt `t`.
    m.soul_fire_with_backdraft = sum(1 for c in soul_fires if in_any(c.start, backdraft_intervals))

    # ------------------------------------------------------------------ Malevolence / Infernal
    malevolence_times = times(spells.MALEVOLENCE)
    m.malevolence_casts = len(malevolence_times)
    m.malevolence_damage = data.damage_of(spells.MALEVOLENCE_DAMAGE)
    m.malevolence_drift_s = cooldown_drift_s(malevolence_times, rules.MALEVOLENCE_CD_S)
    m.malevolence_possible = possible_casts(general.duration_s, rules.MALEVOLENCE_CD_S)
    m.malevolence_times_s = rel(malevolence_times)
    m.malevolence_uptime_pct = 100.0 * total_ms(malevolence_intervals) / span_ms
    m.spenders_in_malevolence = sum(
        1
        for c in casts
        if c.ability in spells.DESTRO_SPENDERS and in_any(c.t, malevolence_intervals)
    )

    infernal_times = times(spells.SUMMON_INFERNAL)
    m.infernal_casts = len(infernal_times)
    m.infernal_damage = data.damage_of(spells.INFERNAL_DAMAGE, spells.INFERNAL_CAST_DAMAGE)
    m.infernal_drift_s = cooldown_drift_s(infernal_times, rules.INFERNAL_CD_S)
    m.infernal_possible = possible_casts(general.duration_s, rules.INFERNAL_CD_S)
    m.infernal_times_s = rel(infernal_times)

    # ------------------------------------------------------------------ Havoc
    havoc_positions = [i for i, c in enumerate(all_casts) if c.ability == spells.HAVOC]
    m.havoc_casts = len(havoc_positions)
    m.havoc_times_s = rel(all_casts[i].t for i in havoc_positions)
    m.havoc_uptime_pct = 100.0 * total_ms(havoc_intervals) / span_ms
    lo, hi = rules.HAVOC_ENTRY_SHARDS
    for i in havoc_positions:
        shards = last_known_shards(all_casts, i)
        if shards is None:
            continue
        m.havoc_shards.append(shards)
        if lo <= shards <= hi:
            m.havoc_entry_ok += 1

    # ------------------------------------------------------------------ Shards / Filler
    m.overcap = shard_overcap(casts)
    m.incinerate_casts = by[spells.INCINERATE]
    m.incinerate_damage = data.damage_of(spells.INCINERATE)
    return m
