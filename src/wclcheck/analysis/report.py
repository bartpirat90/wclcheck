"""Orchestrierung: pro Boss-Kill Spieler analysieren, Vergleichsspieler holen, Befunde ableiten."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from ..client import WCLClient, WCLError
from ..models import Actor, Fight, Report
from .comparators import find_comparators, load_comparator
from .compare import Comparison, Finding, Lever, compare_rows, derive_findings, raid_levers
from .loader import FightData, load_fight_data
from .metrics import GeneralMetrics, compute_general
from .rankings import Criteria, RankingEntry, Selection, player_key
from .rows import MetricRow

log = logging.getLogger("wclcheck.report")
Progress = Callable[[str], None]


@dataclass
class Options:
    comparators: int = 3
    ilvl_tolerance: float = 2.0
    threshold_pct: float = 8.0
    regions: frozenset[str] = frozenset({"EU"})
    max_findings: int = 6

    @property
    def region_param(self) -> str | None:
        """Rankings-Query kann nur eine Region filtern; bei mehreren clientseitig filtern."""
        return next(iter(self.regions)) if len(self.regions) == 1 else None


@dataclass
class PlayerResult:
    name: str
    server: str | None
    report_code: str
    fight_id: int
    general: GeneralMetrics
    spec_rows: list[MetricRow]
    data: FightData
    entry: RankingEntry | None = None

    @property
    def url(self) -> str:
        return f"https://www.warcraftlogs.com/reports/{self.report_code}#fight={self.fight_id}"

    @property
    def rank(self) -> int | None:
        return self.entry.rank if self.entry else None

    def all_rows(self) -> list[MetricRow]:
        return self.general.rows() + self.spec_rows


@dataclass
class BossResult:
    fight: Fight
    player: PlayerResult
    comparators: list[PlayerResult] = field(default_factory=list)
    selection: Selection | None = None
    comparisons: list[Comparison] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def general_comparisons(self) -> list[Comparison]:
        return [c for c in self.comparisons if c.key.startswith("general.")]

    @property
    def spec_comparisons(self) -> list[Comparison]:
        return [c for c in self.comparisons if not c.key.startswith("general.")]


@dataclass
class RaidResult:
    report: Report
    actor: Actor
    bosses: list[BossResult]
    levers: list[Lever]
    options: Options
    errors: list[str] = field(default_factory=list)  # Bosse, die nicht analysiert werden konnten


def spec_rows_for(data: FightData, general: GeneralMetrics) -> list[MetricRow]:
    """Spec-Metriken je nach erkannter Spec; Module werden erst hier importiert."""
    try:
        if general.spec.is_demo:
            from .demo import compute_demo

            return compute_demo(data, general).rows()
        if general.spec.is_destro:
            from .destro import compute_destro

            return compute_destro(data, general).rows()
    except ImportError as exc:  # Spec-Modul (noch) nicht vorhanden
        log.warning("Spec-Metriken für %s nicht verfügbar: %s", general.spec.label, exc)
    return []


def analyze_player(data: FightData, entry: RankingEntry | None = None) -> PlayerResult:
    general = compute_general(data)
    return PlayerResult(
        name=data.actor.name,
        server=data.actor.server,
        report_code=data.report.code,
        fight_id=data.fight.id,
        general=general,
        spec_rows=spec_rows_for(data, general),
        data=data,
        entry=entry,
    )


def analyze_boss(
    client: WCLClient,
    report: Report,
    fight: Fight,
    actor: Actor,
    opts: Options,
    progress: Progress | None = None,
) -> BossResult:
    say = progress or (lambda _msg: None)
    say(f"{fight.name}: lade {actor.name}")
    data = load_fight_data(client, report, fight, actor, with_damage_events=True)
    player = analyze_player(data)
    result = BossResult(fight=fight, player=player)
    spec = player.general.spec

    if opts.comparators <= 0:
        return result
    if not spec.spec:
        result.notes.append("Spec nicht erkannt, keine Vergleichsspieler.")
        return result
    if fight.difficulty is None:
        result.notes.append("Keine Schwierigkeit im Report, keine Vergleichsspieler.")
        return result

    ilvl = player.general.ilvl or fight.averageItemLevel
    if not ilvl:
        result.notes.append("Ilvl des Spielers unbekannt, Ilvl-Filter für Vergleich deaktiviert.")
    criteria = Criteria(
        ilvl=ilvl or None,
        duration_ms=fight.duration_ms,
        ilvl_tolerance=opts.ilvl_tolerance,
        regions=opts.regions,
        exclude=frozenset({(report.code, fight.id)}),
        exclude_player=player_key(actor.name, actor.server),
    )
    say(f"{fight.name}: suche Vergleichsspieler ({spec.spec}, {fight.difficulty_name})")
    try:
        selection = find_comparators(
            client,
            encounter_id=fight.encounterID,
            spec=spec.spec,
            difficulty=fight.difficulty,
            criteria=criteria,
            n=opts.comparators,
            region=opts.region_param,
        )
    except WCLError as exc:
        result.notes.append(f"Rankings nicht ladbar: {exc}")
        return result
    result.selection = selection
    if selection.relaxed:
        result.notes.append(f"Toleranzen gelockert auf {selection.criteria.label}.")

    for entry in selection.entries:
        say(f"{fight.name}: lade {entry.name} ({entry.report_code} #{entry.fight_id})")
        comp = load_comparator(client, entry)
        if comp is None:
            result.notes.append(f"{entry.name}: Report/Spieler nicht ladbar, übersprungen.")
            continue
        pr = analyze_player(comp.data, entry)
        if pr.general.spec.spec != spec.spec:
            result.notes.append(
                f"{entry.name}: andere Spec ({pr.general.spec.label}), übersprungen."
            )
            continue
        if pr.general.spec.hero != spec.hero and spec.hero:
            result.notes.append(f"{entry.name}: anderes Hero-Talent ({pr.general.spec.label}).")
        result.comparators.append(pr)

    if len(result.comparators) < opts.comparators:
        result.notes.append(
            f"Nur {len(result.comparators)} von {opts.comparators} Vergleichsspielern gefunden."
        )
    if result.comparators:
        result.comparisons = compare_rows(
            player.all_rows(), [c.all_rows() for c in result.comparators]
        )
        result.findings = derive_findings(
            result.comparisons,
            threshold_pct=opts.threshold_pct,
            total_damage=player.general.total_damage,
            max_findings=opts.max_findings,
        )
    return result


def analyze_raid(
    client: WCLClient,
    report: Report,
    actor: Actor,
    fights: list[Fight],
    opts: Options,
    progress: Progress | None = None,
) -> RaidResult:
    bosses: list[BossResult] = []
    errors: list[str] = []
    for fight in fights:
        try:
            bosses.append(analyze_boss(client, report, fight, actor, opts, progress))
        except WCLError as exc:
            # Ein Boss darf die fertigen Ergebnisse der anderen nicht verwerfen.
            log.warning("Fight %s (%s) nicht analysierbar: %s", fight.id, fight.name, exc)
            errors.append(f"{fight.name} (Fight {fight.id}): {exc}")
    levers = raid_levers({f"{b.fight.name} #{b.fight.id}": b.findings for b in bosses})
    return RaidResult(
        report=report, actor=actor, bosses=bosses, levers=levers, options=opts, errors=errors
    )
