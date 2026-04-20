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


def test_external_status_default(isolated, capsys):
    _call("cmd_config_external_status", human=False)
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["enabled"] is False
    assert data["musicbrainz"] == "available"


def test_external_enable_persists(isolated, capsys):
    _call("cmd_config_external_enable", human=False)
    cfg_path = Path(isolated) / "config" / "maestra" / "config.json"
    data = json.loads(cfg_path.read_text())
    assert data["external_sources_enabled"] is True


def test_external_disable_persists(isolated, capsys):
    _call("cmd_config_external_enable", human=False)
    _call("cmd_config_external_disable", human=False)
    cfg_path = Path(isolated) / "config" / "maestra" / "config.json"
    data = json.loads(cfg_path.read_text())
    assert data["external_sources_enabled"] is False
