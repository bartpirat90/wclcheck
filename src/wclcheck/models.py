"""Datenmodelle für Report, Fights und Actors (WCL API v2)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

DIFFICULTY_NAMES = {1: "LFR", 2: "Flex", 3: "Normal", 4: "Heroic", 5: "Mythic"}


class Actor(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    name: str
    type: str
    subType: str | None = None
    petOwner: int | None = None
    server: str | None = None

    @property
    def is_player(self) -> bool:
        return self.type == "Player"

    @property
    def is_pet(self) -> bool:
        return self.type == "Pet"


class Ability(BaseModel):
    model_config = ConfigDict(extra="ignore")

    gameID: int
    name: str | None = None
    type: str | None = None
    icon: str | None = None


class Fight(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    encounterID: int
    name: str
    kill: bool | None = None
    difficulty: int | None = None
    startTime: int
    endTime: int
    averageItemLevel: float | None = None
    size: int | None = None
    inProgress: bool | None = None
    friendlyPlayers: list[int] = Field(default_factory=list)

    @property
    def duration_ms(self) -> int:
        return self.endTime - self.startTime

    @property
    def duration_s(self) -> float:
        return self.duration_ms / 1000.0

    @property
    def is_complete(self) -> bool:
        """Abgeschlossen = nicht mehr laufend. Nur solche Fights dauerhaft cachen."""
        return not self.inProgress

    @property
    def difficulty_name(self) -> str:
        return DIFFICULTY_NAMES.get(self.difficulty or 0, str(self.difficulty))


class Zone(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    name: str


class Report(BaseModel):
    model_config = ConfigDict(extra="ignore")

    code: str
    title: str | None = None
    startTime: int
    endTime: int
    region: str | None = None
    zone: Zone | None = None
    fights: list[Fight] = Field(default_factory=list)
    actors: list[Actor] = Field(default_factory=list)

    @classmethod
    def from_graphql(cls, code: str, data: dict) -> Report:
        region = (data.get("region") or {}).get("slug")
        master = data.get("masterData") or {}
        return cls(
            code=code,
            title=data.get("title"),
            startTime=data["startTime"],
            endTime=data["endTime"],
            region=region.upper() if region else None,
            zone=data.get("zone"),
            fights=data.get("fights") or [],
            actors=master.get("actors") or [],
        )

    def actor(self, actor_id: int) -> Actor | None:
        return next((a for a in self.actors if a.id == actor_id), None)

    def find_player(self, name: str) -> Actor | None:
        """Spieler per Name (case-insensitiv). Eindeutigkeit wird nicht garantiert."""
        wanted = name.casefold()
        for a in self.actors:
            if a.is_player and a.name.casefold() == wanted:
                return a
        return None

    def pets_of(self, owner_id: int) -> list[Actor]:
        return [a for a in self.actors if a.is_pet and a.petOwner == owner_id]

    def fight(self, fight_id: int) -> Fight | None:
        return next((f for f in self.fights if f.id == fight_id), None)

    def kills(self) -> list[Fight]:
        return [f for f in self.fights if f.kill]

    def url(self, fight_id: int | None = None) -> str:
        base = f"https://www.warcraftlogs.com/reports/{self.code}"
        return f"{base}#fight={fight_id}" if fight_id is not None else base
