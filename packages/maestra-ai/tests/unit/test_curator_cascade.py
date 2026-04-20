"""Curator em modo cascade: query informada primeiro, fallback SEMANTIC_MAP."""
from __future__ import annotations


class _FakeController:
    def __init__(self, mapping):
        self.mapping = mapping
        self.searches: list[str] = []

    def search(self, query, type="track", limit=10):
        self.searches.append(query)
        return list(self.mapping.get(query, []))


class _FakeTaste:
    def is_rejected(self, uri): return False
    def context_score(self, uri, context): return 0.0
    def filter_with_artist_info(self, items): return items
    def get_successful_queries(self, context): return []


def test_informed_query_used_when_enough_results(mocker):
    from maestra_ai.core.curator import Curator

    controller = _FakeController({
        "rock uplifting 2010s": [{"uri": f"spotify:track:{i}", "name": f"T{i}", "artist": f"A{i}"} for i in range(12)],
    })
    taste = _FakeTaste()
    curator = Curator(controller, taste)

    mocker.patch.object(curator, "_build_informed_query", return_value="rock uplifting 2010s")
    tracks, queries, sources = curator.curate("foco")

    assert "rock uplifting 2010s" in queries
    assert len(tracks) >= 5
    # não deve ter chamado queries do SEMANTIC_MAP
    assert controller.searches == ["rock uplifting 2010s"]


def test_cascade_fallback_when_below_min(mocker):
    from maestra_ai.core.curator import SEMANTIC_MAP, Curator

    first_queries_for_foco = SEMANTIC_MAP["foco"]
    controller = _FakeController({
        "genre X 2010s": [{"uri": "spotify:track:0", "name": "T0", "artist": "A0"}, {"uri": "spotify:track:1", "name": "T1", "artist": "A1"}],
        first_queries_for_foco[0]: [{"uri": f"spotify:track:{10+i}", "name": f"T{i}", "artist": f"B{i}"} for i in range(12)],
    })
    taste = _FakeTaste()
    curator = Curator(controller, taste)

    mocker.patch.object(curator, "_build_informed_query", return_value="genre X 2010s")
    tracks, queries, sources = curator.curate("foco")

    assert "genre X 2010s" in queries
    assert first_queries_for_foco[0] in queries
    assert len(tracks) >= 5


def test_curate_returns_sources_used(mocker):
    from maestra_ai.core.curator import Curator

    controller = _FakeController({"q": [{"uri": "spotify:track:0", "name": "T", "artist": "A"}]})
    taste = _FakeTaste()
    curator = Curator(controller, taste)

    mocker.patch.object(curator, "_build_informed_query", return_value="q")
    mocker.patch.object(curator, "_active_sources", return_value=["musicbrainz", "lastfm"])
    tracks, queries, sources = curator.curate("foco")
    assert sources == ["musicbrainz", "lastfm"]
