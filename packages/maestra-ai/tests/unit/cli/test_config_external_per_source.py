"""CLI: config external set-key/clear-key/enable/disable por source."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest


def _make_args(**kwargs):
    args = MagicMock()
    for k, v in kwargs.items():
        setattr(args, k, v)
    args.human = False
    return args


@pytest.fixture
def fake_cfg_path(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"external_sources": {"musicbrainz": {"enabled": True}, "lastfm": {"enabled": False, "api_key": None}, "getsongbpm": {"enabled": False, "api_key": None}}}), encoding="utf-8")
    from maestra_ai.core import storage
    monkeypatch.setattr(storage, "config_path", lambda: path)
    return path


def test_set_key_lastfm_writes_key(fake_cfg_path, capsys):
    from maestra_ai.cli import config as cli_cfg
    args = _make_args(source="lastfm", key="a" * 32)
    cli_cfg.cmd_config_external_set_key(args)
    data = json.loads(fake_cfg_path.read_text())
    assert data["external_sources"]["lastfm"]["api_key"] == "a" * 32
    assert data["external_sources"]["lastfm"]["enabled"] is True


def test_clear_key_lastfm_nullifies_and_disables(fake_cfg_path):
    fake_cfg_path.write_text(json.dumps({"external_sources": {"musicbrainz": {"enabled": True}, "lastfm": {"enabled": True, "api_key": "a"*32}, "getsongbpm": {"enabled": False, "api_key": None}}}), encoding="utf-8")
    from maestra_ai.cli import config as cli_cfg
    args = _make_args(source="lastfm")
    cli_cfg.cmd_config_external_clear_key(args)
    data = json.loads(fake_cfg_path.read_text())
    assert data["external_sources"]["lastfm"]["api_key"] is None
    assert data["external_sources"]["lastfm"]["enabled"] is False


def test_enable_without_key_fails_gracefully(fake_cfg_path, capsys):
    from maestra_ai.cli import config as cli_cfg
    args = _make_args(source="lastfm")
    cli_cfg.cmd_config_external_enable_source(args)
    data = json.loads(fake_cfg_path.read_text())
    # sem key configurada, enable não deve ativar (ou deve printar erro)
    assert data["external_sources"]["lastfm"]["enabled"] is False


def test_disable_lastfm_turns_off_keeping_key(fake_cfg_path):
    fake_cfg_path.write_text(json.dumps({"external_sources": {"musicbrainz": {"enabled": True}, "lastfm": {"enabled": True, "api_key": "a"*32}, "getsongbpm": {"enabled": False, "api_key": None}}}), encoding="utf-8")
    from maestra_ai.cli import config as cli_cfg
    args = _make_args(source="lastfm")
    cli_cfg.cmd_config_external_disable_source(args)
    data = json.loads(fake_cfg_path.read_text())
    assert data["external_sources"]["lastfm"]["enabled"] is False
    assert data["external_sources"]["lastfm"]["api_key"] == "a" * 32
