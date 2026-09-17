"""Spec- und Hero-Talent-Erkennung pro Fight aus den Cast-IDs des Spielers."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .. import spells


@dataclass(frozen=True)
class SpecInfo:
    spec: str | None  # "Demonology" | "Destruction" | None
    hero: str | None  # "Diabolist" | "Hellcaller" | None

    @property
    def label(self) -> str:
        spec = {"Demonology": "Demo", "Destruction": "Destro"}.get(self.spec or "", "?")
        return f"{spec}/{self.hero or '?'}"

    @property
    def is_demo(self) -> bool:
        return self.spec == "Demonology"

    @property
    def is_destro(self) -> bool:
        return self.spec == "Destruction"


def detect_spec(ability_ids: Iterable[int]) -> SpecInfo:
    ids = set(ability_ids)
    spec: str | None = None
    if ids & spells.DEMO_MARKERS:
        spec = "Demonology"
    elif ids & spells.DESTRO_MARKERS:
        spec = "Destruction"

    hero: str | None = None
    if ids & spells.DIABOLIST_MARKERS:
        hero = "Diabolist"
    elif ids & spells.HELLCALLER_MARKERS:
        hero = "Hellcaller"
    return SpecInfo(spec=spec, hero=hero)
