"""Testes da atribuição em curate quando fontes externas ativas."""
import json


def test_attribution_printed_when_external_enabled(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path / "config" / "maestra"))
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data" / "maestra"))
    (tmp_path / "config" / "maestra").mkdir(parents=True)
    (tmp_path / "data" / "maestra").mkdir(parents=True)
    (tmp_path / "config" / "maestra" / "config.json").write_text(json.dumps({
        "client_id": "x", "client_secret": "y", "redirect_uri": "z",
        "external_sources_enabled": True,
    }))
    (tmp_path / "data" / "maestra" / "external_cache.json").write_text(json.dumps({
        "version": 1, "tracks": {"spotify:track:a": {"uri": "spotify:track:a", "sources": ["musicbrainz"]}},
    }))

    from maestra_ai.cli.curate import _maybe_print_external_attribution
    _maybe_print_external_attribution()
    out = capsys.readouterr().out
    assert "MusicBrainz" in out
    assert "Fontes usadas nesta curadoria" in out


def test_attribution_silent_when_disabled(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path / "config" / "maestra"))
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data" / "maestra"))
    (tmp_path / "config" / "maestra").mkdir(parents=True)
    (tmp_path / "config" / "maestra" / "config.json").write_text(json.dumps({
        "client_id": "x", "client_secret": "y", "redirect_uri": "z",
        "external_sources_enabled": False,
    }))
    from maestra_ai.cli.curate import _maybe_print_external_attribution
    _maybe_print_external_attribution()
    out = capsys.readouterr().out
    assert "MusicBrainz" not in out


def test_attribution_silent_when_enabled_but_cache_empty(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path / "config" / "maestra"))
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data" / "maestra"))
    (tmp_path / "config" / "maestra").mkdir(parents=True)
    (tmp_path / "config" / "maestra" / "config.json").write_text(json.dumps({
        "client_id": "x", "client_secret": "y", "redirect_uri": "z",
        "external_sources_enabled": True,
    }))
    from maestra_ai.cli.curate import _maybe_print_external_attribution
    _maybe_print_external_attribution()
    out = capsys.readouterr().out
    assert "Fontes usadas" not in out
