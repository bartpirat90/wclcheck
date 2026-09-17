"""Lädt alle Rohdaten eines (Report, Fight, Spieler)-Tripels in ein FightData-Objekt.

Punktekosten (gemessen, Referenz-Report): Casts ≈ 3, Buffs/Summons/Summary/DamageDone-Tabelle
je ≈ 1, DamageDone-Events ≈ 1,2. Die Tabelle ist für Gesamtschaden pro Fähigkeit günstiger
und wird bevorzugt; Damage-Events nur, wenn Zeitfenster gebraucht werden (Tyrant-Fenster).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..client import WCLClient
from ..models import Actor, Fight, Report


@dataclass
class FightData:
    report: Report
    fight: Fight
    actor: Actor
    ability_names: dict[int, str]
    pets: list[Actor]
    cast_events: list[dict[str, Any]]
    buff_events: list[dict[str, Any]]
    summon_events: list[dict[str, Any]]
    damage_table: list[dict[str, Any]]
    summary: dict[str, Any]
    damage_events: list[dict[str, Any]] | None = None
    parse_percent: float | None = None
    rank_meta: dict[str, Any] = field(default_factory=dict)

    @property
    def pet_ids(self) -> set[int]:
        return {p.id for p in self.pets}

    @property
    def total_damage(self) -> int:
        return int(sum(e.get("total", 0) for e in self.damage_table))

    def damage_of(self, *ability_ids: int) -> int:
        wanted = set(ability_ids)
        return int(sum(e.get("total", 0) for e in self.damage_table if e.get("guid") in wanted))

    @property
    def combatant_info(self) -> dict[str, Any]:
        return self.summary.get("combatantInfo") or {}

    @property
    def deaths(self) -> list[dict[str, Any]]:
        return [d for d in self.summary.get("deathEvents") or [] if d.get("id") == self.actor.id]


def _find_player_rank(rankings: dict[str, Any], fight_id: int, actor_name: str) -> dict[str, Any]:
    for entry in rankings.get("data") or []:
        if entry.get("fightID") != fight_id:
            continue
        for role in (entry.get("roles") or {}).values():
            for ch in role.get("characters") or []:
                if ch.get("name") == actor_name:
                    return ch
    return {}


def load_fight_data(
    client: WCLClient,
    report: Report,
    fight: Fight,
    actor: Actor,
    *,
    with_damage_events: bool = False,
    with_rankings: bool = True,
) -> FightData:
    code = report.code
    names = {a.gameID: a.name or "" for a in client.abilities(code)}
    data = FightData(
        report=report,
        fight=fight,
        actor=actor,
        ability_names=names,
        pets=report.pets_of(actor.id),
        cast_events=client.events(code, fight, "Casts", source_id=actor.id, include_resources=True),
        buff_events=client.events(code, fight, "Buffs", target_id=actor.id),
        summon_events=client.events(code, fight, "Summons", source_id=actor.id),
        damage_table=(
            client.table(code, fight, "DamageDone", source_id=actor.id, view_by="Ability")
            .get("entries", [])
        ),
        summary=client.table(code, fight, "Summary", source_id=actor.id),
    )
    if with_damage_events:
        data.damage_events = client.events(code, fight, "DamageDone", source_id=actor.id)
    if with_rankings:
        try:
            rank = _find_player_rank(client.report_rankings(code, fight), fight.id, actor.name)
        except Exception:  # Rankings sind optional; nie den Lauf abbrechen
            rank = {}
        data.rank_meta = rank
        data.parse_percent = rank.get("rankPercent")
    return data
