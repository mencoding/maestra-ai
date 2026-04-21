"""Testes do Curator — tradução de contexto em buscas."""
from unittest.mock import MagicMock

import pytest

from maestra_ai.core.curator import Curator
from maestra_ai.core.taste import TasteProfile


@pytest.fixture
def taste(tmp_path):
    """TasteProfile vazio temporário."""
    path = tmp_path / "taste_profile.json"
    return TasteProfile(str(path))


@pytest.fixture
def mock_controller():
    """SpotifyController mockado."""
    ctrl = MagicMock()
    ctrl.search.return_value = [
        {"track": "Focus Track 1", "artist": "Artist A", "uri": "spotify:track:a", "album": "Album A"},
        {"track": "Focus Track 2", "artist": "Artist B", "uri": "spotify:track:b", "album": "Album B"},
        {"track": "Focus Track 3", "artist": "Artist C", "uri": "spotify:track:c", "album": "Album C"},
    ]
    return ctrl


@pytest.fixture
def curator(mock_controller, taste):
    return Curator(mock_controller, taste)


class TestCurate:
    def test_retorna_uris_para_contexto_semantico(self, curator, mock_controller):
        result, queries, _sources = curator.curate("foco", count=3)

        assert len(result) <= 3
        assert all(r["uri"].startswith("spotify:track:") for r in result)
        assert len(queries) > 0
        mock_controller.search.assert_called()

    def test_retorna_lista_vazia_se_search_falha(self, curator, mock_controller):
        mock_controller.search.return_value = []
        result, queries, _sources = curator.curate("contexto impossível", count=5)
        assert result == []

    def test_filtra_faixas_rejeitadas(self, curator, mock_controller, taste):
        taste.record_feedback("spotify:track:a", "bad")
        taste.save()

        result, _, _sources = curator.curate("foco", count=5)
        uris = [r["uri"] for r in result]
        assert "spotify:track:a" not in uris

    def test_usa_queries_aprendidas_quando_disponiveis(self, curator, mock_controller, taste):
        taste.data["context_queries"]["energia"] = {
            "queries_used": ["power metal"],
            "success_rate": 0.8,
            "last_used": "2026-04-16",
        }

        _, queries, _sources = curator.curate("energia", count=3)

        assert "power metal" in queries
        calls = [str(c) for c in mock_controller.search.call_args_list]
        assert any("power metal" in c for c in calls)

    def test_exclui_uris_ja_presentes(self, curator):
        result, _, _sources = curator.curate("foco", count=3, exclude_uris={"spotify:track:a"})

        uris = [r["uri"] for r in result]
        assert "spotify:track:a" not in uris

    def test_busca_mais_resultados_para_compensar_exclusoes(self, curator, mock_controller):
        first_results = [
            {"track": "Old 1", "artist": "Artist A", "uri": "spotify:track:a", "album": "Album A"},
            {"track": "Old 2", "artist": "Artist B", "uri": "spotify:track:b", "album": "Album B"},
            {"track": "New 1", "artist": "Artist C", "uri": "spotify:track:c", "album": "Album C"},
            {"track": "New 2", "artist": "Artist D", "uri": "spotify:track:d", "album": "Album D"},
        ]
        mock_controller.search.return_value = first_results

        result, _, _sources = curator.curate(
            "foco",
            count=2,
            exclude_uris={"spotify:track:a", "spotify:track:b"},
        )

        assert [r["uri"] for r in result] == ["spotify:track:c", "spotify:track:d"]
        assert mock_controller.search.call_args.kwargs["limit"] > 2

    def test_prioriza_faixas_positivas_no_contexto(self, curator, taste):
        taste.record_context_signal(
            "spotify:track:c",
            "positive",
            context="foco",
            source="listened_to_end",
            weight=2,
        )

        result, _, _sources = curator.curate("foco", count=3)

        assert result[0]["uri"] == "spotify:track:c"

    def test_evita_faixas_negativas_no_contexto(self, curator, taste):
        taste.record_context_signal(
            "spotify:track:a",
            "negative",
            context="foco",
            source="skip_candidate",
            weight=-1,
        )

        result, _, _sources = curator.curate("foco", count=3)
        uris = [r["uri"] for r in result]

        assert "spotify:track:a" not in uris

    def test_negativo_em_outro_contexto_nao_bloqueia(self, curator, taste):
        taste.record_context_signal(
            "spotify:track:a",
            "negative",
            context="energia",
            source="skip_candidate",
            weight=-1,
        )

        result, _, _sources = curator.curate("foco", count=3)
        uris = [r["uri"] for r in result]

        assert "spotify:track:a" in uris

    def test_exclui_artistas_dominantes(self, curator):
        result, _, _sources = curator.curate(
            "foco",
            count=3,
            exclude_artists={"Artist A"},
        )

        artists = [r["artist"] for r in result]
        assert "Artist A" not in artists

    def test_limita_faixas_por_artista_no_lote(self, curator, mock_controller):
        mock_controller.search.return_value = [
            {"track": "A1", "artist": "Artist A", "uri": "spotify:track:a1", "album": "Album"},
            {"track": "A2", "artist": "Artist A", "uri": "spotify:track:a2", "album": "Album"},
            {"track": "B1", "artist": "Artist B", "uri": "spotify:track:b1", "album": "Album"},
        ]

        result, _, _sources = curator.curate("foco", count=2, max_per_artist=1)

        assert [r["uri"] for r in result] == ["spotify:track:a1", "spotify:track:b1"]


