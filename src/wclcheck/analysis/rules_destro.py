"""Rotationsregeln und Konstanten für Destruction (Hellcaller).

Regelwerk (Method/Kalamazi 12.1, wörtlich aus der Design-Spec – beim nächsten Patch hier
anpassen, `destro.py` liest ausschließlich die Konstanten unten):

    - Wither nie ablaufen lassen, im Pandemic-Fenster refreshen.
    - Infernal und Malevolence beide on Cooldown, zueinander desynchronisiert.
    - Shadowburn bei Fiendish-Cruelty-Proc und gegen Shard-Overcap; der Cooldown
      resettet, wenn das Ziel stirbt.
    - Chaos Bolt gegen Overcap.
    - Soul Fire on Cooldown, bevorzugt mit Backdraft.
    - Conflagrate nie auf 2 Charges sitzen.
    - Incinerate als Filler.
    - Havoc-Fenster mit 2,5–3,5 Shards betreten.
    - Rain of Fire bei Hellcaller nur gegen Overcap.

Daraus abgeleitete Prüfungen in `destro.py`:

    1. Wither-Uptime und Refresh-Timing (Restdauer beim Refresh).
    2. Shadowburn-Auslastung: Casts, Kill-Resets, Zeit auf voller Ladung.
    3. Chaos Bolt in den Verstärkungsfenstern (Malevolence, Havoc).
    4. Conflagrate: Zeit auf voller Ladung = verschenkte Ladungen.
    5. Soul Fire: Casts gegen die per Cooldown möglichen, Anteil mit Backdraft.
    6. Malevolence / Summon Infernal: Drift zum Cooldown, Spender im Fenster.
    7. Havoc: Casts, Uptime, Shards beim Eintritt.
    8. Shard-Overcap (Näherung, siehe unten).
    9. Incinerate-Anteil an allen Spieler-Casts.

Herkunft der Konstanten
-----------------------
Der Live-Log liefert keine Tooltip-Werte. Alles, was nicht sicher bekannt ist, wurde aus
Fight 17 des Referenz-Reports qCZ2bPkFVzgc46Lp (Entombed Sentinels, 388 s) geschätzt; die
Schätzmethode steht jeweils am Wert und ist über `estimate_recharge_s` reproduzierbar.
Die Werte sind bewusst *feste* Konstanten und keine pro Kampf neu geschätzten Größen,
damit Schauderbart und die Vergleichsspieler an derselben Messlatte hängen.
"""

from __future__ import annotations

from collections.abc import Sequence

# --------------------------------------------------------------------------- Wither
# Gemessen: sauberer applydebuff → removedebuff ohne Refresh dazwischen = 21,0 s;
# längste beobachtete Restlaufzeit nach einem refreshdebuff = 27,3 s = 21 s × 1,3.
# Beides passt exakt zu Basisdauer 21 s + Pandemic-Deckel von 30 %.
WITHER_DURATION_S = 21.0
PANDEMIC_FRACTION = 0.30
PANDEMIC_WINDOW_S = WITHER_DURATION_S * PANDEMIC_FRACTION  # 6,3 s
WITHER_MAX_DURATION_S = WITHER_DURATION_S * (1.0 + PANDEMIC_FRACTION)  # 27,3 s
# > 50 % Restdauer beim Refresh = zu früh (Spec).
REFRESH_TOO_EARLY_FRACTION = 0.50
REFRESH_TOO_EARLY_S = WITHER_DURATION_S * REFRESH_TOO_EARLY_FRACTION  # 10,5 s
# Toleranz, um einen Wither-Cast dem zugehörigen Debuff-Event zuzuordnen. Wither ist
# instant, der Debuff erscheint aber mit Flugzeit; im Referenz-Log 0,0–1,3 s später.
DEBUFF_MATCH_WINDOW_S = 2.0

# --------------------------------------------------------------------------- Ladungen
SHADOWBURN_CHARGES = 2
# Schätzung, nicht gesichert: der Minimum-Schätzer (kürzester Abstand zwischen Cast i und
# Cast i+2 ohne Gegnertod dazwischen) liefert auf Fight 17 nur 2,1 s, weil Fiendish-Cruelty-
# Procs und Kill-Resets Ladungen außer der Reihe zurückgeben. Deshalb auf den plausiblen
# Bereich [6, 14] s begrenzt → 6,0 s. Quercheck: die Vergleichsspieler kommen auf diesem
# Boss auf 60–63 Casts in 388 s, das entspricht rund 6,2 s pro Ladung.
SHADOWBURN_RECHARGE_S = 6.0
SHADOWBURN_RECHARGE_RANGE_S = (6.0, 14.0)

