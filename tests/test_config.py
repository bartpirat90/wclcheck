from pathlib import Path

import pytest

from wclcheck.config import ConfigError, load_settings


def test_creates_template_and_aborts(tmp_path: Path):
    path = tmp_path / "cfg" / "config.toml"
    with pytest.raises(ConfigError, match="Vorlage angelegt"):
        load_settings(path, env={})
    assert path.exists()
    assert "[wcl]" in path.read_text("utf-8")


def test_empty_template_reports_missing(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text('[wcl]\nclient_id = ""\nclient_secret = ""\n', "utf-8")
    with pytest.raises(ConfigError, match="fehlen"):
        load_settings(path, env={})


def test_reads_toml(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text(
        '[wcl]\nclient_id = "abc"\nclient_secret = "xyz"\n'
        '[defaults]\nplayer = "Foo"\nregion = "us"\n',
        "utf-8",
    )
    s = load_settings(path, env={})
    assert (s.client_id, s.client_secret, s.player, s.region) == ("abc", "xyz", "Foo", "US")


def test_env_overrides_toml(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text('[wcl]\nclient_id = "abc"\nclient_secret = "xyz"\n', "utf-8")
    s = load_settings(path, env={"WCL_CLIENT_ID": "e1", "WCL_CLIENT_SECRET": "e2"})
    assert (s.client_id, s.client_secret) == ("e1", "e2")
    assert s.player == "Schauderbart"


def test_env_without_file(tmp_path: Path):
    path = tmp_path / "missing.toml"
    s = load_settings(path, env={"WCL_CLIENT_ID": "e1", "WCL_CLIENT_SECRET": "e2"})
    assert s.client_id == "e1"
    assert not path.exists()
