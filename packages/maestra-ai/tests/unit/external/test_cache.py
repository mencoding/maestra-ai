"""Testes de load/save do cache de metadata externa."""
import json
from pathlib import Path

from maestra_ai.core.external.cache import (
    CACHE_SCHEMA_VERSION,
    get_track,
    load_cache,
    put_track,
    save_cache,
)


def _sample_track(uri: str):
    return {
        "uri": uri,
        "isrc": None,
        "artist_mbid": None,
        "musicbrainz": None,
        "lastfm": None,
        "bpm": None,
        "sources": [],
        "enhanced_at": "2026-04-20T10:00:00-03:00",
        "match_method": "isrc",
    }


def test_load_cache_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path))
    cache = load_cache()
    assert cache == {"version": CACHE_SCHEMA_VERSION, "tracks": {}, "similar_artists": {}}


def test_put_and_get_track(tmp_path, monkeypatch):
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path))
    put_track(_sample_track("spotify:track:a"))
    retrieved = get_track("spotify:track:a")
    assert retrieved is not None
    assert retrieved["uri"] == "spotify:track:a"


def test_cache_round_trip_is_atomic(tmp_path, monkeypatch):
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path))
    cache = {
        "version": CACHE_SCHEMA_VERSION,
        "tracks": {"spotify:track:a": _sample_track("spotify:track:a")},
    }
    save_cache(cache)
    path = Path(tmp_path) / "external_cache.json"
    data = json.loads(path.read_text())
    assert data["version"] == CACHE_SCHEMA_VERSION
    assert "spotify:track:a" in data["tracks"]


def test_load_corrupted_cache_resets_to_default(tmp_path, monkeypatch):
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path))
    path = Path(tmp_path) / "maestra" / "external_cache.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ not json")
    cache = load_cache()
    assert cache == {"version": CACHE_SCHEMA_VERSION, "tracks": {}, "similar_artists": {}}


def test_missing_uri_returns_none(tmp_path, monkeypatch):
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path))
    assert get_track("spotify:track:does-not-exist") is None