CONFLAGRATE_CHARGES = 2
# Schätzung: Minimum-Schätzer über Cast i → Cast i+2 ohne Gegnertod dazwischen = 6,82 s,
# begrenzt auf [5, 13] s. Quercheck: 56 Casts in 388 s = 6,93 s pro Cast, der Spieler hat
# Conflagrate also praktisch im Recharge-Takt benutzt – der Schätzer ist hier belastbar.
CONFLAGRATE_RECHARGE_S = 6.8
CONFLAGRATE_RECHARGE_RANGE_S = (5.0, 13.0)

# --------------------------------------------------------------------------- Cooldowns
# Die Drift-Messung zu diesen Cooldowns (Zeilen „…-Drift zum CD") steckt in
# `timeline.cooldown_drift_s` und benutzt dieselbe Toleranz `timeline.DRIFT_TOLERANCE_S`
# wie Demonology: Verspätungen bis 0,5 s gelten als Reaktionszeit-/GCD-Rauschen und
# zählen als 0, darüber zählt die volle Verspätung. Damit sind die gleichnamigen Zeilen
# beider Specs direkt vergleichbar.
# Malevolence: kleinster Abstand zweier Casts 60,3 s bei 7 Casts in 388 s → 60 s, sicher.
MALEVOLENCE_CD_S = 60.0
# Summon Infernal: Abstände 90,6 / 90,9 / 91,6 / 91,7 s → 90 s, sicher.
INFERNAL_CD_S = 90.0
# Havoc: Abstände 30,4 / 30,6 / 30,7 / 30,7 / 31,3 … → 30 s, sicher.
HAVOC_CD_S = 30.0
# Havoc-Debuff: alle 11 applydebuff → removedebuff exakt 20,0 s → 20 s, sicher.
HAVOC_DURATION_S = 20.0
# Soul Fire: NICHT gesichert. Der Spieler hat nur 7-mal gecastet, der kleinste Abstand
# (47,3 s) ist deshalb nur eine obere Schranke für den echten Cooldown. Angesetzt wird
# 45 s (auf [20, 60] begrenzter Minimum-Schätzer). Die Metrik „Casts vs. möglich" ist
# damit eine Näherung und in der Ausgabe als solche gekennzeichnet.
SOUL_FIRE_CD_S = 45.0
SOUL_FIRE_CD_RANGE_S = (20.0, 60.0)

# --------------------------------------------------------------------------- Shards
SOUL_SHARD_MAX = 5.0
# Havoc-Fenster laut Guide mit 2,5–3,5 Shards betreten.
HAVOC_ENTRY_SHARDS = (2.5, 3.5)
# Shadowburn resettet, wenn das Ziel kurz nach dem Cast stirbt.
KILL_RESET_WINDOW_S = 5.0


def clamp(value: float, lo: float, hi: float) -> float:
    """Begrenzt einen geschätzten Wert auf einen plausiblen Bereich."""
    return max(lo, min(hi, value))


def estimate_recharge_s(
    cast_times_ms: Sequence[int],
    charges: int,
    death_times_ms: Sequence[int] = (),
    *,
    fallback: float,
    lo: float,
    hi: float,
) -> float:
    """Schätzt die Recharge-Zeit einer Ladungs-Fähigkeit aus den Cast-Zeitpunkten.

    Modell: aus vollen Ladungen heraus feuert ein Spieler `charges` Casts dicht
    hintereinander und muss dann genau eine Recharge-Zeit warten. Der kürzeste Abstand
    zwischen Cast i und Cast i+charges ist damit die beste Untergrenze für die Recharge.
    Fenster, in denen ein Gegner gestorben ist, werden verworfen, weil Kill-Resets
    Ladungen außer der Reihe zurückgeben und den Schätzer nach unten verzerren.

    Das Ergebnis wird auf [lo, hi] begrenzt; ohne verwertbare Kandidaten kommt `fallback`.
    """
    times = sorted(cast_times_ms)
    deaths = sorted(death_times_ms)
    candidates: list[float] = []
    for i in range(len(times) - charges):
        a, b = times[i], times[i + charges]
        if any(a <= d <= b for d in deaths):
            continue
        candidates.append((b - a) / 1000.0)
    if not candidates:
        return fallback
    return clamp(min(candidates), lo, hi)


def estimate_cooldown_s(
    cast_times_ms: Sequence[int], *, fallback: float, lo: float, hi: float
) -> float:
    """Schätzt den Cooldown einer Fähigkeit ohne Ladungen als kleinsten Cast-Abstand."""
    times = sorted(cast_times_ms)
    deltas = [(b - a) / 1000.0 for a, b in zip(times, times[1:], strict=False)]
    if not deltas:
        return fallback
    return clamp(min(deltas), lo, hi)
