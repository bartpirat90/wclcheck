"""Terminal-Ausgabe (rich). Vorläufig: Basismetriken pro Fight (Phase 2)."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from . import spells
from .analysis.metrics import GeneralMetrics
from .models import Fight


def fmt_m(value: float) -> str:
    return f"{value / 1e6:.2f}m"


def fmt_int(value: int | float | None) -> str:
    return "–" if value is None else f"{value:,.0f}"


def fmt_pct(value: float | None) -> str:
    return "–" if value is None else f"{value:.0f}"


def print_general(console: Console, fight: Fight, m: GeneralMetrics, names: dict[int, str]) -> None:
    console.rule(
        f"[bold]{fight.name}[/bold] (Fight {fight.id}, {fight.difficulty_name}) · "
        f"{m.spec.label} · {m.duration_s:.0f} s · {fmt_m(m.total_damage)} · "
        f"{fmt_int(m.dps)} DPS · Parse {fmt_pct(m.parse_percent)} · Ilvl {m.ilvl or '–'}"
    )
    t = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
    t.add_column("Metrik")
    t.add_column("Wert", justify="right")
    t.add_row("Spieler-Casts", str(m.casts_total))
    t.add_row("Casts / 30 s", " ".join(f"{n:2d}" for n in m.casts_per_30s))
    t.add_row(f"Lücken > {m.gaps.threshold_s} s", f"{m.gaps.count} / {m.gaps.total_s:.1f} s")
    t.add_row("Abgebrochene Casts", str(len(m.cancelled)))
    if m.reaction.median_s is not None:
        t.add_row(
            "Reaktion nach Instants (Median / P90)",
            f"{m.reaction.median_s:.2f} s / {m.reaction.p90_s:.2f} s "
            f"(GCD ≈ {m.reaction.gcd_estimate_s or 0:.2f} s)",
        )
    t.add_row("Aktivzeit", f"{m.active_time_s:.0f} s ({m.active_pct:.0f} %)")
    t.add_row("Tode", str(m.deaths))
    t.add_row(
        "Kampftrank",
        ", ".join(f"{s:.0f} s" for s in m.potions_s) if m.potions_s else "keiner erkannt",
    )
    console.print(t)

    c = Table(title="Casts nach Zauber", box=None, pad_edge=False, title_justify="left")
    c.add_column("Zauber")
    c.add_column("Casts", justify="right")
    for ability, n in m.casts_by_ability.most_common():
        c.add_row(spells.name(ability, names), str(n))
    console.print(c)

    if m.gaps.largest:
        g = Table(title="Größte Lücken", box=None, pad_edge=False, title_justify="left")
        g.add_column("bei", justify="right")
        g.add_column("Dauer", justify="right")
        g.add_column("von → nach")
        for gap in m.gaps.largest:
            g.add_row(
                f"{gap.start_s:.1f} s",
                f"{gap.length_s:.1f} s",
                f"{spells.name(gap.from_ability, names)} → {spells.name(gap.to_ability, names)}",
            )
        console.print(g)

    gear = m.gear
    console.print(
        f"[dim]Gear: Ilvl {gear.ilvl or '–'} · Int {fmt_int(gear.intellect)} · "
        f"Crit {fmt_int(gear.crit)} · Haste {fmt_int(gear.haste)} · "
        f"Mastery {fmt_int(gear.mastery)} · Vers {fmt_int(gear.versatility)} · "
        f"Set {gear.set_pieces} · Enchants {gear.enchants} · "
        f"Trinkets {', '.join(f'{i} ({lvl})' for i, lvl in gear.trinkets) or '–'}[/dim]"
    )
