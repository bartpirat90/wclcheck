"""Regressionstests zu den Befunden des Code-Reviews (Fehlerbehandlung, Vergleichsauswahl)."""

from __future__ import annotations

import json
from io import StringIO

import httpx
import pytest
from rich.console import Console

from wclcheck import spells
from wclcheck.analysis import comparators as comparators_mod
from wclcheck.analysis import report as report_mod
from wclcheck.analysis.casts import parse_casts
from wclcheck.analysis.rankings import (
    Criteria,
    RankingEntry,
    reject_reason,
    relaxation_steps,
    select_comparators,
)
from wclcheck.analysis.report import Options, RaidResult, analyze_raid
from wclcheck.auth import TOKEN_URL, AuthError, TokenProvider
from wclcheck.cache import DiskCache
from wclcheck.client import WCLClient, WCLError
from wclcheck.config import Settings
from wclcheck.models import Fight, Report
from wclcheck.output import render_markdown, render_terminal

RL = {"limitPerHour": 18000, "pointsSpentThisHour": 1, "pointsResetIn": 3000}
FIGHT = Fight(id=1, encounterID=5, name="Boss", startTime=0, endTime=300_000, kill=True)


def _client(handler, settings: Settings, cache: DiskCache) -> WCLClient:
    http = httpx.Client(transport=httpx.MockTransport(handler))
    tokens = TokenProvider(settings.client_id, settings.client_secret, cache.root, http)
    return WCLClient(settings, cache, http=http, tokens=tokens)


def _token_ok(request: httpx.Request) -> httpx.Response | None:
    if str(request.url) == TOKEN_URL:
        return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
    return None


# ------------------------------------------------------------- Transport-/JSON-Fehler


def test_transport_error_becomes_wclerror(settings, cache):
    def handler(request):
        if (r := _token_ok(request)) is not None:
            return r
        raise httpx.ConnectError("offline", request=request)

    with pytest.raises(WCLError, match="Netzwerkfehler"):
        _client(handler, settings, cache).graphql("query Q { x }", {})


def test_non_json_response_becomes_wclerror(settings, cache):
    def handler(request):
        if (r := _token_ok(request)) is not None:
            return r
        return httpx.Response(200, text="<html>Wartung</html>")

    with pytest.raises(WCLError, match="kein JSON"):
        _client(handler, settings, cache).graphql("query Q { x }", {})


def test_token_transport_error_becomes_autherror(cache):
    def handler(request):
        raise httpx.ReadTimeout("langsam", request=request)

    http = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(AuthError, match="Netzwerkfehler"):
        TokenProvider("id", "s", cache.root, http).token()


# ------------------------------------------------------------------- token.json kaputt


@pytest.mark.parametrize(
    "content",
    ["[]", '{"client_id": "id", "access_token": "t", "expires_at": null}',
     '{"client_id": "id", "access_token": "t", "expires_at": "abc"}', "nicht json"],
)
def test_corrupt_token_cache_is_ignored(cache, content):
    cache.root.mkdir(parents=True, exist_ok=True)
    (cache.root / "token.json").write_text(content, "utf-8")
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"access_token": "fresh", "expires_in": 3600})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    assert TokenProvider("id", "s", cache.root, http).token() == "fresh"
    assert len(calls) == 1


# ------------------------------------------------------- Rankings: null und leer


def test_null_character_rankings_yield_empty_dict(settings, cache):
    def handler(request):
        if (r := _token_ok(request)) is not None:
            return r
        return httpx.Response(200, json={"data": {
            "worldData": {"encounter": {"characterRankings": None}}, "rateLimitData": RL}})

    client = _client(handler, settings, cache)
    payload = client.character_rankings(
        5, class_name="Warlock", spec_name="Destruction", difficulty=4
    )
    assert payload == {}
    sel = select_comparators(lambda p: payload, Criteria(ilvl=320, duration_ms=300_000))
    assert sel.entries == []


