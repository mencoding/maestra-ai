"""Testes do profile_view com bloco de fontes externas."""
import json


def test_profile_view_includes_external_block(tmp_path, monkeypatch):
    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path / "config" / "maestra"))
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data" / "maestra"))
    monkeypatch.setenv("MAESTRA_STATE_DIR", str(tmp_path / "state" / "maestra"))
    (tmp_path / "config" / "maestra").mkdir(parents=True)
    (tmp_path / "data" / "maestra").mkdir(parents=True)
    (tmp_path / "config" / "maestra" / "config.json").write_text(json.dumps({
        "client_id": "x", "client_secret": "y", "redirect_uri": "z",
        "external_sources_enabled": True,
    }))
    (tmp_path / "data" / "maestra" / "external_cache.json").write_text(json.dumps({
        "version": 1,
        "tracks": {
            "spotify:track:a": {
                "uri": "spotify:track:a",
                "musicbrainz": {"mbid": "r1", "genres": ["rock"], "tags": []},
                "sources": ["musicbrainz"],
            },
            "spotify:track:b": {
                "uri": "spotify:track:b",
                "musicbrainz": {"mbid": "r2", "genres": [], "tags": []},
                "sources": ["musicbrainz"],
            },
        },
    }))

    from maestra_ai.core.profile_view import build_profile_view
    view = build_profile_view()

    assert view["external"]["enabled"] is True
    assert view["external"]["musicbrainz"]["tracks_with_genres"] == 1
    assert view["external"]["musicbrainz"]["tracks_total"] == 2


def test_profile_view_external_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path / "config" / "maestra"))
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data" / "maestra"))
    monkeypatch.setenv("MAESTRA_STATE_DIR", str(tmp_path / "state" / "maestra"))
    (tmp_path / "config" / "maestra").mkdir(parents=True)
    (tmp_path / "config" / "maestra" / "config.json").write_text(json.dumps({
        "client_id": "x", "client_secret": "y", "redirect_uri": "z",
    }))

    from maestra_ai.core.profile_view import build_profile_view
    view = build_profile_view()
    assert view["external"] == {"enabled": False}
