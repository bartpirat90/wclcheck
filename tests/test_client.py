"""Client-Tests mit httpx.MockTransport: Token, Cache, Paginierung, Fehler."""

from __future__ import annotations

import json

import httpx
import pytest

from wclcheck.auth import TOKEN_URL, TokenProvider
from wclcheck.cache import DiskCache
from wclcheck.client import API_URL, WCLClient, WCLError
from wclcheck.config import Settings
from wclcheck.models import Fight

REPORT_JSON = {
    "code": "qCZ2bPkFVzgc46Lp",
    "title": "Test",
    "startTime": 1000,
    "endTime": 900000,
    "region": {"slug": "eu"},
    "zone": {"id": 44, "name": "Testraid"},
    "fights": [
        {
            "id": 22,
            "encounterID": 3001,
            "name": "Vashnik the Malignant",
            "kill": True,
            "difficulty": 5,
            "startTime": 500000,
            "endTime": 783000,
            "averageItemLevel": 289.4,
            "size": 20,
            "inProgress": False,
            "friendlyPlayers": [3, 4],
        },
        {
            "id": 23,
            "encounterID": 3002,
            "name": "Laufend",
            "kill": None,
            "difficulty": 5,
            "startTime": 800000,
            "endTime": 850000,
            "inProgress": True,
            "friendlyPlayers": [3],
        },
    ],
    "masterData": {
        "actors": [
            {"id": 3, "name": "Schauderbart", "type": "Player", "subType": "Warlock",
             "petOwner": None, "server": "Antonidas"},
            {"id": 4, "name": "Other", "type": "Player", "subType": "Mage",
             "petOwner": None, "server": "Antonidas"},
            {"id": 50, "name": "Wild Imp", "type": "Pet", "subType": "Pet", "petOwner": 3},
            {"id": 51, "name": "Dreadstalker", "type": "Pet", "subType": "Pet", "petOwner": 3},
        ]
    },
}


class FakeAPI:
    """Simuliert Token-Endpunkt und GraphQL; zählt Aufrufe."""

    def __init__(self) -> None:
        self.token_calls = 0
        self.graphql_calls = 0
        self.event_pages = [
            {"data": [{"timestamp": 500100, "type": "cast"}], "nextPageTimestamp": 600000},
            {"data": [{"timestamp": 600000, "type": "cast"}], "nextPageTimestamp": None},
        ]
        self.fail_token = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        if str(request.url) == TOKEN_URL:
            self.token_calls += 1
            if self.fail_token:
                return httpx.Response(401, json={"error": "invalid_client"})
            return httpx.Response(200, json={"access_token": f"tok{self.token_calls}",
                                             "expires_in": 3600})
        assert str(request.url) == API_URL
        assert request.headers["Authorization"].startswith("Bearer tok")
        self.graphql_calls += 1
        body = json.loads(request.content)
        query, variables = body["query"], body["variables"]
        rl = {"limitPerHour": 18000, "pointsSpentThisHour": 12, "pointsResetIn": 3000}
        if "query Report(" in query:
            return httpx.Response(200, json={"data": {
                "reportData": {"report": REPORT_JSON}, "rateLimitData": rl}})
        if "query Events(" in query:
            page = 0 if variables["startTime"] == 500000 else 1
            return httpx.Response(200, json={"data": {
                "reportData": {"report": {"events": self.event_pages[page]}},
                "rateLimitData": rl}})
        if "query Table(" in query:
            return httpx.Response(200, json={"data": {
                "reportData": {"report": {"table": {"data": {"entries": []}}}},
                "rateLimitData": rl}})
        return httpx.Response(200, json={"errors": [{"message": "unbekannte Query"}]})


@pytest.fixture
def api() -> FakeAPI:
    return FakeAPI()


@pytest.fixture
def client(api: FakeAPI, settings: Settings, cache: DiskCache) -> WCLClient:
    http = httpx.Client(transport=httpx.MockTransport(api.handler))
    tokens = TokenProvider(settings.client_id, settings.client_secret, cache.root, http)
    return WCLClient(settings, cache, http=http, tokens=tokens)


def test_report_parsing_and_actor_resolution(client: WCLClient, api: FakeAPI):
    rep = client.report("qCZ2bPkFVzgc46Lp")
    assert rep.region == "EU"
    assert rep.zone.name == "Testraid"
    player = rep.find_player("schauderbart")
    assert player is not None and player.id == 3
    assert {p.name for p in rep.pets_of(3)} == {"Wild Imp", "Dreadstalker"}
    assert [f.id for f in rep.kills()] == [22]
    assert rep.fight(22).duration_s == 283.0
    assert rep.fight(23).is_complete is False
    assert client.last_rate_limit["pointsSpentThisHour"] == 12
    assert api.token_calls == 1


def test_report_is_cached_for_60s(client: WCLClient, api: FakeAPI):
    client.report("qCZ2bPkFVzgc46Lp")
    client.report("qCZ2bPkFVzgc46Lp")
    assert api.graphql_calls == 1


def test_token_is_cached_on_disk(settings: Settings, cache: DiskCache, api: FakeAPI):
    http = httpx.Client(transport=httpx.MockTransport(api.handler))
    TokenProvider(settings.client_id, settings.client_secret, cache.root, http).token()
    TokenProvider(settings.client_id, settings.client_secret, cache.root, http).token()
    assert api.token_calls == 1


def test_events_paginate_and_cache(client: WCLClient, api: FakeAPI):
    rep = client.report("qCZ2bPkFVzgc46Lp")
    fight = rep.fight(22)
    events = client.events(rep.code, fight, "Casts", source_id=3, include_resources=True)
    assert [e["timestamp"] for e in events] == [500100, 600000]
    assert api.graphql_calls == 3  # 1 Report + 2 Seiten
    client.events(rep.code, fight, "Casts", source_id=3, include_resources=True)
    assert api.graphql_calls == 3
    # anderer sourceID → anderer Cache-Schlüssel
    client.events(rep.code, fight, "Casts", source_id=4, include_resources=True)
    assert api.graphql_calls == 5


def test_table_unwraps_data(client: WCLClient):
    rep = client.report("qCZ2bPkFVzgc46Lp")
    assert client.table(rep.code, rep.fight(22), "Summary", source_id=3) == {"entries": []}


def test_graphql_errors_raise(client: WCLClient):
    with pytest.raises(WCLError, match="unbekannte Query"):
        client.graphql("query Nope { x }", {})


def test_missing_report_raises(settings: Settings, cache: DiskCache):
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == TOKEN_URL:
            return httpx.Response(200, json={"access_token": "tok1", "expires_in": 60})
        return httpx.Response(200, json={"data": {"reportData": {"report": None}}})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    tokens = TokenProvider("id", "s", cache.root, http)
    c = WCLClient(settings, cache, http=http, tokens=tokens)
    with pytest.raises(WCLError, match="nicht gefunden"):
        c.report("XXXXXXXXXXXXXXXX")


def test_fight_model_defaults():
    f = Fight(id=1, encounterID=2, name="x", startTime=0, endTime=1500)
    assert f.is_complete and f.duration_s == 1.5 and f.difficulty_name == "None"
