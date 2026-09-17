"""Vergleich Spieler ↔ Vergleichsspieler und Ableitung der Befunde.

- Abweichung = (Spieler − Median der Vergleichsspieler) / |Median| in %.
- Befund = Abweichung in der schlechten Richtung über dem Schwellwert (Default 8 %).
- Geschätzter Schadenswert = Median(Schaden der Vergleichsspieler) − Schaden des Spielers,
  sofern die Metrik einen Schadenswert trägt (`MetricRow.damage`). Befunde ohne Schadenswert
  werden nach der prozentualen Abweichung sortiert und hinter die bewerteten gestellt.
- Zeilen derselben Fähigkeit (z. B. Shadowburn-Casts und Shadowburn-Schaden) tragen denselben
  Schadenswert und würden sonst zwei Befunde belegen; sie werden zu einem Befund verschmolzen,
  die Zählzeile führt, die Schadenszeile wird in Klammern angehängt.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from dataclasses import dataclass, field

from .rows import MetricRow, format_value


@dataclass
class Comparison:
    key: str
    label: str
    unit: str
    better: str
    player: float | None
    others: list[float | None]
    median: float | None
    delta_pct: float | None
    damage_player: float | None = None
    damage_median: float | None = None
    detail_player: str = ""
    details_others: list[str] = field(default_factory=list)
    compare: bool = True
    lever: bool = True

    @property
    def damage_delta(self) -> float | None:
        if self.damage_player is None or self.damage_median is None:
            return None
        return self.damage_median - self.damage_player

    @property
    def worse(self) -> bool:
        if self.delta_pct is None or self.better == "neutral":
            return False
        return self.delta_pct < 0 if self.better == "higher" else self.delta_pct > 0

    def exceeds(self, threshold_pct: float) -> bool:
        return self.delta_pct is not None and abs(self.delta_pct) >= threshold_pct

    def formatted_player(self) -> str:
        return format_value(self.player, self.unit)

    def formatted_median(self) -> str:
        return format_value(self.median, self.unit)


@dataclass
class Finding:
    key: str
    label: str
    text: str
    delta_pct: float
    damage_delta: float | None
    damage_pct: float | None  # Anteil am Gesamtschaden des Spielers


def _median(values: Sequence[float | None]) -> float | None:
    vals = [v for v in values if v is not None]
    return statistics.median(vals) if vals else None


def compare_rows(
    player_rows: Sequence[MetricRow], others_rows: Sequence[Sequence[MetricRow]]
) -> list[Comparison]:
    """Ordnet Zeilen über den Schlüssel zu; fehlende Zeilen bei Vergleichsspielern = None."""
    others_by_key = [{r.key: r for r in rows} for rows in others_rows]
    out: list[Comparison] = []
    for row in player_rows:
        matched = [d.get(row.key) for d in others_by_key]
        values = [m.value if m else None for m in matched]
        median = _median(values)
        delta = None
        if row.value is not None and median is not None:
            if median != 0:
                delta = (row.value - median) / abs(median) * 100.0
            elif row.value != 0:
                delta = 100.0 if row.value > 0 else -100.0
            else:
                delta = 0.0
        out.append(
            Comparison(
                key=row.key,
                label=row.label,
                unit=row.unit,
                better=row.better,
                player=row.value,
                others=values,
                median=median,
                delta_pct=delta,
                damage_player=row.damage,
                damage_median=_median([m.damage if m else None for m in matched]),
                detail_player=row.detail,
                details_others=[m.detail if m else "" for m in matched],
                compare=row.compare,
                lever=row.lever,
            )
        )
    return out


def derive_findings(
    comparisons: Sequence[Comparison],
    *,
    threshold_pct: float = 8.0,
    total_damage: float | None = None,
    max_findings: int = 6,
) -> list[Finding]:
    hits = [
        c for c in comparisons
        if c.compare and c.lever and c.worse and c.exceeds(threshold_pct)
    ]
    # Zeilen mit identischem Schadenswert gehören zur selben Fähigkeit: die Zählzeile (ohne
    # Einheit) führt, alle weiteren werden an sie angehängt statt eigene Befunde zu belegen.
    groups: dict[float, list[Comparison]] = {}
    for c in hits:
        if c.damage_delta is not None and c.damage_delta > 0:
            groups.setdefault(c.damage_delta, []).append(c)
    merged: dict[str, list[Comparison]] = {}
    skip: set[str] = set()
    for members in groups.values():
        if len(members) < 2:
            continue
        primary = next((m for m in members if m.unit == ""), members[0])
        merged[primary.key] = [m for m in members if m is not primary]
        skip.update(m.key for m in members if m is not primary)

    candidates: list[Finding] = []
    for c in hits:
        if c.key in skip:
            continue
        dmg = c.damage_delta
        if dmg is not None and dmg <= 0:
            dmg = None  # kein Schadensnachteil trotz Abweichung → nicht schadensbewertet
        dmg_pct = (dmg / total_damage * 100.0) if (dmg and total_damage) else None
        text = f"{c.label}: {c.formatted_player()} vs. {c.formatted_median()} (Median)"
        if dmg is not None:
            text += f" – ~{dmg / 1e6:.1f}m Schaden"
            extras = [
                (f"{d.formatted_player()} vs. {d.formatted_median()}" if d.unit == "m"
                 else f"{d.label} {d.formatted_player()} vs. {d.formatted_median()}")
                for d in merged.get(c.key, [])
            ]
            if extras:
                text += f" ({'; '.join(extras)})"
            if dmg_pct is not None:
                text += f", ~{dmg_pct:.0f} %"
        else:
            text += f", {c.delta_pct:+.0f} %"
        candidates.append(
            Finding(
                key=c.key,
                label=c.label,
                text=text,
                delta_pct=c.delta_pct or 0.0,
                damage_delta=dmg,
                damage_pct=dmg_pct,
            )
        )
    candidates.sort(
        key=lambda f: (f.damage_delta is None, -(f.damage_delta or 0.0), -abs(f.delta_pct))
    )
    return candidates[:max_findings]


@dataclass
class Lever:
    key: str
    label: str
    bosses: int
    damage_total: float | None
    mean_delta_pct: float

    @property
    def text(self) -> str:
        base = f"{self.label}: auf {self.bosses} Boss{'en' if self.bosses != 1 else ''}"
        if self.damage_total:
            return f"{base}, zusammen ~{self.damage_total / 1e6:.1f}m Schaden"
        return f"{base}, im Mittel {self.mean_delta_pct:+.0f} %"


def raid_levers(findings_by_boss: dict[str, Sequence[Finding]], n: int = 3) -> list[Lever]:
    """Die n größten Hebel über alle Bosse: nach summiertem Schadenswert, dann Häufigkeit."""
    agg: dict[str, list[Finding]] = {}
    for findings in findings_by_boss.values():
        for f in findings:
            agg.setdefault(f.key, []).append(f)
    levers = []
    for key, fs in agg.items():
        dmg = [f.damage_delta for f in fs if f.damage_delta]
        levers.append(
            Lever(
                key=key,
                label=fs[0].label,
                bosses=len(fs),
                damage_total=sum(dmg) if dmg else None,
                mean_delta_pct=statistics.mean(f.delta_pct for f in fs),
            )
        )
    levers.sort(
        key=lambda lv: (lv.damage_total is None, -(lv.damage_total or 0), -lv.bosses,
                        -abs(lv.mean_delta_pct))
    )
    return levers[:n]
