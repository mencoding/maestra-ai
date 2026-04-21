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


def test_reranking_uses_compose_score(mocker):
    """Verifica que o score composto governa ordenação (não só taste.context_score)."""
    from maestra_ai.core.curator import Curator

    results = [
        {"uri": "spotify:track:A", "name": "A", "artist": "Art1", "release_date": "2015-01-01"},
        {"uri": "spotify:track:B", "name": "B", "artist": "Art2", "release_date": "1990-01-01"},
    ]
    controller = _FakeController({"q": results})
    taste = _FakeTaste()
    curator = Curator(controller, taste)

    mocker.patch.object(curator, "_build_informed_query", return_value="q")
    mocker.patch.object(curator, "_active_sources", return_value=["musicbrainz", "lastfm"])
    # Força context_score = 0 pra ambos; decade_match é que diferencia
    mocker.patch.object(taste, "context_score", return_value=0.0)
    mocker.patch.object(curator, "_dominant_decades", return_value={"2010s"})
    mocker.patch.object(curator, "_track_tags", return_value=set())
    mocker.patch.object(curator, "_context_tags", return_value=set())
    tracks, _, _ = curator.curate("foco")
    # Track A (2010s) deve vir antes de B (1990s) porque decade_match
    assert tracks[0]["uri"] == "spotify:track:A"


def test_bpm_proximity_affects_rerank(mocker):
    from maestra_ai.core.curator import Curator

    results = [
        {"uri": "spotify:track:A", "name": "A", "artist": "Art", "release_date": "2020-01-01"},
        {"uri": "spotify:track:B", "name": "B", "artist": "Art", "release_date": "2020-01-01"},
    ]
    controller = _FakeController({"q": results})
    taste = _FakeTaste()
    curator = Curator(controller, taste)

    mocker.patch.object(curator, "_build_informed_query", return_value="q")
    mocker.patch.object(curator, "_active_sources", return_value=["musicbrainz", "reccobeats"])
    mocker.patch.object(curator, "_track_bpm", side_effect=lambda uri: 75 if uri.endswith("A") else 180)
    mocker.patch.object(curator, "_active_bpm_target", return_value={"min": 60, "max": 90})
    mocker.patch.object(curator, "_dominant_decades", return_value=set())

    tracks, _, _ = curator.curate("foco")
    # Track A (75 BPM) bate com target; B (180) longe. A deve vir primeiro.
    assert tracks[0]["uri"] == "spotify:track:A"


# v0.12.0 — Issue #5: enhance de candidatos novos --------------------------


def test_enhance_candidates_default_on(mocker):
    """Sem --no-enhance, enhance_many deve ser chamado com track_infos
    contendo isrc dos candidatos."""
    from unittest.mock import MagicMock

    from maestra_ai.core.curator import Curator

    candidates = [
        {"uri": "spotify:track:X", "track": "Faixa X", "artist": "ArtX", "isrc": "USRC10100001"},
        {"uri": "spotify:track:Y", "track": "Faixa Y", "artist": "ArtY", "isrc": None},
    ]
    controller = _FakeController({"q": candidates})
    taste = _FakeTaste()
    curator = Curator(controller, taste)

    mocker.patch.object(curator, "_build_informed_query", return_value="q")
    mocker.patch.object(curator, "_active_sources", return_value=["reccobeats"])

    # Source fake com is_configured = True
    fake_source = MagicMock()
    fake_source.is_configured.return_value = True
    fake_enhancer = MagicMock()
    fake_enhancer._sources = [fake_source]
    fake_enhancer.enhance_many.return_value = []

    mocker.patch(
        "maestra_ai.core.external.default_enhancer",
        return_value=fake_enhancer,
    )

    curator.curate("foco", enhance_candidates=True)

    # enhance_many deve ter sido chamado
    fake_enhancer.enhance_many.assert_called_once()
    call_args = fake_enhancer.enhance_many.call_args[0][0]
    uris_enviados = [t["uri"] for t in call_args]
    assert "spotify:track:X" in uris_enviados
    assert "spotify:track:Y" in uris_enviados
    # ISRC propagado corretamente
    info_x = next(t for t in call_args if t["uri"] == "spotify:track:X")
    assert info_x["isrc"] == "USRC10100001"
    info_y = next(t for t in call_args if t["uri"] == "spotify:track:Y")
    assert info_y["isrc"] is None


