"""Testes do Enhancer — orquestração de fontes + cache."""
from maestra_ai.core.external.enhancer import Enhancer


class FakeSource:
    def __init__(self, name: str, result: dict | None, configured: bool = True):
        self.name = name
        self._result = result
        self._configured = configured
        self.call_count = 0

    def is_configured(self):
        return self._configured

    def enhance_track(self, track):
        self.call_count += 1
        return self._result


def _track():
    return {
        "uri": "spotify:track:sample",
        "name": "Sample",
        "artists": ["Artist"],
        "isrc": "USABC0000001",
    }


def test_enhance_track_with_single_source(tmp_path, monkeypatch):
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path))
    fake = FakeSource("musicbrainz", {
        "musicbrainz": {"mbid": "r1", "genres": ["rock"], "tags": []},
        "artist_mbid": "a1",
        "match_method": "isrc",
    })
    enhancer = Enhancer(sources=[fake])
    enhanced = enhancer.enhance_track(_track())

    assert enhanced["musicbrainz"]["genres"] == ["rock"]
    assert enhanced["sources"] == ["musicbrainz"]
    assert enhanced["match_method"] == "isrc"
    assert enhanced["artist_mbid"] == "a1"


def test_enhance_track_caches_result(tmp_path, monkeypatch):
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path))
    fake = FakeSource("musicbrainz", {
        "musicbrainz": {"mbid": "r1", "genres": ["rock"], "tags": []},
        "artist_mbid": "a1",
        "match_method": "isrc",
    })
    enhancer = Enhancer(sources=[fake])
    enhancer.enhance_track(_track())
    enhancer.enhance_track(_track())
    assert fake.call_count == 1


def test_enhance_track_skips_unconfigured_source(tmp_path, monkeypatch):
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path))
    fake = FakeSource("x", {"musicbrainz": {"mbid": "r1", "genres": [], "tags": []}}, configured=False)
    enhancer = Enhancer(sources=[fake])
    enhanced = enhancer.enhance_track(_track())
    assert enhanced["sources"] == []
    assert fake.call_count == 0


def test_enhance_many_with_progress(tmp_path, monkeypatch):
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path))
    fake = FakeSource("musicbrainz", {
        "musicbrainz": {"mbid": "r1", "genres": ["rock"], "tags": []},
        "artist_mbid": "a1",
        "match_method": "isrc",
    })
    enhancer = Enhancer(sources=[fake])
    events = []
    enhancer.enhance_many(
        [
            {"uri": "spotify:track:1", "name": "A", "artists": ["X"], "isrc": "I1"},
            {"uri": "spotify:track:2", "name": "B", "artists": ["Y"], "isrc": "I2"},
        ],
        progress_cb=lambda ev: events.append(ev),
    )
    assert len(events) == 2
    assert events[0]["step"] == 1
    assert events[0]["total"] == 2


def test_source_exception_does_not_break_pipeline(tmp_path, monkeypatch):
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path))
    class ExplodingSource:
        name = "boom"
        def is_configured(self): return True
        def enhance_track(self, track): raise RuntimeError("boom")
    enhancer = Enhancer(sources=[ExplodingSource()])
    result = enhancer.enhance_track(_track())
    assert result["sources"] == []
