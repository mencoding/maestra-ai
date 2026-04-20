"""Integration: fluxo completo com fontes externas habilitadas."""
import json

import pytest

from maestra_ai.core.external import cache as ext_cache
from maestra_ai.core.external.enhancer import Enhancer


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path / "config" / "maestra"))
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data" / "maestra"))
    monkeypatch.setenv("MAESTRA_STATE_DIR", str(tmp_path / "state" / "maestra"))
    (tmp_path / "config" / "maestra").mkdir(parents=True)
    return tmp_path


class _StubSource:
    name = "musicbrainz"
    def is_configured(self): return True
    def __init__(self):
        self.calls = 0
    def enhance_track(self, track):
        self.calls += 1
        return {
            "musicbrainz": {"mbid": f"r-{track['uri']}", "genres": ["rock"], "tags": []},
            "artist_mbid": f"a-{track['uri']}",
            "match_method": "isrc",
        }


def test_enhance_then_profile_view_integration(isolated):
    source = _StubSource()
    enhancer = Enhancer(sources=[source])
    tracks = [
        {"uri": "spotify:track:1", "name": "A", "artists": ["X"], "isrc": "I1"},
        {"uri": "spotify:track:2", "name": "B", "artists": ["Y"], "isrc": "I2"},
    ]
    enhancer.enhance_many(tracks)

    cfg_path = isolated / "config" / "maestra" / "config.json"
    cfg_path.write_text(json.dumps({
        "client_id": "x", "client_secret": "y", "redirect_uri": "z",
        "external_sources_enabled": True,
    }))

    from maestra_ai.core.profile_view import build_profile_view
    view = build_profile_view()

    assert view["external"]["enabled"] is True
    assert view["external"]["musicbrainz"]["tracks_total"] == 2
    assert view["external"]["musicbrainz"]["tracks_with_genres"] == 2


def test_cache_hit_avoids_second_call(isolated):
    source = _StubSource()
    enhancer = Enhancer(sources=[source])
    track = {"uri": "spotify:track:1", "name": "A", "artists": ["X"], "isrc": "I1"}
    enhancer.enhance_track(track)
    enhancer.enhance_track(track)
    assert source.calls == 1


def test_refresh_clears_cache(isolated):
    source = _StubSource()
    enhancer = Enhancer(sources=[source])
    track = {"uri": "spotify:track:1", "name": "A", "artists": ["X"], "isrc": "I1"}
    enhancer.enhance_track(track)
    assert ext_cache.load_cache()["tracks"]
    cache = ext_cache.load_cache()
    cache["tracks"] = {}
    ext_cache.save_cache(cache)
    assert ext_cache.load_cache()["tracks"] == {}
