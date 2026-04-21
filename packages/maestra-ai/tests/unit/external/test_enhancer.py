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


def test_enhance_track_fills_missing_source_in_cache(tmp_path, monkeypatch):
    """v0.11.1: quando uma source nova entra online, o cache é complementado.

    Cenário: onboard rodou em v0.10.x com MB+LF. Depois v0.11 adiciona
    Reccobeats. Próximo enhance não deve retornar cache stale — deve chamar
    só Reccobeats e fazer merge, preservando MB+LF já cacheados.
    """
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path))

    mb = FakeSource("musicbrainz", {
        "musicbrainz": {"mbid": "r1", "genres": ["rock"], "tags": []},
        "artist_mbid": "a1",
        "match_method": "isrc",
    })
    lf = FakeSource("lastfm", {
        "lastfm": {"top_tags": ["classic"], "playcount": 1, "listeners": 1, "similar_artists": []},
        "match_method": "name",
    })

    # Primeiro enhance com MB+LF ativos
    enhancer_v1 = Enhancer(sources=[mb, lf])
    enhanced_v1 = enhancer_v1.enhance_track(_track())
    assert set(enhanced_v1["sources"]) == {"musicbrainz", "lastfm"}
    assert enhanced_v1["reccobeats"] is None
    assert mb.call_count == 1
    assert lf.call_count == 1

    # Segundo enhance com MB+LF+Reccobeats (source nova)
    rb = FakeSource("reccobeats", {
        "reccobeats": {"tempo": 120.0, "key": 5, "mode": 1, "loudness": -8.0,
                       "acousticness": 0.1, "danceability": 0.7, "energy": 0.8,
                       "instrumentalness": 0.0, "liveness": 0.1, "speechiness": 0.05,
                       "valence": 0.6},
        "match_method": "isrc",
    })
    enhancer_v2 = Enhancer(sources=[mb, lf, rb])
    enhanced_v2 = enhancer_v2.enhance_track(_track())

    # MB e LF não devem ser re-consultados (cache hit), só RB
    assert mb.call_count == 1, "MB não deveria ser re-consultado"
    assert lf.call_count == 1, "LF não deveria ser re-consultado"
    assert rb.call_count == 1, "RB deveria ser consultado uma vez"
    # Merge preservou dados antigos + adicionou novos
    assert enhanced_v2["musicbrainz"] == {"mbid": "r1", "genres": ["rock"], "tags": []}
    assert enhanced_v2["lastfm"]["top_tags"] == ["classic"]
    assert enhanced_v2["reccobeats"]["tempo"] == 120.0
    assert set(enhanced_v2["sources"]) == {"musicbrainz", "lastfm", "reccobeats"}


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
