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


class TestBuildInformedQuery:
    def _ctx(self, **kwargs):
        from maestra_ai.core.context_parser import ParsedContext
        defaults = {"text": "", "positive": (), "negative": (), "artists_hint": (), "bpm": None}
        defaults.update(kwargs)
        return ParsedContext(**defaults)

    def test_vazio_retorna_none(self, curator, monkeypatch):
        monkeypatch.setattr(curator.taste, "get_preferred_artists", lambda: [])
        assert curator._build_informed_query(self._ctx()) is None

    def test_so_positivo_gera_query(self, curator, monkeypatch):
        monkeypatch.setattr(curator.taste, "get_preferred_artists", lambda: [])
        q = curator._build_informed_query(self._ctx(positive=("metal",)))
        assert q is not None
        assert "metal" in q

    def test_positivo_e_artist_hint_combinam(self, curator, monkeypatch):
        monkeypatch.setattr(curator.taste, "get_preferred_artists", lambda: [])
        q = curator._build_informed_query(self._ctx(
            positive=("metal",), artists_hint=("Gojira",)
        ))
        assert "Gojira" in q
        assert "metal" in q

    def test_bpm_adiciona_qualificador(self, curator, monkeypatch):
        from maestra_ai.core.context_parser import BpmRange
        monkeypatch.setattr(curator.taste, "get_preferred_artists", lambda: [])
        q = curator._build_informed_query(self._ctx(
            positive=("metal",), bpm=BpmRange(min=100, max=120)
        ))
        assert q is not None
        assert "metal" in q
        # Qualificador de bpm é adicionado — formato "110bpm" (média)
        assert "110" in q or "bpm" in q.lower()

    def test_so_taste_sem_positive_usa_top_artista(self, curator, monkeypatch):
        monkeypatch.setattr(curator.taste, "get_preferred_artists", lambda: ["Heilung"])
        q = curator._build_informed_query(self._ctx())
        assert q is not None
        assert "Heilung" in q

    def test_top_taste_negado_pula_pro_proximo(self, curator, monkeypatch):
        monkeypatch.setattr(
            curator.taste, "get_preferred_artists",
            lambda: ["Ambient Band", "Heilung"]
        )
        q = curator._build_informed_query(self._ctx(negative=("ambient",)))
        # "Ambient Band" tem "ambient" case-insensitive → pula
        assert q is not None
        assert "Heilung" in q
        assert "Ambient" not in q

    def test_todos_os_top_taste_negados_e_sem_positive_retorna_none(self, curator, monkeypatch):
        monkeypatch.setattr(
            curator.taste, "get_preferred_artists",
            lambda: ["Ambient One", "Ambient Two", "Ambient Three"]
        )
        q = curator._build_informed_query(self._ctx(negative=("ambient",)))
        assert q is None

    # --- Testes T3: DSL Spotify artist:"..." (#20-4) ---

    def test_build_informed_query_um_artist_hint_usa_dsl_spotify(self, curator, monkeypatch):
        """N=1 artist_hint → query usa DSL artist:"Nome"."""
        monkeypatch.setattr(curator.taste, "get_preferred_artists", lambda: [])
        q = curator._build_informed_query(self._ctx(artists_hint=("The HU",)))
        assert q is not None
        assert 'artist:"The HU"' in q

    def test_build_informed_query_multiplos_artists_concat_com_or(self, curator, monkeypatch):
        """N=3 artists_hint → query usa DSL com OR entre todos."""
        monkeypatch.setattr(curator.taste, "get_preferred_artists", lambda: [])
        q = curator._build_informed_query(
            self._ctx(artists_hint=("The HU", "Wardruna", "Heilung"))
        )
        assert q is not None
        assert 'artist:"The HU"' in q
        assert 'artist:"Wardruna"' in q
        assert 'artist:"Heilung"' in q
        assert " OR " in q

    def test_build_informed_query_inclui_positive_livre(self, curator, monkeypatch):
        """artist_hint + positive → DSL artist + texto livre para positive."""
        monkeypatch.setattr(curator.taste, "get_preferred_artists", lambda: [])
        q = curator._build_informed_query(
            self._ctx(artists_hint=("The HU",), positive=("metal",))
        )
        assert q is not None
        assert 'artist:"The HU"' in q
        assert "metal" in q

    def test_build_informed_query_inclui_bpm_livre(self, curator, monkeypatch):
        """artist_hint + bpm → DSL artist + qualificador bpm como texto livre."""
        from maestra_ai.core.context_parser import BpmRange
        monkeypatch.setattr(curator.taste, "get_preferred_artists", lambda: [])
        q = curator._build_informed_query(
            self._ctx(artists_hint=("The HU",), bpm=BpmRange(min=100, max=140))
        )
        assert q is not None
        assert 'artist:"The HU"' in q
        # mid = (100+140)//2 = 120
        assert "120bpm" in q

    def test_build_informed_query_sem_artist_hint_usa_top_taste_com_dsl(self, curator, monkeypatch):
        """Sem artists_hint, top taste também usa DSL artist:"..."."""
        monkeypatch.setattr(curator.taste, "get_preferred_artists", lambda: ["Heilung"])
        q = curator._build_informed_query(self._ctx())
        assert q is not None
        assert 'artist:"Heilung"' in q

    def test_build_informed_query_aspas_no_nome_artist(self, curator, monkeypatch):
        """Aspas internas no nome do artista são removidas antes do wrap DSL."""
        monkeypatch.setattr(curator.taste, "get_preferred_artists", lambda: [])
        q = curator._build_informed_query(
            self._ctx(artists_hint=('Foo "Bar" Baz',))
        )
        assert q is not None
        # Aspas internas removidas → nome limpo entre as aspas externas da DSL
        assert 'artist:"Foo Bar Baz"' in q
        # Não deve ter aspas duplas dentro do valor da DSL
        assert 'artist:"Foo "Bar" Baz"' not in q

    def test_build_informed_query_sem_sinal_retorna_none(self, curator, monkeypatch):
        """Regressão: sem artists_hint, sem taste e sem positive → None."""
        monkeypatch.setattr(curator.taste, "get_preferred_artists", lambda: [])
        q = curator._build_informed_query(self._ctx())
        assert q is None