def test_enhance_candidates_off_skips_enhancer(mocker):
    """Com enhance_candidates=False, enhance_many NÃO deve ser chamado."""
    from unittest.mock import MagicMock

    from maestra_ai.core.curator import Curator

    candidates = [
        {"uri": "spotify:track:X", "track": "Faixa X", "artist": "ArtX", "isrc": "USRC10100001"},
    ]
    controller = _FakeController({"q": candidates})
    taste = _FakeTaste()
    curator = Curator(controller, taste)

    mocker.patch.object(curator, "_build_informed_query", return_value="q")
    mocker.patch.object(curator, "_active_sources", return_value=["reccobeats"])

    fake_enhancer = MagicMock()
    mock_default_enhancer = mocker.patch(
        "maestra_ai.core.external.default_enhancer",
        return_value=fake_enhancer,
    )

    curator.curate("foco", enhance_candidates=False)

    # default_enhancer nem deve ser importado/chamado
    mock_default_enhancer.assert_not_called()
    fake_enhancer.enhance_many.assert_not_called()


def test_bpm_proximity_works_with_fresh_candidates(mocker):
    """Setup completo: search retorna candidatos com ISRC, Reccobeats retorna
    BPMs distintos via enhance_many, context tem bpm target → ordenação reflete
    bpm_proximity."""
    from unittest.mock import MagicMock

    from maestra_ai.core.curator import Curator
    from maestra_ai.core.external import cache as cache_mod

    candidates = [
        {"uri": "spotify:track:SLOW", "track": "Slow", "artist": "ArtS", "isrc": "USRC10100001"},
        {"uri": "spotify:track:FAST", "track": "Fast", "artist": "ArtF", "isrc": "USRC10100002"},
    ]
    controller = _FakeController({"q": candidates})
    taste = _FakeTaste()
    curator = Curator(controller, taste)

    mocker.patch.object(curator, "_build_informed_query", return_value="q")
    mocker.patch.object(curator, "_active_sources", return_value=["reccobeats"])
    mocker.patch.object(curator, "_active_bpm_target", return_value={"min": 60, "max": 90})
    mocker.patch.object(curator, "_dominant_decades", return_value=set())
    mocker.patch.object(curator, "_track_tags", return_value=set())
    mocker.patch.object(curator, "_context_tags", return_value=set())

    # Simula enhance_many populando o cache: SLOW=75 BPM (dentro do target),
    # FAST=160 BPM (fora do target).
    def fake_enhance_many(track_infos, **_kwargs):
        for ti in track_infos:
            uri = ti["uri"]
            bpm = 75.0 if "SLOW" in uri else 160.0
            cache_mod.put_track({
                "uri": uri,
                "isrc": ti.get("isrc"),
                "artist_mbid": None,
                "musicbrainz": None,
                "lastfm": None,
                "reccobeats": {"tempo": bpm},
                "sources": ["reccobeats"],
                "enhanced_at": "2026-04-20T00:00:00-03:00",
                "match_method": "isrc",
            })
        return []

    fake_source = MagicMock()
    fake_source.is_configured.return_value = True
    fake_enhancer = MagicMock()
    fake_enhancer._sources = [fake_source]
    fake_enhancer.enhance_many.side_effect = fake_enhance_many

    mocker.patch("maestra_ai.core.external.default_enhancer", return_value=fake_enhancer)

    tracks, _, _ = curator.curate("foco")

    # SLOW (75 BPM dentro do target 60-90) deve vir antes de FAST (160 BPM)
    assert tracks[0]["uri"] == "spotify:track:SLOW", (
        f"Esperado SLOW primeiro; ordem: {[t['uri'] for t in tracks]}"
    )
