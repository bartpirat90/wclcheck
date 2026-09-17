"""Cast-Basismetriken: Spieler-Casts, Casts pro Fenster, Lücken, Abbrüche, Reaktionszeiten.

Definitionen (an den Referenzwerten verifiziert):
- Spieler-Cast = `cast`-Event des Spielers, dessen Spell-ID nicht in
  `spells.EXCLUDED_FROM_PLAYER_CASTS` liegt (Utility + Havoc).
- Lücke = Abstand zwischen den Zeitstempeln zweier aufeinanderfolgender Spieler-Casts
  (Abschluss → Abschluss) > Schwellwert (Default 2,5 s).
- Castdauer = Zeitstempel `cast` minus Zeitstempel des zugehörigen `begincast`
  derselben Spell-ID; ohne `begincast` gilt 0. Instant = Dauer < 0,5 s.
- Abgebrochener Cast = `begincast`, auf den kein `cast` derselben ID folgt, bevor ein
  anderer On-GCD-Zauber beginnt oder abgeschlossen wird.
"""

from __future__ import annotations

import logging
import statistics
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from .. import spells

log = logging.getLogger("wclcheck.casts")

INSTANT_THRESHOLD_MS = 500
SOUL_SHARD_RESOURCE_TYPE = 7
SOUL_SHARD_SCALE = 10.0  # classResources.amount ist in Zehnteln (50 = 5 Shards)


@dataclass(frozen=True)
class Cast:
    t: int  # Zeitstempel des Abschlusses (ms, absolut)
    ability: int
    target: int
    begin: int | None = None  # Zeitstempel des begincast, None = kein begincast
    shards: float | None = None  # Soul Shards VOR dem Cast
    shard_cost: float | None = None

    @property
    def duration_ms(self) -> int:
        return 0 if self.begin is None else max(0, self.t - self.begin)

    @property
    def instant(self) -> bool:
        return self.duration_ms < INSTANT_THRESHOLD_MS

    @property
    def start(self) -> int:
        """Beginn der Aktion (begincast, sonst der Cast selbst)."""
        return self.begin if self.begin is not None else self.t


@dataclass(frozen=True)
class Cancelled:
    begin: int
    ability: int
    reason: str  # "begincast" | "cast" | "end"


@dataclass(frozen=True)
class Gap:
    start_s: float  # relativ zum Fight-Start
    length_s: float
    from_ability: int
    to_ability: int


@dataclass
class GapStats:
    threshold_s: float
    count: int = 0
    total_s: float = 0.0
    largest: list[Gap] = field(default_factory=list)


@dataclass
class ReactionStats:
    n: int = 0
    median_s: float | None = None
    p90_s: float | None = None
    gcd_estimate_s: float | None = None


def _shards(event: dict) -> tuple[float | None, float | None]:
    for res in event.get("classResources") or []:
        if res.get("type") == SOUL_SHARD_RESOURCE_TYPE:
            amount = res.get("amount")
            cost = res.get("cost")
            return (
                None if amount is None else amount / SOUL_SHARD_SCALE,
                None if cost is None else cost / SOUL_SHARD_SCALE,
            )
    return None, None


def parse_casts(
    events: Iterable[dict], actor_id: int
) -> tuple[list[Cast], list[Cancelled]]:
    """Paart begincast/cast des Spielers und erkennt abgebrochene Casts."""
    casts: list[Cast] = []
    cancelled: list[Cancelled] = []
    pending: tuple[int, int] | None = None  # (ability, begin_ts)

    def cancel(reason: str) -> None:
        nonlocal pending
        if pending is not None:
            cancelled.append(Cancelled(begin=pending[1], ability=pending[0], reason=reason))
            pending = None

    for ev in events:
        if ev.get("sourceID") != actor_id:
            continue
        kind = ev.get("type")
        ability = ev.get("abilityGameID")
        ts = ev["timestamp"]
        if kind == "begincast":
            if ability in spells.UTILITY:
                continue
            cancel("begincast")
            pending = (ability, ts)
        elif kind == "cast":
            begin = None
            if pending is not None and pending[0] == ability:
                begin = pending[1]
                pending = None
            elif ability in spells.INTERRUPTING_CASTS:
                # Nur ein bekannter On-GCD-Cast beendet den laufenden Hardcast; Trinkets,
                # Tränke und unbekannte Off-GCD-IDs laufen parallel weiter.
                cancel("cast")
            shards, cost = _shards(ev)
            casts.append(
                Cast(
                    t=ts,
                    ability=ability,
                    target=ev.get("targetID", -1),
                    begin=begin,
                    shards=shards,
                    shard_cost=cost,
                )
            )
    cancel("end")
    casts.sort(key=lambda c: c.t)
    return casts, cancelled