def test_empty_report_rankings_are_not_cached(settings, cache):
    answers = [{"data": []}, {"data": [{"fightID": 1, "roles": {}}]}]
    calls = 0

    def handler(request):
        nonlocal calls
        if (r := _token_ok(request)) is not None:
            return r
        calls += 1
        rankings = answers[min(calls, len(answers)) - 1]
        return httpx.Response(200, json={"data": {
            "reportData": {"report": {"rankings": rankings}}, "rateLimitData": RL}})

    client = _client(handler, settings, cache)
    assert client.report_rankings("XXXXXXXXXXXXXXXX", FIGHT) == {"data": []}
    assert client.report_rankings("XXXXXXXXXXXXXXXX", FIGHT)["data"]  # neu geholt
    client.report_rankings("XXXXXXXXXXXXXXXX", FIGHT)
    assert calls == 2  # danach aus dem Cache


# ------------------------------------------------ Casts: Off-GCD während Hardcast


def _ev(t, kind, ability):
    return {"timestamp": t, "type": kind, "sourceID": 3, "targetID": 9, "abilityGameID": ability}


def test_unknown_offgcd_cast_does_not_cancel_hardcast():
    events = [_ev(1000, "begincast", spells.CHAOS_BOLT), _ev(1500, "cast", 999_999),
              _ev(3000, "cast", spells.CHAOS_BOLT)]
    casts, cancelled = parse_casts(events, 3)
    assert cancelled == []
    cb = [c for c in casts if c.ability == spells.CHAOS_BOLT][0]
    assert cb.begin == 1000 and cb.duration_ms == 2000 and not cb.instant


def test_known_gcd_cast_still_cancels_hardcast():
    events = [_ev(1000, "begincast", spells.CHAOS_BOLT), _ev(1500, "cast", spells.HAVOC),
              _ev(4000, "begincast", spells.CHAOS_BOLT), _ev(6000, "cast", spells.CHAOS_BOLT)]
    casts, cancelled = parse_casts(events, 3)
    assert [c.ability for c in cancelled] == [spells.CHAOS_BOLT]
    assert [c.duration_ms for c in casts if c.ability == spells.CHAOS_BOLT] == [2000]


# ---------------------------------------------------- Rankings: Kriterien


def _entry(rank, name="Other", server="Blackhand", code=None):
    return RankingEntry(rank, name, server, "EU", 1000.0, 300_000, 320.0,
                        code or f"CODE{rank:012d}", 1, 25, False)


def test_own_character_in_other_report_is_rejected():
    c = Criteria(ilvl=320, duration_ms=300_000, exclude_player=("schauderbart", "antonidas"))
    assert reject_reason(_entry(12, "Schauderbart", "Antonidas"), c) == "eigener Charakter"
    assert reject_reason(_entry(12, "Schauderbart", None), c) == "eigener Charakter"
    assert reject_reason(_entry(12, "Schauderbart", "Blackhand"), c) is None
    assert reject_reason(_entry(12), c) is None


def test_relaxation_never_tightens_custom_tolerance():
    steps = relaxation_steps(Criteria(ilvl=320, duration_ms=1, ilvl_tolerance=5))
    assert [(s.ilvl_tolerance, s.duration_tolerance) for s in steps] == [
        (5, 0.10), (5, 0.15), (5, 0.20)
    ]
    assert all(s.exclude_player is None for s in steps)


def test_unknown_ilvl_disables_ilvl_filter():
    c = Criteria(ilvl=None, duration_ms=300_000)
    assert reject_reason(_entry(12), c) is None
    e = RankingEntry(13, "X", "S", "EU", 1.0, 300_000, None, "CODE0000000000013", 1, 25, False)
    assert reject_reason(e, c) is None


# ------------------------------------------- Orchestrierung: Fehler eingrenzen


