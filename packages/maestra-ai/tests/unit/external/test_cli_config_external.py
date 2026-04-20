"""Testes do subgrupo `maestra config external`."""
import json
from pathlib import Path

import pytest


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    # data_dir path: env + /maestra suffix auto (see storage.py convention)
    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path / "config" / "maestra"))
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data" / "maestra"))
    yield tmp_path


def _call(fn_name, **kwargs):
    from maestra_ai.cli import config
    fn = getattr(config, fn_name)
    class A:
        pass
    a = A()
    for k, v in kwargs.items():
        setattr(a, k, v)
    fn(a)


def test_external_status_default(isolated, monkeypatch, capsys):
    # Mockar get_source_key para isolar de keyring real do sistema
    from maestra_ai.cli import config as cli_cfg
    monkeypatch.setattr(cli_cfg, "get_source_key", lambda source: None)
    _call("cmd_config_external_status", human=False)
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["enabled"] is False
    # v0.10.4: status retorna per_source com has_key para sources keyed
    assert "per_source" in data
    assert "musicbrainz" in data["per_source"]
    assert "lastfm" in data["per_source"]
    assert "has_key" in data["per_source"]["lastfm"]
    assert data["per_source"]["lastfm"]["has_key"] is False


def test_external_enable_persists(isolated, capsys):
    _call("cmd_config_external_enable", human=False)
    cfg_path = Path(isolated) / "config" / "maestra" / "config.json"
    data = json.loads(cfg_path.read_text())
    assert data["external_sources"]["musicbrainz"]["enabled"] is True


def test_external_disable_persists(isolated, capsys):
    _call("cmd_config_external_enable", human=False)
    _call("cmd_config_external_disable", human=False)
    cfg_path = Path(isolated) / "config" / "maestra" / "config.json"
    data = json.loads(cfg_path.read_text())
    assert data["external_sources"]["musicbrainz"]["enabled"] is False