class TestCurateIntegracaoV013:
    """Integração T11: curate() usa parsed + negative_filter + anti_tag_penalty."""

    def test_curate_usa_parsed_context_quando_informado(self, curator, mock_controller, monkeypatch):
        """curate() continua devolvendo tupla (tracks, queries, sources)."""
        result = curator.curate("foco", count=3)
        assert len(result) == 3  # (tracks, queries, sources)

    def test_curate_aplica_negative_filter_e_reporta_queries(self, curator, mock_controller, monkeypatch):
        """Com contexto 'rock evitar ambient', tracks retornadas não devem ter tag 'ambient'.

        Usa URIs distinguíveis (ambient_N vs rock_N) para garantir que o filtro
        negativo seja realmente exercitado — e não passe de forma trivial.
        """
        from maestra_ai.core.external import cache as cache_mod

        # 3 candidatos ambient + 12 rock = 15 total; após filtro: 12 rock (>= MIN_CANDIDATES=10).
        # Ambient URIs vêm PRIMEIRO na lista para garantir que, sem o filtro, eles
        # apareceriam no top-5 retornado (teste falha com filtro quebrado).
        ambient_uris = [f"spotify:track:ambient_{i}" for i in range(3)]
        rock_uris = [f"spotify:track:rock_{i}" for i in range(12)]
        all_uris = ambient_uris + rock_uris  # ambient primeiro → ranking favorece ambient sem filtro

        mock_controller.search.return_value = [
            {"uri": u, "track": "t", "artist": "A", "album": "Album"} for u in all_uris
        ]

        def fake_get(uri):
            tags = ["ambient"] if "ambient" in uri else ["rock"]
            return {"musicbrainz": {"tags": tags}}

        monkeypatch.setattr(cache_mod, "get_track", fake_get)

        tracks, _queries, _sources = curator.curate("rock evitar ambient", count=5)

        returned_uris = {t["uri"] for t in tracks}
        # Nenhuma track com tag ambient deve ter passado pelo filtro
        assert not any("ambient" in u for u in returned_uris), (
            f"Negative filter deveria ter removido ambient tracks; retornou: {returned_uris}"
        )
        # Deve ter retornado ao menos uma track rock
        assert len(tracks) > 0
        assert all("rock" in u for u in returned_uris)

    def test_curate_degraded_log_warning(self, curator, mock_controller, monkeypatch, caplog):
        """Quando hard filter esvaziaria (todos candidatos têm tag negada), loga warning."""
        import logging

        from maestra_ai.core.external import cache as cache_mod
        # Todos os candidatos passam a ter tag ambient → filtro esvazia → degrada
        monkeypatch.setattr(cache_mod, "get_track",
                            lambda uri: {"musicbrainz": {"tags": ["ambient"]}})

        with caplog.at_level(logging.WARNING):
            curator.curate("rock evitar ambient", count=3)
        assert any("degrading to soft penalty" in r.message for r in caplog.records)


class TestNormalizeContext:
    """Testes para _normalize_context — bug #20-2."""

    def test_normalize_context_aceita_dict_com_text(self, curator):
        """Dict com campo 'text' deve retornar apenas o valor texto."""
        resultado = curator._normalize_context({"text": "metal ritual", "bpm": None})
        assert resultado == "metal ritual"

    def test_normalize_context_aceita_string(self, curator):
        """String direta deve passar sem alteração (regressão)."""
        resultado = curator._normalize_context("metal ritual")
        assert resultado == "metal ritual"

    def test_normalize_context_aceita_none(self, curator):
        """None deve retornar DEFAULT_CONTEXT (regressão)."""
        from maestra_ai.core.curator import DEFAULT_CONTEXT
        resultado = curator._normalize_context(None)
        assert resultado == DEFAULT_CONTEXT

    def test_normalize_context_dict_sem_text(self, curator):
        """Dict sem campo 'text' deve retornar DEFAULT_CONTEXT."""
        from maestra_ai.core.curator import DEFAULT_CONTEXT
        resultado = curator._normalize_context({"bpm": None})
        assert resultado == DEFAULT_CONTEXT

    def test_normalize_context_nao_serializa_dict_como_query(self, curator):
        """Garantir que dict com bpm nunca vira repr literal na query."""
        resultado = curator._normalize_context({"text": "foo", "bpm": None})
        assert "{" not in resultado
        assert "'bpm'" not in resultado
        assert "none" not in resultado.lower()
