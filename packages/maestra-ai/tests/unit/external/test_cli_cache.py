"""Testes do subcomando `maestra cache`."""
import json
from pathlib import Path

import pytest


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data" / "maestra"))
    monkeypatch.setenv("MAESTRA_STATE_DIR", str(tmp_path / "state"))
    yield tmp_path


def test_cache_refresh_all_clears_cache(isolated_env):
    data_dir = Path(isolated_env) / "data" / "maestra"
    data_dir.mkdir(parents=True, exist_ok=True)
    cache_file = data_dir / "external_cache.json"
    cache_file.write_text(json.dumps({
        "version": 1,
        "tracks": {"spotify:track:a": {"uri": "spotify:track:a"}},
    }))
    from maestra_ai.cli.cache import cmd_cache_refresh
    class A:
        source = None
        uri = None
        human = False
    cmd_cache_refresh(A())
    reloaded = json.loads(cache_file.read_text())
    assert reloaded["tracks"] == {}


def test_cache_refresh_by_uri(isolated_env):
    data_dir = Path(isolated_env) / "data" / "maestra"
    data_dir.mkdir(parents=True, exist_ok=True)
    cache_file = data_dir / "external_cache.json"
    cache_file.write_text(json.dumps({
        "version": 1,
        "tracks": {
            "spotify:track:a": {"uri": "spotify:track:a"},
            "spotify:track:b": {"uri": "spotify:track:b"},
        },
    }))
    from maestra_ai.cli.cache import cmd_cache_refresh
    class A:
        source = None
        uri = "spotify:track:a"
        human = False
    cmd_cache_refresh(A())
    reloaded = json.loads(cache_file.read_text())
    assert "spotify:track:a" not in reloaded["tracks"]
    assert "spotify:track:b" in reloaded["tracks"]
