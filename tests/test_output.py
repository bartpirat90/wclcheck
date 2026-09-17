"""Smoke-Tests für Terminal- und Markdown-Ausgabe mit synthetischen Daten."""

from io import StringIO

from rich.console import Console

from wclcheck import spells
from wclcheck.analysis.compare import compare_rows, derive_findings, raid_levers
from wclcheck.analysis.loader import FightData
from wclcheck.analysis.metrics import compute_general
from wclcheck.analysis.rankings import RankingEntry
from wclcheck.analysis.report import BossResult, Options, PlayerResult, RaidResult
from wclcheck.analysis.rows import MetricRow
from wclcheck.models import Report
from wclcheck.output import render_markdown, render_terminal

START = 1_000_000


def _fight_data(name: str, actor_id: int, casts: int, code: str) -> FightData:
    report = Report(
        code=code, title="T", startTime=0, endTime=10_000_000, region="EU",
        zone={"id": 1, "name": "Zone"},
        fights=[{"id": 1, "encounterID": 5, "name": "Boss", "kill": True, "difficulty": 4,
                 "startTime": START, "endTime": START + 300_000, "friendlyPlayers": [actor_id]}],
        actors=[{"id": actor_id, "name": name, "type": "Player", "subType": "Warlock",
                 "server": "Srv"}],
    )
    fight = report.fight(1)
    actor = report.actor(actor_id)
    events = []
    for i in range(casts):
        t = START + i * 1200
        events.append({"timestamp": t, "type": "begincast", "sourceID": actor_id,
                       "targetID": -1, "abilityGameID": spells.SHADOW_BOLT})
        events.append({"timestamp": t + 1000, "type": "cast", "sourceID": actor_id,
                       "targetID": 9, "abilityGameID": spells.SHADOW_BOLT})
    events.append({"timestamp": START + 5000, "type": "cast", "sourceID": actor_id,
                   "targetID": 9, "abilityGameID": spells.HAND_OF_GULDAN,
                   "classResources": [{"type": 7, "amount": 30, "max": 50, "cost": 30}]})
    return FightData(
        report=report, fight=fight, actor=actor, ability_names={}, pets=[],
        cast_events=events, buff_events=[], summon_events=[],
        damage_table=[{"name": "Shadow Bolt", "guid": spells.SHADOW_BOLT, "total": casts * 50_000}],
        summary={"combatantInfo": {"stats": {"Intellect": {"max": 3000}}, "gear": []}},
    )


def _player(name, actor_id, casts, code, rank=None):
    data = _fight_data(name, actor_id, casts, code)
    general = compute_general(data)
    spec_rows = [MetricRow("demo.hog.casts", "HoG-Casts", 1, "", "higher", damage=1e6),
                 MetricRow("demo.opener", "Opener", None, "", "neutral", compare=False,
                           detail="SB → HoG")]
    entry = None
    if rank:
        entry = RankingEntry(rank, name, "Srv", "EU", 1000.0, 300_000, 320.0, code, 1, 25, False)
    return PlayerResult(name, "Srv", code, 1, general, spec_rows, data, entry)


def _raid_result(with_comparators: bool) -> RaidResult:
    me = _player("Me", 3, 100, "AAAAAAAAAAAAAAAA")
    comps = []
    if with_comparators:
        comps = [
            _player("C1", 4, 120, "BBBBBBBBBBBBBBBB", 11),
            _player("C2", 5, 130, "CCCCCCCCCCCCCCCC", 12),
        ]
    boss = BossResult(fight=me.data.fight, player=me, comparators=comps, notes=["Testhinweis"])
    if comps:
        boss.comparisons = compare_rows(me.all_rows(), [c.all_rows() for c in comps])
        boss.findings = derive_findings(boss.comparisons, total_damage=me.general.total_damage)
    levers = raid_levers({"Boss": boss.findings})
    return RaidResult(me.data.report, me.data.actor, [boss], levers, Options())


def test_markdown_with_comparators():
    md = render_markdown(_raid_result(True))
    assert "## Boss (Fight 1, Heroic)" in md
    assert "| Spieler-Casts | 101 | 121 | 131 | 126 | **-20 %** 🔻 |" in md
    assert "Spieler-Casts: 101 vs. 126 (Median), -20 %" in md
    assert "SB → HoG" in md
    assert "## Raid-Fazit" in md and "Spieler-Casts: auf 1 Boss" in md
    assert "> Hinweis: Testhinweis" in md


def test_markdown_without_comparators():
    md = render_markdown(_raid_result(False))
    assert "_keine_" in md
    assert "| Spieler-Casts | 101 |" in md


def test_terminal_renders_without_error():
    buf = StringIO()
    console = Console(file=buf, width=140, force_terminal=False, color_system=None)
    render_terminal(_raid_result(True), console)
    text = buf.getvalue()
    assert "Kernmetriken" in text and "Befunde" in text and "Raid-Fazit" in text
    assert "V1 C1: https://www.warcraftlogs.com/reports/BBBBBBBBBBBBBBBB#fight=1" in text
