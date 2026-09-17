"""Ausgabe der Analyse: Terminal (rich) oder Markdown. Struktur pro Boss laut Spec:

1. Kopfzeile: Boss, Spec/Hero, Dauer, DPS, Parse, Ilvl – Spieler und Vergleichsspieler.
2. Kernmetriken nebeneinander, Abweichung zum Median in %, farbig ab Schwellwert.
3. Casts pro 30 s als Zeile pro Spieler.
4. Spec-Metriken nebeneinander.
5. Befunde (max. 6), sortiert nach geschätztem Schadenswert.
6. Gear/Stats nebeneinander ohne Bewertung.
Am Ende das Raid-Fazit mit den größten Hebeln.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from rich.console import Console
from rich.table import Table

from .analysis.compare import Comparison
from .analysis.report import BossResult, PlayerResult, RaidResult
from .analysis.rows import format_value

# ------------------------------------------------------------------ neutrale Zwischenform


@dataclass
class Cell:
    text: str
    tone: str | None = None  # "good" | "bad" | "dim" | "bold"


@dataclass
class TableSpec:
    title: str
    headers: list[str]
    rows: list[list[Cell]] = field(default_factory=list)
    align_right_from: int = 1  # ab dieser Spalte rechtsbündig


@dataclass
class BossBlock:
    heading: str
    players: TableSpec
    links: list[tuple[str, str]]
    general: TableSpec
    windows: list[tuple[str, str]]
    spec: TableSpec | None
    findings: list[str]
    gear: TableSpec
    notes: list[str]


def _fmt_int(v: float | None) -> str:
    return "–" if v is None else f"{v:,.0f}"


def _player_label(p: PlayerResult) -> str:
    return p.name


def _delta_cell(c: Comparison, threshold: float) -> Cell:
    if c.delta_pct is None or not c.compare:
        return Cell("")
    text = f"{c.delta_pct:+.0f} %"
    if abs(c.delta_pct) < threshold or c.better == "neutral":
        return Cell(text, "dim")
    return Cell(text, "bad" if c.worse else "good")


def _comparison_table(
    title: str, comps: list[Comparison], names: list[str], threshold: float
) -> TableSpec:
    headers = ["Metrik", "Du", *names]
    if names:
        headers += ["Median", "Δ"]
    t = TableSpec(title, headers)
    for c in comps:
        row = [Cell(c.label), Cell(_value_or_detail(c.player, c.unit, c.detail_player))]
        row += [
            Cell(_value_or_detail(v, c.unit, d))
            for v, d in zip(c.others, c.details_others or [""] * len(c.others), strict=False)
        ]
        if names:
            row += [Cell(format_value(c.median, c.unit)), _delta_cell(c, threshold)]
        t.rows.append(row)
    return t


def _value_or_detail(value: float | None, unit: str, detail: str) -> str:
    """Zeilen ohne Zahl (z. B. Opener-Reihenfolge) zeigen ihr Detail statt „–“."""
    if value is None:
        return detail or "–"
    return format_value(value, unit)


def build_boss_block(b: BossResult, threshold: float) -> BossBlock:
    p = b.player
    g = p.general
    everyone = [p, *b.comparators]
    names = [_player_label(c) for c in b.comparators]

    heading = (
        f"{b.fight.name} (Fight {b.fight.id}, {b.fight.difficulty_name}) · "
        f"{g.spec.label} · {g.duration_s:.0f} s · {_fmt_int(g.dps)} DPS · "
        f"Parse {format_value(g.parse_percent, '%')} · Ilvl {format_value(g.ilvl)}"
    )

    players = TableSpec(
        "Spieler", ["", "Name", "Server", "Rang", "Dauer", "DPS", "Parse", "Ilvl", "Spec"],
        align_right_from=3,
    )
    links: list[tuple[str, str]] = []
    for i, pr in enumerate(everyone):
        gg = pr.general
        tag = "Du" if i == 0 else f"V{i}"
        players.rows.append(
            [
                Cell(tag, "bold" if i == 0 else None),
                Cell(pr.name),
                Cell(pr.server or "–"),
                Cell(str(pr.rank) if pr.rank else "–"),
                Cell(f"{gg.duration_s:.0f} s"),
                Cell(_fmt_int(gg.dps)),
                Cell(format_value(gg.parse_percent, "%")),
                Cell(format_value(gg.ilvl)),
                Cell(gg.spec.label),
            ]
        )
        links.append((f"{tag} {pr.name}", pr.url))

    if b.comparisons:
        general = _comparison_table("Kernmetriken", b.general_comparisons, names, threshold)
        spec_t = (
            _comparison_table("Spec-Metriken", b.spec_comparisons, names, threshold)
            if b.spec_comparisons
            else None
        )
    else:
        from .analysis.compare import compare_rows

        general = _comparison_table("Kernmetriken", compare_rows(g.rows(), []), [], threshold)
        spec_t = (
            _comparison_table("Spec-Metriken", compare_rows(p.spec_rows, []), [], threshold)
            if p.spec_rows
            else None
        )

    windows = [
        (("Du" if i == 0 else pr.name), " ".join(f"{n:2d}" for n in pr.general.casts_per_30s))
        for i, pr in enumerate(everyone)
    ]

    gear = TableSpec("Gear/Stats (ohne Bewertung)", ["", "Du", *names])
    gear_rows = [pr.general.gear_rows() for pr in everyone]
    for idx, row in enumerate(gear_rows[0]):
        cells = [Cell(row.label)]
        for rows in gear_rows:
            r = rows[idx]
            cells.append(Cell(r.detail if r.value is None else format_value(r.value, r.unit)))
        gear.rows.append(cells)

    return BossBlock(
        heading=heading,
        players=players,
        links=links,
        general=general,
        windows=windows,
        spec=spec_t,
        findings=[f.text for f in b.findings],
        gear=gear,
        notes=list(b.notes),
    )


# ------------------------------------------------------------------------------ Terminal

_TONE_STYLE = {"good": "green", "bad": "red", "dim": "dim", "bold": "bold"}


def _rich_table(spec: TableSpec) -> Table:
    t = Table(title=spec.title, title_justify="left", box=None, pad_edge=False,
              header_style="bold")
    for i, h in enumerate(spec.headers):
        t.add_column(h, justify="right" if i >= spec.align_right_from else "left",
                     overflow="fold")
    for row in spec.rows:
        t.add_row(*[_rich_cell(c) for c in row])
    return t


def _rich_cell(c: Cell) -> str:
    style = _TONE_STYLE.get(c.tone or "")
    text = c.text.replace("[", "\\[")
    return f"[{style}]{text}[/{style}]" if style else text


def render_terminal(result: RaidResult, console: Console) -> None:
    thr = result.options.threshold_pct
    for b in result.bosses:
        block = build_boss_block(b, thr)
        console.rule(f"[bold]{block.heading}[/bold]", align="left")
        console.print(_rich_table(block.players))
        for tag, url in block.links:
            console.print(f"  [dim]{tag}: {url}[/dim]")
        console.print()
        console.print(_rich_table(block.general))
        console.print()
        console.print("[bold]Casts / 30 s[/bold]")
        width = max(len(n) for n, _ in block.windows)
        for name, line in block.windows:
            console.print(f"  {name:<{width}}  {line}")
        console.print()
        if block.spec:
            console.print(_rich_table(block.spec))
            console.print()
        console.print("[bold]Befunde[/bold]")
        if block.findings:
            for i, text in enumerate(block.findings, 1):
                console.print(f"  {i}. {text}")
        else:
            console.print("  [dim]keine Abweichung über Schwellwert" +
                          (" (keine Vergleichsspieler)" if not b.comparators else "") + "[/dim]")
        console.print()
        console.print(_rich_table(block.gear))
        for note in block.notes:
            console.print(f"[yellow]Hinweis: {note}[/yellow]")
        console.print()

    for err in result.errors:
        console.print(f"[red]Nicht analysiert: {err}[/red]")
    console.rule("[bold]Raid-Fazit[/bold]", align="left")
    if result.levers:
        for i, lv in enumerate(result.levers, 1):
            console.print(f"  {i}. {lv.text}")
    else:
        console.print("  [dim]keine Hebel über Schwellwert[/dim]")


# ------------------------------------------------------------------------------ Markdown


def _md_table(spec: TableSpec) -> str:
    def esc(s: str) -> str:
        return s.replace("|", "\\|")

    lines = [f"**{spec.title}**", ""]
    lines.append("| " + " | ".join(esc(h) for h in spec.headers) + " |")
    lines.append(
        "| " + " | ".join(
            ("---:" if i >= spec.align_right_from else ":---") for i in range(len(spec.headers))
        ) + " |"
    )
    for row in spec.rows:
        cells = []
        for c in row:
            text = esc(c.text)
            if c.tone == "bad":
                text = f"**{text}** 🔻"
            elif c.tone == "good":
                text = f"{text} ✅"
            elif c.tone == "bold":
                text = f"**{text}**"
            cells.append(text)
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def render_markdown(result: RaidResult) -> str:
    thr = result.options.threshold_pct
    rep = result.report
    out: list[str] = [
        f"# wclcheck – {rep.title or rep.code}",
        "",
        f"Spieler **{result.actor.name}** · {rep.zone.name if rep.zone else ''} · {rep.url()}",
        "",
    ]
    for b in result.bosses:
        block = build_boss_block(b, thr)
        out += [f"## {block.heading}", "", _md_table(block.players), ""]
        out += [f"- {tag}: <{url}>" for tag, url in block.links]
        out += ["", _md_table(block.general), ""]
        out += ["**Casts / 30 s**", "", "```"]
        width = max(len(n) for n, _ in block.windows)
        out += [f"{name:<{width}}  {line}" for name, line in block.windows]
        out += ["```", ""]
        if block.spec:
            out += [_md_table(block.spec), ""]
        out += ["**Befunde**", ""]
        out += [f"{i}. {t}" for i, t in enumerate(block.findings, 1)] or ["_keine_"]
        out += ["", _md_table(block.gear), ""]
        out += [f"> Hinweis: {n}" for n in block.notes]
        out.append("")
    out += [f"> Nicht analysiert: {e}" for e in result.errors]
    out += ["## Raid-Fazit", ""]
    out += [f"{i}. {lv.text}" for i, lv in enumerate(result.levers, 1)] or ["_keine Hebel_"]
    out.append("")
    return "\n".join(out)
