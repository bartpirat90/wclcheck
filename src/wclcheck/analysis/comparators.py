"""Vergleichsspieler: Rankings holen, auswählen und deren Fight-Daten laden."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ..client import WCLClient, WCLError
from ..models import Actor, Fight, Report
from .loader import FightData, load_fight_data
from .rankings import Criteria, RankingEntry, Selection, select_comparators

log = logging.getLogger("wclcheck.comparators")

SPEC_RANKING_NAMES = {"Demonology": "Demonology", "Destruction": "Destruction"}


@dataclass
class Comparator:
    entry: RankingEntry
    report: Report
    fight: Fight
    actor: Actor
    data: FightData


def find_comparators(
    client: WCLClient,
    *,
    encounter_id: int,
    spec: str,
    difficulty: int,
    criteria: Criteria,
    n: int = 3,
    region: str | None = None,
) -> Selection:
    def fetch(page: int) -> dict:
        return client.character_rankings(
            encounter_id,
            class_name="Warlock",
            spec_name=SPEC_RANKING_NAMES.get(spec, spec),
            difficulty=difficulty,
            page=page,
            region=region,
        )

    return select_comparators(fetch, criteria, n=n)


def _resolve_actor(report: Report, fight: Fight, entry: RankingEntry) -> Actor | None:
    """Spieler im Vergleichsreport finden: Name + Server, im Fight anwesend, Warlock."""
    wanted = entry.name.casefold()
    candidates = [
        a
        for a in report.actors
        if a.is_player and a.name.casefold() == wanted and a.subType == "Warlock"
    ]
    if entry.server:
        srv = entry.server.replace(" ", "").replace("'", "").casefold()
        exact = [
            a for a in candidates
            if (a.server or "").replace(" ", "").replace("'", "").casefold() == srv
        ]
        candidates = exact or candidates
    present = [a for a in candidates if a.id in fight.friendlyPlayers] or candidates
    return present[0] if present else None


def load_comparator(client: WCLClient, entry: RankingEntry) -> Comparator | None:
    """Lädt Report, Fight und Spieler eines Ranking-Eintrags; None bei Problemen (geloggt)."""
    try:
        report = client.report(entry.report_code, live=False)
    except WCLError as exc:
        log.warning("Vergleichsreport %s nicht ladbar: %s", entry.report_code, exc)
        return None
    fight = report.fight(entry.fight_id)
    if fight is None:
        log.warning("Fight %s fehlt in %s", entry.fight_id, entry.report_code)
        return None
    actor = _resolve_actor(report, fight, entry)
    if actor is None:
        log.warning("Spieler %s nicht in %s gefunden", entry.name, entry.report_code)
        return None
    try:
        data = load_fight_data(client, report, fight, actor, with_damage_events=True)
    except WCLError as exc:
        log.warning("Daten für %s (%s) nicht ladbar: %s", entry.name, entry.report_code, exc)
        return None
    return Comparator(entry=entry, report=report, fight=fight, actor=actor, data=data)
