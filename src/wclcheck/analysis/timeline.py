"""Gemeinsame Zeitreihen-Hilfen für alle Specs: Aura-Intervalle und Cooldown-Drift.

Diese Funktionen lagen vorher doppelt in `demo.py` und `destro.py` – mit leicht
unterschiedlicher Auslegung. Sie stehen jetzt einmal hier, damit gleich benannte
Ausgabezeilen in beiden Specs auch dasselbe messen:

- **Aura-Intervalle** (`aura_intervals`): apply/refresh öffnet, remove schließt. Ein
  `removebuff` ohne vorheriges apply gilt als Pre-Pull-Aura und beginnt am Kampfbeginn;
  eine am Kampfende noch offene Aura läuft bis Kampfende. Fallen apply und remove auf
  dieselbe Millisekunde (WCL protokolliert das beim Austausch einer Aura), bleibt die
  Aura aktiv. Alle Intervalle sind auf `[start_ms, end_ms]` beschnitten.
- **Drift zum Cooldown** (`cooldown_drift_s` / `drift_list_s`): je Cast-Paar der Abstand
  minus Cooldown, also die verlorene Zeit. Liegt die Verspätung eines Abstands bei
  höchstens `tolerance_s`, gilt sie als Rundungsrauschen (Reaktionszeit/GCD) und zählt
  als 0; darüber zählt sie in voller Höhe. Beide Specs benutzen dafür
  `DRIFT_TOLERANCE_S`, damit die Zeilen „…-Drift zum CD" vergleichbar sind.
- **Soll-Anzahl** (`expected_casts`): floor(Kampfdauer / Cooldown) + 1.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence

Interval = tuple[int, int]  # (start_ms, end_ms), absolute Zeitstempel
Span = Interval

OPEN_TYPES = frozenset({"applybuff", "refreshbuff", "applydebuff", "refreshdebuff"})
CLOSE_TYPES = frozenset({"removebuff", "removedebuff"})

# Drift unterhalb dieser Schwelle gilt als Rundungsrauschen (Reaktionszeit/GCD) und wird
# nicht als verlorene Zeit gewertet. Gilt für Demo und Destro gleichermaßen.
DRIFT_TOLERANCE_S = 0.5


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
        if kind in OPEN_TYPES or kind in CLOSE_TYPES:
            by_ts[ev["timestamp"]].add(kind)

    out: list[Interval] = []
    active_since: int | None = None
    for ts in sorted(by_ts):
        kinds = by_ts[ts]
        if kinds & OPEN_TYPES:
            if active_since is None:
                active_since = ts
        elif kinds & CLOSE_TYPES:
            out.append((active_since if active_since is not None else start_ms, ts))
            active_since = None
    if active_since is not None:
        out.append((active_since, end_ms))
    return [(max(a, start_ms), min(b, end_ms)) for a, b in out if min(b, end_ms) > max(a, start_ms)]


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
    """Gesamtdauer der Vereinigung aller Intervalle in Millisekunden."""
    return sum(b - a for a, b in merge(intervals))


def active_at(intervals: Iterable[Interval], t: int) -> int:
    """Anzahl der Intervalle, die den Zeitpunkt einschließen (Ränder zählen mit)."""
    return sum(1 for a, b in intervals if a <= t <= b)


def in_any(t: int, intervals: Sequence[Interval]) -> bool:
    """Liegt der Zeitpunkt in mindestens einem Intervall? (Ränder zählen mit)"""
    return active_at(intervals, t) > 0


# --------------------------------------------------------------------------- Drift
def drift_list_s(
    cast_times_ms: Sequence[int], cd_s: float, tolerance_s: float = 0.0
) -> list[float]:
    """Verlorene Sekunden je Cast-Paar: Abstand minus Cooldown.

    Verspätungen bis einschließlich `tolerance_s` gelten als Rauschen und werden auf 0
    gesetzt; oberhalb der Toleranz zählt die volle Verspätung (nicht um die Toleranz
    gekürzt).
    """
    times = sorted(cast_times_ms)
    out: list[float] = []
    for a, b in zip(times, times[1:], strict=False):
        lost = (b - a) / 1000.0 - cd_s
        out.append(lost if lost > tolerance_s else 0.0)
    return out


def cooldown_drift_s(
    cast_times_ms: Sequence[int], cd_s: float, tolerance_s: float = 0.0
) -> float:
    """Summierte Verspätung gegenüber dem Cooldown (s. `drift_list_s`)."""
    return sum(drift_list_s(cast_times_ms, cd_s, tolerance_s))


def expected_casts(duration_s: float, cd_s: float) -> int:
    """Soll-Anzahl eines Cooldowns über die Kampfdauer: floor(Dauer / CD) + 1."""
    if cd_s <= 0:
        return 0
    return int(duration_s // cd_s) + 1