class TestResolveQueries:
    def test_referencia_direta_artista(self, curator):
        queries = curator._resolve_queries("mais The HU")
        assert "the hu" in queries[0]

    def test_mapeamento_semantico_foco(self, curator):
        queries = curator._resolve_queries("foco")
        assert len(queries) > 0

    def test_mapeamento_semantico_energia(self, curator):
        queries = curator._resolve_queries("energia")
        assert len(queries) > 0

    def test_fallback_pra_contexto_desconhecido(self, curator):
        queries = curator._resolve_queries("algo completamente aleatório")
        assert "algo completamente aleatório" in queries

    def test_contexto_vazio_usa_fallback_foco(self, curator):
        queries = curator._resolve_queries("")
        assert queries == ["lo-fi instrumental", "ambient study", "minimal piano", "post-rock instrumental"]

    def test_contexto_composto_preserva_descritores_especificos(self, curator):
        queries = curator._resolve_queries(
            "foco analítico, neoclássico minimalista e ambient denso para trabalho concentrado"
        )

        assert queries[0] == "neoclassical minimal ambient dark study focus"
        assert "lo-fi instrumental" in queries


class TestCuratorPrune:
    def test_prune_dry_run_retorna_candidatos_sem_remover(self):
        import tempfile
        from unittest.mock import MagicMock

        from maestra_ai.core.curator import Curator
        from maestra_ai.core.taste import TasteProfile

        controller = MagicMock()
        controller.playlist_tracks.return_value = [
            {"uri": "spotify:track:a", "track": "A", "artist": "ArtA"},
            {"uri": "spotify:track:b", "track": "B", "artist": "ArtB"},
        ]

        with tempfile.TemporaryDirectory() as td:
            taste = TasteProfile(f"{td}/taste.json")
            # Marca A como ruim globalmente
            taste.record_feedback("spotify:track:a", "bad", global_feedback=True)

            curator = Curator(controller, taste)
            result = curator.prune(playlist_id="pl_123", context="foco", confirm=False)

            assert result["dry_run"] is True
            assert result["removed"] == 0
            assert len(result["candidates"]) >= 1
            controller.playlist_remove.assert_not_called()

    def test_prune_confirm_remove_e_cria_snapshot(self, tmp_path, monkeypatch):
        from unittest.mock import MagicMock

        from maestra_ai.core.curator import Curator
        from maestra_ai.core.taste import TasteProfile
        monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))

        controller = MagicMock()
        controller.playlist_tracks.return_value = [
            {"uri": "spotify:track:bad", "track": "Bad", "artist": "ArtBad"},
        ]

        taste = TasteProfile(str(tmp_path / "taste.json"))
        taste.record_feedback("spotify:track:bad", "bad", global_feedback=True)

        curator = Curator(controller, taste)
        result = curator.prune(
            playlist_id="pl_xyz", context="foco", confirm=True,
        )

        assert result["dry_run"] is False
        assert result["removed"] >= 1
        controller.playlist_remove.assert_called_once()
        assert result["snapshot_id"]  # id não-vazio


