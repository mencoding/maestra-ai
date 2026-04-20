"""Valida migração do config.external_sources flat → nested."""
from __future__ import annotations

from maestra_ai.core import config as cfg_module


def test_migrate_flat_true_to_nested():
    cfg = {"external_sources_enabled": True}
    migrated = cfg_module.migrate_external_sources(cfg)
    assert migrated["external_sources"]["musicbrainz"]["enabled"] is True
    assert migrated["external_sources"]["lastfm"]["enabled"] is False
    assert migrated["external_sources"]["lastfm"]["api_key"] is None
    assert migrated["external_sources"]["getsongbpm"]["enabled"] is False
    assert migrated["external_sources"]["getsongbpm"]["api_key"] is None
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


def test_migrate_nested_already_present_is_noop():
    cfg = {
        "external_sources": {
            "musicbrainz": {"enabled": True},
            "lastfm": {"enabled": True, "api_key": "abc"},
            "getsongbpm": {"enabled": False, "api_key": None},
        }
    }
    migrated = cfg_module.migrate_external_sources(cfg)
    assert migrated["external_sources"]["lastfm"]["api_key"] == "abc"


def test_source_enabled_helper_reads_nested():
    cfg = {"external_sources": {"musicbrainz": {"enabled": True}, "lastfm": {"enabled": False, "api_key": None}, "getsongbpm": {"enabled": False, "api_key": None}}}
    assert cfg_module.source_enabled(cfg, "musicbrainz") is True
    assert cfg_module.source_enabled(cfg, "lastfm") is False


def test_source_enabled_helper_reads_flat_legacy():
    """Helpers precisam funcionar antes da migração também (read-side)."""
    cfg = {"external_sources_enabled": True}
    assert cfg_module.source_enabled(cfg, "musicbrainz") is True
    assert cfg_module.source_enabled(cfg, "lastfm") is False


def test_any_source_enabled_helper():
    cfg = {"external_sources": {"musicbrainz": {"enabled": False}, "lastfm": {"enabled": True, "api_key": "k"}, "getsongbpm": {"enabled": False, "api_key": None}}}
    assert cfg_module.any_source_enabled(cfg) is True

    cfg2 = {"external_sources": {"musicbrainz": {"enabled": False}, "lastfm": {"enabled": False, "api_key": None}, "getsongbpm": {"enabled": False, "api_key": None}}}
    assert cfg_module.any_source_enabled(cfg2) is False
