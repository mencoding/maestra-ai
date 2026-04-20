"""Testes dos helpers keyring em core/config.py (v0.10.4).

Cobre get_source_key, set_source_key, delete_source_key e o comportamento
de migrate_external_sources com api_key plaintext.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from maestra_ai.core import config as cfg_module

# ---------------------------------------------------------------------------
# get_source_key
# ---------------------------------------------------------------------------

def test_get_source_key_lastfm_returns_value(monkeypatch):
    mock_kr = MagicMock()
    mock_kr.get_password.return_value = "minha-api-key"
    monkeypatch.setattr(cfg_module, "keyring", mock_kr)

    result = cfg_module.get_source_key("lastfm")

    mock_kr.get_password.assert_called_once_with("maestra-ai", "lastfm-api-key")
    assert result == "minha-api-key"


def test_get_source_key_getsongbpm_returns_value(monkeypatch):
    mock_kr = MagicMock()
    mock_kr.get_password.return_value = "gsb-key"
    monkeypatch.setattr(cfg_module, "keyring", mock_kr)

    result = cfg_module.get_source_key("getsongbpm")

    mock_kr.get_password.assert_called_once_with("maestra-ai", "getsongbpm-api-key")
    assert result == "gsb-key"


def test_get_source_key_unknown_source_returns_none(monkeypatch):
    mock_kr = MagicMock()
    monkeypatch.setattr(cfg_module, "keyring", mock_kr)

    result = cfg_module.get_source_key("unknown_source")

    mock_kr.get_password.assert_not_called()
    assert result is None


def test_get_source_key_keyring_exception_returns_none(monkeypatch):
    mock_kr = MagicMock()
    mock_kr.get_password.side_effect = RuntimeError("backend falhou")
    monkeypatch.setattr(cfg_module, "keyring", mock_kr)

    result = cfg_module.get_source_key("lastfm")

    assert result is None


def test_get_source_key_keyring_none_returns_none(monkeypatch):
    """Sem módulo keyring disponível, retorna None sem levantar."""
    monkeypatch.setattr(cfg_module, "keyring", None)
    assert cfg_module.get_source_key("lastfm") is None


def test_get_source_key_not_set_returns_none(monkeypatch):
    mock_kr = MagicMock()
    mock_kr.get_password.return_value = None
    monkeypatch.setattr(cfg_module, "keyring", mock_kr)

    assert cfg_module.get_source_key("lastfm") is None


# ---------------------------------------------------------------------------
# set_source_key
# ---------------------------------------------------------------------------

def test_set_source_key_lastfm(monkeypatch):
    mock_kr = MagicMock()
    monkeypatch.setattr(cfg_module, "keyring", mock_kr)

    cfg_module.set_source_key("lastfm", "minha-key")

    mock_kr.set_password.assert_called_once_with("maestra-ai", "lastfm-api-key", "minha-key")


def test_set_source_key_getsongbpm(monkeypatch):
    mock_kr = MagicMock()
    monkeypatch.setattr(cfg_module, "keyring", mock_kr)

    cfg_module.set_source_key("getsongbpm", "gsb-key")

    mock_kr.set_password.assert_called_once_with("maestra-ai", "getsongbpm-api-key", "gsb-key")


def test_set_source_key_unknown_raises_value_error(monkeypatch):
    mock_kr = MagicMock()
    monkeypatch.setattr(cfg_module, "keyring", mock_kr)

    with pytest.raises(ValueError, match="source sem keyring"):
        cfg_module.set_source_key("musicbrainz", "key")


def test_set_source_key_keyring_none_raises(monkeypatch):
    monkeypatch.setattr(cfg_module, "keyring", None)

    with pytest.raises(RuntimeError, match="keyring não disponível"):
        cfg_module.set_source_key("lastfm", "key")


# ---------------------------------------------------------------------------
# delete_source_key
# ---------------------------------------------------------------------------

def test_delete_source_key_lastfm(monkeypatch):
    mock_kr = MagicMock()
    monkeypatch.setattr(cfg_module, "keyring", mock_kr)

    cfg_module.delete_source_key("lastfm")

    mock_kr.delete_password.assert_called_once_with("maestra-ai", "lastfm-api-key")


def test_delete_source_key_idempotent_on_exception(monkeypatch):
    """delete_source_key não levanta mesmo se keyring lançar."""
    mock_kr = MagicMock()
    mock_kr.delete_password.side_effect = Exception("PasswordDeleteError")
    monkeypatch.setattr(cfg_module, "keyring", mock_kr)

    # Não deve levantar
    cfg_module.delete_source_key("lastfm")


def test_delete_source_key_unknown_source_noop(monkeypatch):
    """Source desconhecida não chama keyring."""
    mock_kr = MagicMock()
    monkeypatch.setattr(cfg_module, "keyring", mock_kr)

    cfg_module.delete_source_key("musicbrainz")

    mock_kr.delete_password.assert_not_called()


def test_delete_source_key_keyring_none_noop(monkeypatch):
    monkeypatch.setattr(cfg_module, "keyring", None)
    # Não deve levantar
    cfg_module.delete_source_key("lastfm")


# ---------------------------------------------------------------------------
# migrate_external_sources — integração com keyring
# ---------------------------------------------------------------------------

def test_migrate_moves_lastfm_plaintext_to_keyring(monkeypatch):
    """migrate_external_sources chama set_source_key e remove api_key do dict."""
    mock_kr = MagicMock()
    monkeypatch.setattr(cfg_module, "keyring", mock_kr)

    cfg = {
        "external_sources": {
            "musicbrainz": {"enabled": True},
            "lastfm": {"enabled": True, "api_key": "plain-key"},
            "getsongbpm": {"enabled": False},
        }
    }
    migrated = cfg_module.migrate_external_sources(cfg)

    mock_kr.set_password.assert_called_once_with("maestra-ai", "lastfm-api-key", "plain-key")
    assert "api_key" not in migrated["external_sources"]["lastfm"]


def test_migrate_moves_getsongbpm_plaintext_to_keyring(monkeypatch):
    mock_kr = MagicMock()
    monkeypatch.setattr(cfg_module, "keyring", mock_kr)

    cfg = {
        "external_sources": {
            "musicbrainz": {"enabled": False},
            "lastfm": {"enabled": False},
            "getsongbpm": {"enabled": True, "api_key": "gsb-plain"},
        }
    }
    migrated = cfg_module.migrate_external_sources(cfg)

    mock_kr.set_password.assert_called_once_with("maestra-ai", "getsongbpm-api-key", "gsb-plain")
    assert "api_key" not in migrated["external_sources"]["getsongbpm"]


def test_migrate_both_keys_plaintext(monkeypatch):
    mock_kr = MagicMock()
    monkeypatch.setattr(cfg_module, "keyring", mock_kr)

    cfg = {
        "external_sources": {
            "musicbrainz": {"enabled": False},
            "lastfm": {"enabled": True, "api_key": "lf-key"},
            "getsongbpm": {"enabled": True, "api_key": "gsb-key"},
        }
    }
    cfg_module.migrate_external_sources(cfg)

    calls = {c.args[1]: c.args[2] for c in mock_kr.set_password.call_args_list}
    assert calls["lastfm-api-key"] == "lf-key"
    assert calls["getsongbpm-api-key"] == "gsb-key"


def test_migrate_graceful_when_keyring_unavailable(monkeypatch):
    """Se keyring indisponível, api_key fica em config (fallback graceful)."""
    monkeypatch.setattr(cfg_module, "keyring", None)

    cfg = {
        "external_sources": {
            "musicbrainz": {"enabled": False},
            "lastfm": {"enabled": True, "api_key": "stays-here"},
            "getsongbpm": {"enabled": False},
        }
    }
    migrated = cfg_module.migrate_external_sources(cfg)
    # Fallback: key fica em config
    assert migrated["external_sources"]["lastfm"]["api_key"] == "stays-here"


def test_migrate_idempotent_when_no_plaintext():
    """migrate_external_sources sem api_key não chama keyring."""
    cfg = {
        "external_sources": {
            "musicbrainz": {"enabled": True},
            "lastfm": {"enabled": True},
            "getsongbpm": {"enabled": False},
        }
    }
    with patch.object(cfg_module, "set_source_key") as mock_set:
        migrated = cfg_module.migrate_external_sources(cfg)

    mock_set.assert_not_called()
    assert "api_key" not in migrated["external_sources"]["lastfm"]
