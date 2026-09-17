"""GraphQL-Client für die WCL Client-API v2 mit Disk-Cache und Rate-Limit-Beobachtung."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any

import httpx

from . import queries
from .auth import TokenProvider
from .cache import DiskCache
from .config import Settings
from .models import Ability, Fight, Report

API_URL = "https://www.warcraftlogs.com/api/v2/client"
FIGHTS_MAX_AGE_S = 60  # Live-Logs: Fight-Liste nie länger als 60 s cachen
EVENT_PAGE_LIMIT = 10000

log = logging.getLogger("wclcheck.client")


class WCLError(Exception):
    pass


class WCLClient:
    def __init__(
        self,
        settings: Settings,
        cache: DiskCache,
        http: httpx.Client | None = None,
        tokens: TokenProvider | None = None,
    ) -> None:
        self.settings = settings
        self.cache = cache
        self.http = http or httpx.Client(timeout=httpx.Timeout(60.0, connect=15.0))
        self.tokens = tokens or TokenProvider(
            settings.client_id, settings.client_secret, cache.root, self.http
        )
        self.requests_made = 0
        self.last_rate_limit: dict[str, Any] | None = None
        # Reports, die trotz Cache neu gezogen werden (`--no-cache` für den Live-Log);
        # Vergleichslogs bleiben gecacht.
        self.no_cache_codes: set[str] = set()

    def _max_age(self, code: str, default: float | None) -> float | None:
        return 0.0 if code in self.no_cache_codes else default

    # ------------------------------------------------------------------ Transport

    def graphql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        """Roher GraphQL-Aufruf ohne Cache. Erneuert den Token einmal bei 401."""
        for attempt in (1, 2):
            resp = self.http.post(
                API_URL,
                json={"query": query, "variables": variables},
                headers={"Authorization": f"Bearer {self.tokens.token()}"},
            )
            self.requests_made += 1
            if resp.status_code == 401 and attempt == 1:
                self.tokens.invalidate()
                continue
            break
        if resp.status_code == 429:
            raise WCLError("Rate-Limit erreicht (HTTP 429). Später erneut versuchen.")
        if resp.status_code != 200:
            raise WCLError(f"API-Fehler {resp.status_code}: {resp.text[:300]}")
        body = resp.json()
        if body.get("errors"):
            msg = "; ".join(e.get("message", str(e)) for e in body["errors"])
            raise WCLError(f"GraphQL-Fehler: {msg}")
        data = body.get("data") or {}
        if data.get("rateLimitData"):
            self.last_rate_limit = data["rateLimitData"]
        return data

    def cached_graphql(
        self,
        query: str,
        variables: dict[str, Any],
        *,
        key_parts: tuple[Any, ...],
        max_age: float | None = None,
    ) -> dict[str, Any]:
        key = DiskCache.key(*key_parts, DiskCache.key(query))
        hit = self.cache.get(key, max_age=max_age)
        if hit is not None:
            return hit
        data = self.graphql(query, variables)
        data.pop("rateLimitData", None)
        self.cache.set(key, data)
        return data

    # --------------------------------------------------------------------- Report

    def report(self, code: str) -> Report:
        data = self.cached_graphql(
            queries.REPORT,
            {"code": code},
            key_parts=(code, "report"),
            max_age=self._max_age(code, FIGHTS_MAX_AGE_S),
        )
        raw = (data.get("reportData") or {}).get("report")
        if not raw:
            raise WCLError(f"Report {code!r} nicht gefunden oder nicht zugänglich.")
        return Report.from_graphql(code, raw)

    def abilities(self, code: str) -> list[Ability]:
        data = self.cached_graphql(
            queries.REPORT_ABILITIES,
            {"code": code},
            key_parts=(code, "abilities"),
            max_age=self._max_age(code, None),
        )
        raw = data["reportData"]["report"]["masterData"]["abilities"] or []
        return [Ability.model_validate(a) for a in raw]

    # --------------------------------------------------------------------- Events

    def _fight_max_age(self, fight: Fight) -> float | None:
        # Abgeschlossene Fights dauerhaft, laufende nie länger als die Fight-Liste.
        return None if fight.is_complete else FIGHTS_MAX_AGE_S

    def events(
        self,
        code: str,
        fight: Fight,
        data_type: str,
        *,
        source_id: int | None = None,
        target_id: int | None = None,
        ability_id: int | None = None,
        hostility_type: str | None = None,
        include_resources: bool = False,
    ) -> list[dict[str, Any]]:
        """Alle Events eines Fights (paginiert), als Liste. Vollständig gecacht."""
        variables: dict[str, Any] = {
            "code": code,
            "fightIDs": [fight.id],
            "startTime": fight.startTime,
            "endTime": fight.endTime,
            "dataType": data_type,
            "limit": EVENT_PAGE_LIMIT,
            "includeResources": include_resources,
        }
        if source_id is not None:
            variables["sourceID"] = source_id
        if target_id is not None:
            variables["targetID"] = target_id
        if ability_id is not None:
            variables["abilityID"] = float(ability_id)
        if hostility_type is not None:
            variables["hostilityType"] = hostility_type

        key = DiskCache.key(code, fight.id, "events", variables, DiskCache.key(queries.EVENTS))
        hit = self.cache.get(key, max_age=self._max_age(code, self._fight_max_age(fight)))
        if hit is not None:
            return hit

        out: list[dict[str, Any]] = list(self._iter_event_pages(variables))
        self.cache.set(key, out)
        return out

    def _iter_event_pages(self, variables: dict[str, Any]) -> Iterator[dict[str, Any]]:
        start = variables["startTime"]
        pages = 0
        while True:
            data = self.graphql(queries.EVENTS, {**variables, "startTime": start})
            block = data["reportData"]["report"]["events"]
            pages += 1
            yield from block.get("data") or []
            nxt = block.get("nextPageTimestamp")
            if nxt is None or nxt <= start:
                break
            start = nxt
            if pages > 200:  # Schutz gegen Endlosschleifen
                raise WCLError("Zu viele Event-Seiten. Abbruch.")

    # --------------------------------------------------------------------- Tables

    def table(
        self,
        code: str,
        fight: Fight,
        data_type: str,
        *,
        source_id: int | None = None,
        target_id: int | None = None,
        view_by: str | None = None,
        hostility_type: str | None = None,
    ) -> dict[str, Any]:
        variables: dict[str, Any] = {
            "code": code,
            "fightIDs": [fight.id],
            "startTime": fight.startTime,
            "endTime": fight.endTime,
            "dataType": data_type,
        }
        if source_id is not None:
            variables["sourceID"] = source_id
        if target_id is not None:
            variables["targetID"] = target_id
        if view_by is not None:
            variables["viewBy"] = view_by
        if hostility_type is not None:
            variables["hostilityType"] = hostility_type
        data = self.cached_graphql(
            queries.TABLE,
            variables,
            key_parts=(code, fight.id, "table", variables),
            max_age=self._max_age(code, self._fight_max_age(fight)),
        )
        table = data["reportData"]["report"]["table"]
        # WCL liefert {"data": {...}}; wir geben das Innere zurück.
        return table.get("data", table) if isinstance(table, dict) else table

    # ------------------------------------------------------------------- Rankings

    def character_rankings(
        self,
        encounter_id: int,
        *,
        class_name: str,
        spec_name: str,
        difficulty: int,
        page: int = 1,
        region: str | None = None,
        max_age: float | None = 6 * 3600,
    ) -> dict[str, Any]:
        variables: dict[str, Any] = {
            "encounterID": encounter_id,
            "className": class_name,
            "specName": spec_name,
            "difficulty": difficulty,
            "page": page,
            "metric": "dps",
        }
        if region:
            variables["serverRegion"] = region
        data = self.cached_graphql(
            queries.CHARACTER_RANKINGS,
            variables,
            key_parts=("rankings", variables),
            max_age=max_age,
        )
        enc = data["worldData"]["encounter"]
        return enc["characterRankings"] if enc else {}

    def report_rankings(self, code: str, fight: Fight) -> dict[str, Any]:
        data = self.cached_graphql(
            queries.REPORT_RANKINGS,
            {"code": code, "fightIDs": [fight.id], "playerMetric": "dps"},
            key_parts=(code, fight.id, "report_rankings"),
            max_age=self._max_age(code, self._fight_max_age(fight)),
        )
        return data["reportData"]["report"]["rankings"] or {}
