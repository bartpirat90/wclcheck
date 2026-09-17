from __future__ import annotations

import os
from pathlib import Path

import pytest

from wclcheck.cache import DiskCache
from wclcheck.config import CONFIG_PATH, ConfigError, Settings, load_settings


def _live_settings() -> Settings | None:
    try:
        if os.environ.get("WCL_CLIENT_ID") and os.environ.get("WCL_CLIENT_SECRET"):
            return load_settings(Path("/nonexistent"), os.environ)
        if CONFIG_PATH.exists():
            return load_settings(CONFIG_PATH, {})
    except ConfigError:
        return None
    return None


def pytest_collection_modifyitems(config, items):
    if _live_settings() is not None:
        return
    skip = pytest.mark.skip(reason="keine WCL-Zugangsdaten (Config oder Env)")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def settings() -> Settings:
    return Settings(client_id="id", client_secret="secret")


@pytest.fixture
def cache(tmp_path: Path) -> DiskCache:
    return DiskCache(root=tmp_path / "cache")


@pytest.fixture(scope="session")
def live_settings() -> Settings:
    s = _live_settings()
    if s is None:
        pytest.skip("keine WCL-Zugangsdaten")
    return s


@pytest.fixture(scope="session")
def live_client(live_settings: Settings):
    """Echter Client mit dem normalen Disk-Cache, damit Live-Tests wenig Punkte kosten."""
    from wclcheck.client import WCLClient

    return WCLClient(live_settings, DiskCache())
