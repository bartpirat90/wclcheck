"""Konfiguration: Zugangsdaten aus ~/.config/wclcheck/config.toml oder Umgebungsvariablen."""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "wclcheck"
CONFIG_PATH = CONFIG_DIR / "config.toml"

TEMPLATE = """# wclcheck – Konfiguration
# Client-ID/Secret unter https://www.warcraftlogs.com/api/clients/ anlegen
# (Client-Typ: beliebig, kein Redirect nötig). Alternativ die Umgebungsvariablen
# WCL_CLIENT_ID / WCL_CLIENT_SECRET setzen; diese haben Vorrang.

[wcl]
client_id = ""
client_secret = ""

[defaults]
player = "Schauderbart"
region = "EU"
"""


class ConfigError(Exception):
    """Fehlende oder unvollständige Konfiguration."""


@dataclass(frozen=True)
class Settings:
    client_id: str
    client_secret: str
    player: str = "Schauderbart"
    region: str = "EU"


def load_settings(
    path: Path = CONFIG_PATH, env: Mapping[str, str] | None = None
) -> Settings:
    """Liest die Einstellungen. Legt beim ersten Start eine Vorlage an und bricht ab."""
    env = os.environ if env is None else env
    data: dict = {}
    if path.exists():
        try:
            data = tomllib.loads(path.read_text("utf-8"))
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"Konfiguration {path} ist kein gültiges TOML: {exc}") from exc

    wcl = data.get("wcl", {}) or {}
    client_id = env.get("WCL_CLIENT_ID") or str(wcl.get("client_id") or "")
    client_secret = env.get("WCL_CLIENT_SECRET") or str(wcl.get("client_secret") or "")

    if not client_id or not client_secret:
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(TEMPLATE, "utf-8")
            raise ConfigError(
                f"Keine Zugangsdaten gefunden. Vorlage angelegt: {path}\n"
                "Dort client_id und client_secret eintragen "
                "(oder WCL_CLIENT_ID / WCL_CLIENT_SECRET setzen) und erneut starten."
            )
        raise ConfigError(
            f"client_id / client_secret fehlen in {path} "
            "(oder WCL_CLIENT_ID / WCL_CLIENT_SECRET setzen)."
        )

    defaults = data.get("defaults", {}) or {}
    return Settings(
        client_id=client_id,
        client_secret=client_secret,
        player=str(defaults.get("player") or "Schauderbart"),
        region=str(defaults.get("region") or "EU").upper(),
    )
