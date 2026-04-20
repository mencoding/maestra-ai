"""Valida migração do config.external_sources flat → nested (v0.10.4+).

v0.10.4: api_key sai de config.json e vai para keyring. migrate_external_sources
migra automaticamente keys em plaintext para o keyring (best-effort) e remove
o campo do JSON.
"""
from __future__ import annotations

from unittest.mock import patch

from maestra_ai.core import config as cfg_module


def test_migrate_flat_true_to_nested():
    cfg = {"external_sources_enabled": True}
    migrated = cfg_module.migrate_external_sources(cfg)
    assert migrated["external_sources"]["musicbrainz"]["enabled"] is True
    assert migrated["external_sources"]["lastfm"]["enabled"] is False
    # v0.10.4: api_key não existe mais no dict nested
    assert "api_key" not in migrated["external_sources"]["lastfm"]
    assert migrated["external_sources"]["getsongbpm"]["enabled"] is False
    assert "api_key" not in migrated["external_sources"]["getsongbpm"]
    assert "external_sources_enabled" not in migrated


def test_migrate_flat_false_to_nested():
    cfg = {"external_sources_enabled": False}
    migrated = cfg_module.migrate_external_sources(cfg)
    assert migrated["external_sources"]["musicbrainz"]["enabled"] is False


def test_migrate_missing_key_initializes_defaults():
    cfg = {}
    migrated = cfg_module.migrate_external_sources(cfg)
    assert migrated["external_sources"]["musicbrainz"]["enabled"] is False
    assert migrated["external_sources"]["lastfm"]["enabled"] is False


def test_migrate_nested_plaintext_key_moves_to_keyring():
    """api_key plaintext em config é migrada para keyring e removida do dict."""
    cfg = {
        "external_sources": {
            "musicbrainz": {"enabled": True},
            "lastfm": {"enabled": True, "api_key": "abc123"},
            "getsongbpm": {"enabled": False, "api_key": None},
        }
    }
    with patch.object(cfg_module, "set_source_key") as mock_set:
        migrated = cfg_module.migrate_external_sources(cfg)
    mock_set.assert_called_once_with("lastfm", "abc123")
    assert "api_key" not in migrated["external_sources"]["lastfm"]
    assert migrated["external_sources"]["lastfm"]["enabled"] is True


def test_migrate_nested_no_plaintext_key_is_noop():
    """Sem api_key no dict, migração é noop (keyring não é chamado)."""
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


def test_migrate_nested_keyring_failure_keeps_plaintext():
    """Se keyring falhar, api_key permanece em config (graceful degradation)."""
    cfg = {
        "external_sources": {
            "musicbrainz": {"enabled": True},
            "lastfm": {"enabled": True, "api_key": "secretkey"},
            "getsongbpm": {"enabled": False},
        }
    }
    with patch.object(cfg_module, "set_source_key", side_effect=RuntimeError("keyring indisponível")):
        migrated = cfg_module.migrate_external_sources(cfg)
    # Fallback: api_key fica em config
    assert migrated["external_sources"]["lastfm"]["api_key"] == "secretkey"


def test_source_enabled_helper_reads_nested():
    cfg = {"external_sources": {"musicbrainz": {"enabled": True}, "lastfm": {"enabled": False}, "getsongbpm": {"enabled": False}}}
    assert cfg_module.source_enabled(cfg, "musicbrainz") is True
    assert cfg_module.source_enabled(cfg, "lastfm") is False


def test_source_enabled_helper_reads_flat_legacy():
    """Helpers precisam funcionar antes da migração também (read-side)."""
    cfg = {"external_sources_enabled": True}
    assert cfg_module.source_enabled(cfg, "musicbrainz") is True
    assert cfg_module.source_enabled(cfg, "lastfm") is False


def test_any_source_enabled_helper():
    cfg = {"external_sources": {"musicbrainz": {"enabled": False}, "lastfm": {"enabled": True}, "getsongbpm": {"enabled": False}}}
    assert cfg_module.any_source_enabled(cfg) is True

    cfg2 = {"external_sources": {"musicbrainz": {"enabled": False}, "lastfm": {"enabled": False}, "getsongbpm": {"enabled": False}}}
    assert cfg_module.any_source_enabled(cfg2) is False
