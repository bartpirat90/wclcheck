"""Auswahl der Vergleichsspieler aus den WCL-Rankings (worldData.encounter.characterRankings).

Regeln (Spec):
1. Gleiche Spec, Schwierigkeit und Encounter.
2. Ilvl innerhalb ±Toleranz, Kampfdauer innerhalb ±10 %, Raidgröße 20–30, kein anonymer
   Report (`a:`-Codes), Region laut Parameter. Rang 1–10 überspringen, dann die ersten
   n Treffer nehmen.
3. Ohne n Treffer nach 5 Seiten: Toleranzen schrittweise bis ±4 Ilvl / ±20 % lockern und
   das kennzeichnen.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Any

PAGE_SIZE = 100
MAX_PAGES = 5
SKIP_TOP = 10


@dataclass(frozen=True)
class RankingEntry:
    rank: int
    name: str
    server: str | None
    region: str | None
    dps: float
    duration_ms: int
    ilvl: float | None
    report_code: str
    fight_id: int
    size: int | None
    hidden: bool

    @property
    def anonymous(self) -> bool:
        return self.hidden or self.report_code.startswith("a:")

    @property
    def url(self) -> str:
        return f"https://www.warcraftlogs.com/reports/{self.report_code}#fight={self.fight_id}"


def _norm(s: str | None) -> str:
    return (s or "").replace(" ", "").replace("'", "").casefold()


def player_key(name: str | None, server: str | None) -> tuple[str, str]:
    """Vergleichsschlüssel für „derselbe Charakter“ (Name + Server, normalisiert)."""
    return _norm(name), _norm(server)


@dataclass(frozen=True)
class Criteria:
    ilvl: float | None  # None = Ilvl des Spielers unbekannt, Filter deaktiviert
    duration_ms: int
    ilvl_tolerance: float = 2.0
    duration_tolerance: float = 0.10
    size_min: int = 20
    size_max: int = 30
    regions: frozenset[str] = frozenset({"EU"})
    skip_top: int = SKIP_TOP
    exclude: frozenset[tuple[str, int]] = frozenset()  # (report_code, fight_id) des Spielers
    # Der analysierte Charakter selbst (sein bester Kill kann in einem anderen Report liegen).
    exclude_player: tuple[str, str] | None = None

    def relaxed(self, ilvl_tolerance: float, duration_tolerance: float) -> Criteria:
        return replace(
            self, ilvl_tolerance=ilvl_tolerance, duration_tolerance=duration_tolerance
        )

    @property
    def label(self) -> str:
        return f"±{self.ilvl_tolerance:g} Ilvl / ±{self.duration_tolerance * 100:.0f} % Dauer"


@dataclass
class Selection:
    entries: list[RankingEntry]
    criteria: Criteria
    relaxed: bool
    pages_loaded: int
    candidates_seen: int = 0
    rejected: dict[str, int] = field(default_factory=dict)


def parse_rankings_page(payload: dict[str, Any], page: int) -> list[RankingEntry]:
    out: list[RankingEntry] = []
    for i, r in enumerate(payload.get("rankings") or []):
        report = r.get("report") or {}
        server = r.get("server") or {}
        if not report.get("code"):
            continue
        out.append(
            RankingEntry(
                rank=(page - 1) * PAGE_SIZE + i + 1,
                name=r.get("name") or "?",
                server=server.get("name"),
                region=(server.get("region") or None),
                dps=float(r.get("amount") or 0.0),
                duration_ms=int(r.get("duration") or 0),
                ilvl=r.get("bracketData"),
                report_code=str(report["code"]),
                fight_id=int(report.get("fightID") or 0),
                size=r.get("size"),
                hidden=bool(r.get("hidden")),
            )
        )
    return out


def reject_reason(entry: RankingEntry, c: Criteria) -> str | None:
    if entry.rank <= c.skip_top:
        return "top10"
    if entry.anonymous:
        return "anonym"
    if (entry.report_code, entry.fight_id) in c.exclude:
        return "eigener Report"
    if c.exclude_player is not None:
        name, server = player_key(entry.name, entry.server)
        if name == c.exclude_player[0] and server in ("", c.exclude_player[1]):
            return "eigener Charakter"
    if c.regions and (entry.region or "").upper() not in c.regions:
        return "Region"
    if c.ilvl is not None and (entry.ilvl is None or abs(entry.ilvl - c.ilvl) > c.ilvl_tolerance):
        return "Ilvl"
    max_delta = c.duration_tolerance * c.duration_ms
    if c.duration_ms and abs(entry.duration_ms - c.duration_ms) > max_delta:
        return "Dauer"
    if entry.size is not None and not (c.size_min <= entry.size <= c.size_max):
        return "Raidgröße"
    return None


def relaxation_steps(c: Criteria) -> list[Criteria]:
    """Ausgangs-Toleranz, dann zwei Lockerungsstufen bis ±4 Ilvl / ±20 %. Eine Stufe ist
    nie strenger als die Ausgangs-Toleranz (auch bei `--ilvl-tolerance 5`)."""
    steps = [c]
    t1 = max(c.ilvl_tolerance, min(4.0, c.ilvl_tolerance + 1))
    t2 = max(4.0, c.ilvl_tolerance)
    for tol, dur in ((t1, 0.15), (t2, 0.20)):
        if tol > steps[-1].ilvl_tolerance or dur > steps[-1].duration_tolerance:
            steps.append(c.relaxed(tol, dur))
    return steps


def select_comparators(
    fetch_page: Callable[[int], dict[str, Any]],
    criteria: Criteria,
    n: int = 3,
    max_pages: int = MAX_PAGES,
) -> Selection:
    """Lädt Seiten bis n Treffer da sind (max. max_pages), lockert danach die Toleranzen."""
    pages: list[list[RankingEntry]] = []
    steps = relaxation_steps(criteria)

    def scan(c: Criteria) -> tuple[list[RankingEntry], dict[str, int]]:
        hits: list[RankingEntry] = []
        rejected: dict[str, int] = {}
        seen: set[tuple[str, str | None]] = set()
        for page in pages:
            for e in page:
                reason = reject_reason(e, c)
                if reason:
                    rejected[reason] = rejected.get(reason, 0) + 1
                    continue
                key = (e.name, e.server)
                if key in seen:  # derselbe Spieler nur einmal
                    continue
                seen.add(key)
                hits.append(e)
                if len(hits) >= n:
                    return hits, rejected
        return hits, rejected

    hits: list[RankingEntry] = []
    rejected: dict[str, int] = {}
    for page_no in range(1, max_pages + 1):
        payload = fetch_page(page_no)
        pages.append(parse_rankings_page(payload, page_no))
        hits, rejected = scan(criteria)
        if len(hits) >= n or not payload.get("hasMorePages", False):
            break

    if len(hits) >= n:
        return Selection(hits, criteria, False, len(pages), sum(map(len, pages)), rejected)

    for c in steps[1:]:
        hits, rejected = scan(c)
        if len(hits) >= n:
            return Selection(hits, c, True, len(pages), sum(map(len, pages)), rejected)

    return Selection(hits, steps[-1], True, len(pages), sum(map(len, pages)), rejected)
