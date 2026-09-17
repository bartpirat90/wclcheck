"""Kommandozeile: `wclcheck <report-url-oder-code> [Optionen]`."""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .auth import AuthError
from .cache import DiskCache
from .client import WCLClient, WCLError
from .config import ConfigError, load_settings
from .models import Actor, Report


def _force_utf8() -> None:
    """Windows-Konsolen laufen oft mit cp1252; wir geben immer UTF-8 aus."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass


_force_utf8()
app = typer.Typer(add_completion=False, no_args_is_help=True)
console = Console()
err_console = Console(stderr=True)

_REPORT_RE = re.compile(r"(?:reports/)?(a:)?([A-Za-z0-9]{16})(?:[/#?].*)?$")
_FIGHT_RE = re.compile(r"fight=(\d+|last)")


def parse_report_arg(arg: str) -> tuple[str, int | None]:
    """Extrahiert Report-Code (inkl. `a:`-Präfix) und optional `#fight=N` aus URL oder Code."""
    arg = arg.strip()
    m = _REPORT_RE.search(arg)
    if not m:
        raise typer.BadParameter(f"Kein Report-Code erkennbar in {arg!r}")
    code = (m.group(1) or "") + m.group(2)
    fm = _FIGHT_RE.search(arg)
    fight = int(fm.group(1)) if fm and fm.group(1).isdigit() else None
    return code, fight


def parse_fight_list(value: str | None) -> list[int] | None:
    if not value:
        return None
    ids: list[int] = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        if not part.isdigit():
            raise typer.BadParameter(f"Ungültige Fight-ID {part!r}")
        ids.append(int(part))
    return ids or None


def parse_regions(value: str) -> frozenset[str]:
    """'EU', 'US', 'EU,US' oder 'ALL' → Menge der zugelassenen Regionen."""
    v = value.strip().upper()
    if v in ("ALL", "*", ""):
        return frozenset({"EU", "US", "KR", "TW", "CN"})
    regions = frozenset(p.strip() for p in v.replace("+", ",").split(",") if p.strip())
    bad = regions - {"EU", "US", "KR", "TW", "CN"}
    if bad:
        raise typer.BadParameter(f"Unbekannte Region(en): {', '.join(sorted(bad))}")
    return regions


def _fmt_duration(seconds: float) -> str:
    m, s = divmod(int(round(seconds)), 60)
    return f"{m}:{s:02d}"


def print_report_overview(report: Report, player: Actor | None, fights_shown: list[int]) -> None:
    zone = report.zone.name if report.zone else "?"
    console.print(
        f"[bold]{report.title or report.code}[/bold]  ·  {zone}  ·  "
        f"Region {report.region or '?'}  ·  {report.url()}"
    )
    if player:
        pets = report.pets_of(player.id)
        pet_names = ", ".join(sorted({p.name for p in pets})) or "keine"
        console.print(
            f"Spieler [bold]{player.name}[/bold] (Actor {player.id}, {player.subType}, "
            f"{player.server or '?'})  ·  Pets: {pet_names}"
        )

    table = Table(title="Encounter-Fights", show_lines=False)
    table.add_column("ID", justify="right")
    table.add_column("Boss")
    table.add_column("Schwierigk.")
    table.add_column("Dauer", justify="right")
    table.add_column("Kill")
    table.add_column("Ilvl", justify="right")
    table.add_column("Status")
    for f in report.fights:
        kill = "[green]Kill[/green]" if f.kill else "[red]Wipe[/red]"
        status = "läuft" if f.inProgress else ""
        if player and player.id not in f.friendlyPlayers:
            status = (status + " ohne Spieler").strip()
        style = "bold" if f.id in fights_shown else "dim"
        table.add_row(
            str(f.id),
            f.name,
            f.difficulty_name,
            _fmt_duration(f.duration_s),
            kill,
            f"{f.averageItemLevel:.1f}" if f.averageItemLevel else "",
            status,
            style=style,
        )
    console.print(table)


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"wclcheck {__version__}")
        raise typer.Exit()


@app.command()
def main(
    report: Annotated[str, typer.Argument(help="Report-URL oder -Code")],
    player: Annotated[
        str | None, typer.Option("--player", "-p", help="Spielername (Default aus Config)")
    ] = None,
    fights: Annotated[
        str | None, typer.Option("--fights", "-f", help="Fight-IDs, kommagetrennt")
    ] = None,
    comparators: Annotated[int, typer.Option(help="Anzahl Vergleichsspieler")] = 3,
    ilvl_tolerance: Annotated[int, typer.Option(help="Ilvl-Toleranz ±")] = 2,
    region: Annotated[
        str | None, typer.Option(help="Rankings-Region (EU/US), Default aus Config")
    ] = None,
    threshold: Annotated[float, typer.Option(help="Befund-Schwellwert in %")] = 8.0,
    format: Annotated[str, typer.Option("--format", help="terminal | md")] = "terminal",
    no_cache: Annotated[bool, typer.Option("--no-cache", help="Cache ignorieren")] = False,
    config: Annotated[Path | None, typer.Option(help="Pfad zur config.toml")] = None,
    debug: Annotated[bool, typer.Option("--debug", help="Debug-Ausgaben")] = False,
    version: Annotated[
        bool | None, typer.Option("--version", callback=_version_callback, is_eager=True)
    ] = None,
) -> None:
    """Vergleicht Warlock-Kills eines Reports mit Top-Spielern derselben Spec."""
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    if format not in ("terminal", "md"):
        raise typer.BadParameter("--format muss terminal oder md sein")

    try:
        settings = load_settings(config) if config else load_settings()
    except ConfigError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=2) from None

    code, url_fight = parse_report_arg(report)
    fight_ids = parse_fight_list(fights) or ([url_fight] if url_fight else None)
    player_name = player or settings.player

    cache = DiskCache()
    client = WCLClient(settings, cache)
    if no_cache:
        client.no_cache_codes.add(code)  # nur der analysierte Report wird neu gezogen
    try:
        rep = client.report(code)
    except (WCLError, AuthError) as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None

    actor = rep.find_player(player_name)
    if actor is None:
        names = ", ".join(sorted(a.name for a in rep.actors if a.is_player))
        err_console.print(f"[red]Spieler {player_name!r} nicht im Report. Vorhanden: {names}[/red]")
        raise typer.Exit(code=1)

    if fight_ids:
        selected = [f for f in rep.fights if f.id in fight_ids]
        missing = set(fight_ids) - {f.id for f in selected}
        if missing:
            err_console.print(f"[red]Fight-IDs nicht gefunden: {sorted(missing)}[/red]")
            raise typer.Exit(code=1)
    else:
        selected = [
            f for f in rep.kills() if f.is_complete and actor.id in f.friendlyPlayers
        ]

    if format == "terminal":
        print_report_overview(rep, actor, [f.id for f in selected])

    running = [f for f in selected if f.inProgress]
    for f in running:
        err_console.print(f"[yellow]Fight {f.id} ({f.name}) läuft noch, übersprungen.[/yellow]")
    selected = [f for f in selected if not f.inProgress]
    if not selected:
        err_console.print("[yellow]Keine abgeschlossenen Kills mit diesem Spieler.[/yellow]")
        raise typer.Exit(code=0)

    from .analysis.report import Options, analyze_raid
    from .output import render_markdown, render_terminal

    opts = Options(
        comparators=comparators,
        ilvl_tolerance=ilvl_tolerance,
        threshold_pct=threshold,
        regions=parse_regions(region or settings.region),
    )

    def progress(msg: str) -> None:
        err_console.print(f"[dim]… {msg}[/dim]")

    try:
        result = analyze_raid(client, rep, actor, selected, opts, progress)
    except (WCLError, AuthError) as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None

    if format == "md":
        sys.stdout.write(render_markdown(result))
    else:
        render_terminal(result, console)

    if debug and client.last_rate_limit:
        rl = client.last_rate_limit
        err_console.print(
            f"[dim]Rate-Limit: {rl.get('pointsSpentThisHour')}/{rl.get('limitPerHour')} "
            f"Punkte, Reset in {rl.get('pointsResetIn')} s · Cache {cache.hits} Treffer / "
            f"{cache.misses} Fehltreffer · {client.requests_made} Requests[/dim]"
        )


if __name__ == "__main__":
    app()
