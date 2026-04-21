"""CLI: config external set-key/clear-key/enable/disable por source.

v0.11.0: getsongbpm removido; reccobeats adicionado (sem key).
API keys vivem no keyring. Testes mockam keyring.get_password /
set_password / delete_password para isolar de backend real.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

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
    path.write_text(
        json.dumps({
            "external_sources": {
                "musicbrainz": {"enabled": True},
                "lastfm": {"enabled": False},
                "reccobeats": {"enabled": False},
            }
        }),
        encoding="utf-8",
    )
    from maestra_ai.core import storage
    monkeypatch.setattr(storage, "config_path", lambda: path)
    return path


def test_set_key_lastfm_writes_to_keyring(fake_cfg_path, capsys):
    """set-key grava no keyring e não persiste api_key no JSON."""
    from maestra_ai.cli import config as cli_cfg

    args = _make_args(source="lastfm", key="a" * 32)
    with patch("maestra_ai.cli.config.set_source_key") as mock_set:
        cli_cfg.cmd_config_external_set_key(args)

    mock_set.assert_called_once_with("lastfm", "a" * 32)
    data = json.loads(fake_cfg_path.read_text())
    assert "api_key" not in data["external_sources"]["lastfm"]
    assert data["external_sources"]["lastfm"]["enabled"] is True


def test_set_key_output_does_not_reveal_key(fake_cfg_path, capsys):
    """Saída do set-key não expõe o valor da key."""
    from maestra_ai.cli import config as cli_cfg

    args = _make_args(source="lastfm", key="supersecret")
    with patch("maestra_ai.cli.config.set_source_key"):
        cli_cfg.cmd_config_external_set_key(args)

    out = capsys.readouterr().out
    assert "supersecret" not in out
    data = json.loads(out)
    assert data["status"] == "set"
    assert data["enabled"] is True


def test_clear_key_calls_delete_and_disables(fake_cfg_path):
    """clear-key deleta do keyring e marca enabled=False."""
    fake_cfg_path.write_text(
        json.dumps({
            "external_sources": {
                "musicbrainz": {"enabled": True},
                "lastfm": {"enabled": True},
                "reccobeats": {"enabled": False},
            }
        }),
        encoding="utf-8",
    )
    from maestra_ai.cli import config as cli_cfg

    args = _make_args(source="lastfm")
    with patch("maestra_ai.cli.config.delete_source_key") as mock_del:
        cli_cfg.cmd_config_external_clear_key(args)

    mock_del.assert_called_once_with("lastfm")
    data = json.loads(fake_cfg_path.read_text())
    assert "api_key" not in data["external_sources"]["lastfm"]
    assert data["external_sources"]["lastfm"]["enabled"] is False


def test_enable_without_key_fails_gracefully(fake_cfg_path, capsys):
    """enable-source sem key no keyring retorna erro sem ativar."""
    from maestra_ai.cli import config as cli_cfg

    args = _make_args(source="lastfm")
    with patch("maestra_ai.cli.config.get_source_key", return_value=None):
        cli_cfg.cmd_config_external_enable_source(args)

    data = json.loads(fake_cfg_path.read_text())
    assert data["external_sources"]["lastfm"]["enabled"] is False


def test_enable_with_key_in_keyring_succeeds(fake_cfg_path, capsys):
    """enable-source com key no keyring ativa a source."""
    from maestra_ai.cli import config as cli_cfg

    args = _make_args(source="lastfm")
    with patch("maestra_ai.cli.config.get_source_key", return_value="mykey"):
        cli_cfg.cmd_config_external_enable_source(args)

    data = json.loads(fake_cfg_path.read_text())
    assert data["external_sources"]["lastfm"]["enabled"] is True


def test_enable_reccobeats_no_key_needed(fake_cfg_path, capsys):
    """enable-source reccobeats ativa sem precisar de API key."""
    from maestra_ai.cli import config as cli_cfg

    args = _make_args(source="reccobeats")
    cli_cfg.cmd_config_external_enable_source(args)

    data = json.loads(fake_cfg_path.read_text())
    assert data["external_sources"]["reccobeats"]["enabled"] is True


def test_disable_lastfm_turns_off(fake_cfg_path):
    """disable-source marca enabled=False; keyring não é tocado."""
    fake_cfg_path.write_text(
        json.dumps({
            "external_sources": {
                "musicbrainz": {"enabled": True},
                "lastfm": {"enabled": True},
                "reccobeats": {"enabled": False},
            }
        }),
        encoding="utf-8",
    )
    from maestra_ai.cli import config as cli_cfg

    args = _make_args(source="lastfm")
    cli_cfg.cmd_config_external_disable_source(args)
    data = json.loads(fake_cfg_path.read_text())
    assert data["external_sources"]["lastfm"]["enabled"] is False


def test_disable_reccobeats(fake_cfg_path):
    """disable-source reccobeats marca enabled=False."""
    fake_cfg_path.write_text(
        json.dumps({
            "external_sources": {
                "musicbrainz": {"enabled": True},
                "lastfm": {"enabled": False},
                "reccobeats": {"enabled": True},
            }
        }),
        encoding="utf-8",
    )
    from maestra_ai.cli import config as cli_cfg

    args = _make_args(source="reccobeats")
    cli_cfg.cmd_config_external_disable_source(args)
    data = json.loads(fake_cfg_path.read_text())
    assert data["external_sources"]["reccobeats"]["enabled"] is False