class TestTrackTags:
    """`_track_tags` consome cache external (MB canônico + LF filtrado)."""

    def test_track_sem_entrada_no_cache_retorna_vazio(self, curator, monkeypatch):
        # Sem entrada no cache → get_track retorna None → set() vazio.
        from maestra_ai.core import curator as curator_mod
        monkeypatch.setattr(curator_mod.cache_mod, "get_track", lambda uri: None)
        track = {"uri": "spotify:track:nao_cacheado", "artist": "X"}
        assert curator._track_tags(track) == set()

    def test_track_com_tags_mb_retorna_as_tags(self, curator, monkeypatch):
        # MB traz tags canônicas; entram direto (lowercased).
        from maestra_ai.core import curator as curator_mod
        monkeypatch.setattr(curator_mod.cache_mod, "get_track", lambda uri: {
            "musicbrainz": {"tags": ["folk metal", "viking metal"]},
        })
        track = {"uri": "spotify:track:x", "artist": "A"}
        tags = curator._track_tags(track)
        assert "folk metal" in tags
        assert "viking metal" in tags

    def test_track_com_tags_lf_filtradas(self, curator, monkeypatch):
        # Cache real: lastfm.top_tags é list[str]. Meta-tags (década) são descartadas.
        from maestra_ai.core import curator as curator_mod
        monkeypatch.setattr(curator_mod.cache_mod, "get_track", lambda uri: {
            "lastfm": {"top_tags": ["2010s", "shoegaze"]},
        })
        track = {"uri": "spotify:track:x", "artist": "A"}
        tags = curator._track_tags(track)
        assert "shoegaze" in tags
        assert "2010s" not in tags

    def test_merge_mb_e_lf(self, curator, monkeypatch):
        # Merge MB (canônico) + LF (filtrado); duplicatas dedupadas pelo set.
        from maestra_ai.core import curator as curator_mod
        monkeypatch.setattr(curator_mod.cache_mod, "get_track", lambda uri: {
            "musicbrainz": {"tags": ["folk metal"]},
            "lastfm": {"top_tags": ["viking"]},
        })
        track = {"uri": "spotify:track:x", "artist": "A"}
        tags = curator._track_tags(track)
        assert "folk metal" in tags
        assert "viking" in tags

    def test_uri_ausente_retorna_vazio(self, curator, monkeypatch):
        # Track sem uri: evita passar string vazia adiante; retorna set() imediatamente.
        from maestra_ai.core import curator as curator_mod
        monkeypatch.setattr(curator_mod.cache_mod, "get_track", lambda uri: None)
        assert curator._track_tags({"artist": "A"}) == set()


class TestApplyNegativeFilter:
    def _ctx(self, neg):
        from maestra_ai.core.context_parser import ParsedContext
        return ParsedContext(text="dummy", negative=tuple(neg))

    def test_sem_negacoes_no_op(self, curator):
        candidates = [{"uri": f"spotify:track:{i}", "artist": "A"} for i in range(15)]
        result, degraded = curator._apply_negative_filter(candidates, self._ctx([]))
        assert result == candidates
        assert degraded is False

    def test_hard_filter_quando_acima_de_min_candidates(self, curator, monkeypatch):
        from maestra_ai.core.external import cache as cache_mod
        def fake_get(uri):
            # URI "spotify:track:1" tem ambient; restantes têm rock.
            # Usa comparação exata para evitar match em "spotify:track:11", etc.
            return {"musicbrainz": {"tags": ["ambient"]}} if uri == "spotify:track:1" else {"musicbrainz": {"tags": ["rock"]}}
        monkeypatch.setattr(cache_mod, "get_track", fake_get)

        candidates = [{"uri": f"spotify:track:{i}", "artist": "A"} for i in range(20)]
        # Apenas candidate ...1 tem ambient; outros têm rock. 1 remove → 19 sobram > 10
        result, degraded = curator._apply_negative_filter(candidates, self._ctx(["ambient"]))
        assert len(result) == 19
        assert degraded is False

    def test_degrada_quando_filtro_esvazia_abaixo_de_min(self, curator, monkeypatch):
        from maestra_ai.core.external import cache as cache_mod
        # Todos os candidatos têm "ambient"
        monkeypatch.setattr(cache_mod, "get_track", lambda uri: {"musicbrainz": {"tags": ["ambient"]}})

        candidates = [{"uri": f"spotify:track:{i}", "artist": "A"} for i in range(12)]
        result, degraded = curator._apply_negative_filter(candidates, self._ctx(["ambient"]))
        assert result == candidates  # originais preservados
        assert degraded is True

    def test_fronteira_exatamente_min_candidates_e_sucesso(self, curator, monkeypatch):
        from maestra_ai.core.external import cache as cache_mod
        def fake_get(uri):
            # candidates 0..9 sem ambient; 10..14 com ambient
            idx = int(uri.split(":")[-1])
            return {"musicbrainz": {"tags": ["rock"] if idx < 10 else ["ambient"]}}
        monkeypatch.setattr(cache_mod, "get_track", fake_get)

        candidates = [{"uri": f"spotify:track:{i}", "artist": "A"} for i in range(15)]
        # Após filter: 10 sobram (exatamente MIN_CANDIDATES=10)
        result, degraded = curator._apply_negative_filter(candidates, self._ctx(["ambient"]))
        assert len(result) == 10
        assert degraded is False  # >= MIN_CANDIDATES aceita