def _report() -> Report:
    return Report(
        code="AAAAAAAAAAAAAAAA", title="T", startTime=0, endTime=10_000_000, region="EU",
        zone={"id": 1, "name": "Zone"},
        fights=[{"id": 1, "encounterID": 5, "name": "Boss A", "kill": True, "difficulty": 4,
                 "startTime": 0, "endTime": 300_000, "friendlyPlayers": [3]},
                {"id": 2, "encounterID": 6, "name": "Boss B", "kill": True, "difficulty": 4,
                 "startTime": 400_000, "endTime": 700_000, "friendlyPlayers": [3]}],
        actors=[{"id": 3, "name": "Me", "type": "Player", "subType": "Warlock",
                 "server": "Srv"}],
    )


def test_load_comparator_returns_none_when_fight_data_fails(monkeypatch, settings, cache):
    rep = _report()
    client = _client(lambda r: httpx.Response(500), settings, cache)
    monkeypatch.setattr(comparators_mod.WCLClient, "report", lambda self, code, **kw: rep)
    monkeypatch.setattr(
        comparators_mod, "load_fight_data",
        lambda *a, **k: (_ for _ in ()).throw(WCLError("GraphQL-Fehler: kaputt")),
    )
    entry = RankingEntry(11, "Me", "Srv", "EU", 1.0, 300_000, 320.0, rep.code, 1, 25, False)
    assert comparators_mod.load_comparator(client, entry) is None


def test_analyze_raid_keeps_other_bosses_when_one_fails(monkeypatch, settings, cache):
    rep = _report()
    client = _client(lambda r: httpx.Response(500), settings, cache)
    fights = list(rep.fights)

    def fake_boss(client, report, fight, actor, opts, progress=None):
        if fight.id == 2:
            raise WCLError("Rate-Limit erreicht (HTTP 429). Später erneut versuchen.")
        return report_mod.BossResult(fight=fight, player=None)  # type: ignore[arg-type]

    monkeypatch.setattr(report_mod, "analyze_boss", fake_boss)
    result = analyze_raid(client, rep, rep.actor(3), fights, Options())
    assert [b.fight.id for b in result.bosses] == [1]
    assert result.errors == [
        "Boss B (Fight 2): Rate-Limit erreicht (HTTP 429). Später erneut versuchen."
    ]


def test_output_lists_unanalysed_bosses():
    rep = _report()
    result = RaidResult(rep, rep.actor(3), [], [], Options(), errors=["Boss B (Fight 2): kaputt"])
    assert "> Nicht analysiert: Boss B (Fight 2): kaputt" in render_markdown(result)
    buf = StringIO()
    render_terminal(result, Console(file=buf, width=120, force_terminal=False, color_system=None))
    assert "Nicht analysiert: Boss B (Fight 2): kaputt" in buf.getvalue()


def test_cache_if_skips_write(settings, cache):
    def handler(request):
        if (r := _token_ok(request)) is not None:
            return r
        return httpx.Response(200, json={"data": {"x": 1, "rateLimitData": RL}})

    client = _client(handler, settings, cache)
    client.cached_graphql("query Q { x }", {}, key_parts=("k",), cache_if=lambda d: False)
    assert cache.get(DiskCache.key("k", DiskCache.key("query Q { x }"))) is None
    client.cached_graphql("query Q { x }", {}, key_parts=("k",))
    assert json.dumps(cache.get(DiskCache.key("k", DiskCache.key("query Q { x }")))) == '{"x": 1}'


def test_comparator_reports_are_cached_permanently(monkeypatch, settings, cache):
    seen = []
    client = _client(lambda r: httpx.Response(500), settings, cache)

    def fake_cached(query, variables, *, key_parts, max_age=None, cache_if=None):
        seen.append(max_age)
        return {"reportData": {"report": {
            "code": variables["code"], "title": "T", "startTime": 0, "endTime": 1,
            "fights": [], "masterData": {"actors": []}}}}

    monkeypatch.setattr(client, "cached_graphql", fake_cached)
    client.report("AAAAAAAAAAAAAAAA")
    client.report("AAAAAAAAAAAAAAAA", live=False)
    client.no_cache_codes.add("AAAAAAAAAAAAAAAA")
    client.report("AAAAAAAAAAAAAAAA", live=False)
    assert seen == [60, None, 0.0]