_warned_unknown: set[int] = set()


def player_casts(casts: Sequence[Cast], ability_names: dict[int, str] | None = None) -> list[Cast]:
    """Filtert Utility/Havoc heraus; loggt unbekannte IDs einmalig, zählt sie aber mit."""
    out: list[Cast] = []
    for c in casts:
        if c.ability in spells.EXCLUDED_FROM_PLAYER_CASTS:
            continue
        if c.ability not in spells.KNOWN_ROTATION and c.ability not in _warned_unknown:
            _warned_unknown.add(c.ability)
            log.warning(
                "Unbekannte Cast-ID %s (%s): zählt als Spieler-Cast, in spells.py eintragen.",
                c.ability,
                spells.name(c.ability, ability_names),
            )
        out.append(c)
    return out


def count_by_ability(casts: Iterable[Cast]) -> Counter[int]:
    return Counter(c.ability for c in casts)


def casts_per_window(
    casts: Iterable[Cast], start_ms: int, end_ms: int, window_ms: int = 30_000
) -> list[int]:
    n_windows = max(1, (end_ms - start_ms + window_ms - 1) // window_ms)
    out = [0] * n_windows
    for c in casts:
        idx = (c.t - start_ms) // window_ms
        if 0 <= idx < n_windows:
            out[idx] += 1
    return out


def find_gaps(
    casts: Sequence[Cast], start_ms: int, threshold_s: float = 2.5, top: int = 5
) -> GapStats:
    stats = GapStats(threshold_s=threshold_s)
    gaps: list[Gap] = []
    for a, b in zip(casts, casts[1:], strict=False):
        length = (b.t - a.t) / 1000.0
        if length > threshold_s:
            gaps.append(
                Gap(
                    start_s=(a.t - start_ms) / 1000.0,
                    length_s=length,
                    from_ability=a.ability,
                    to_ability=b.ability,
                )
            )
    stats.count = len(gaps)
    stats.total_s = sum(g.length_s for g in gaps)
    stats.largest = sorted(gaps, key=lambda g: g.length_s, reverse=True)[:top]
    return stats


def _percentile(values: Sequence[float], q: float) -> float:
    vals = sorted(values)
    if not vals:
        raise ValueError("leer")
    pos = (len(vals) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(vals) - 1)
    return vals[lo] + (vals[hi] - vals[lo]) * (pos - lo)


def reaction_times(casts: Sequence[Cast]) -> ReactionStats:
    """Zeit von einem Instant bis zum Beginn der nächsten Aktion (begincast oder Instant).

    GCD-Schätzung = kleinster Abstand zweier aufeinanderfolgender Instants, der plausibel
    über einem halben GCD liegt (≥ 0,5 s), damit Off-GCD-Artefakte nicht dominieren.
    """
    stats = ReactionStats()
    reactions: list[float] = []
    instant_pairs: list[float] = []
    for a, b in zip(casts, casts[1:], strict=False):
        if not a.instant:
            continue
        delta = (b.start - a.t) / 1000.0
        if delta < 0:
            continue
        reactions.append(delta)
        if b.instant and delta >= 0.5:
            instant_pairs.append(delta)
    stats.n = len(reactions)
    if reactions:
        stats.median_s = statistics.median(reactions)
        stats.p90_s = _percentile(reactions, 0.9)
    if instant_pairs:
        stats.gcd_estimate_s = min(instant_pairs)
    return stats


def active_time_s(casts: Sequence[Cast], duration_s: float, gcd_s: float | None) -> float:
    """Näherung: Fightdauer minus Leerlauf jenseits eines GCD zwischen zwei Aktionen."""
    if not casts:
        return 0.0
    gcd = gcd_s or 1.0
    idle = 0.0
    for a, b in zip(casts, casts[1:], strict=False):
        idle += max(0.0, (b.start - a.t) / 1000.0 - gcd)
    return max(0.0, duration_s - idle)
