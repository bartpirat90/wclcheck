"""Gemeinsames Zeilenformat für alle Metriken (Tabelle, Vergleich, Befunde)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Better = Literal["higher", "lower", "neutral"]


@dataclass(frozen=True)
class MetricRow:
    key: str  # stabiler Schlüssel, z. B. "demo.hog.casts"
    label: str  # deutsche Beschriftung
    value: float | None  # numerischer Wert (None = nicht ermittelbar)
    unit: str = ""  # "", "s", "%", "m" (Millionen Schaden), "k" (Tausend), "x" (Faktor)
    better: Better = "higher"  # Richtung, in der ein höherer Wert besser ist
    damage: float | None = None  # zugehöriger Gesamtschaden (absolut) für die Befund-Gewichtung
    detail: str = ""  # Zusatzinfo für die Ausgabe (Zeitpunkte, Listen)
    compare: bool = True  # in den Vergleich aufnehmen (Median, Δ %)
    lever: bool = True  # als Befund/Hebel zulässig (False für Ergebnisgrößen wie DPS)
    group: str = ""  # Zeilen derselben Fähigkeit; leer = Schlüssel ohne letztes Segment

    @property
    def group_key(self) -> str:
        return self.group or self.key.rsplit(".", 1)[0]

    def formatted(self) -> str:
        return format_value(self.value, self.unit)


def format_value(value: float | None, unit: str = "") -> str:
    if value is None:
        return "–"
    if unit == "m":
        return f"{value / 1e6:.2f}m"
    if unit == "k":
        return f"{value / 1e3:.0f}k"
    if unit == "%":
        return f"{value:.0f} %"
    if unit == "s":
        return f"{value:.1f} s"
    if unit == "x":
        return f"{value:.2f}"
    if float(value).is_integer():
        return f"{int(value)}"
    return f"{value:.1f}"
