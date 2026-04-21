"""Testes unitários para MusicBrainzSource — foco em artist_exists (T4)."""
from unittest.mock import patch

import pytest

from maestra_ai.core.external.musicbrainz import MusicBrainzSource


@pytest.fixture
def mb():
    """MusicBrainzSource com versão fake (evita chamadas reais ao set_useragent)."""
    with patch("musicbrainzngs.set_useragent"), patch("musicbrainzngs.set_rate_limit"):
        return MusicBrainzSource(app_version="0.0.0-test")


class TestArtistExists:
    """Testes para MusicBrainzSource.artist_exists."""

    def test_artist_exists_retorna_true_com_score_alto(self, mb):
        """Mock search_artists com score 95 → deve retornar True."""
        resp = {"artist-list": [{"ext:score": "95", "id": "abc", "name": "The HU"}]}
        with patch("musicbrainzngs.search_artists", return_value=resp):
            assert mb.artist_exists("The HU") is True

    def test_artist_exists_retorna_false_score_baixo(self, mb):
        """Mock search_artists com score 40 → deve retornar False (abaixo de 85)."""
        resp = {"artist-list": [{"ext:score": "40", "id": "xyz", "name": "FakeBand"}]}
        with patch("musicbrainzngs.search_artists", return_value=resp):
            assert mb.artist_exists("FakeBand") is False

    def test_artist_exists_retorna_false_lista_vazia(self, mb):
        """Mock search_artists retornando lista vazia → deve retornar False."""
        resp = {"artist-list": []}
        with patch("musicbrainzngs.search_artists", return_value=resp):
            assert mb.artist_exists("BandaInexistente") is False

    def test_artist_exists_fallback_true_em_exception(self, mb):
        """MB lança exceção → fallback gracioso deve retornar True (não penalizar)."""
        with patch("musicbrainzngs.search_artists", side_effect=Exception("timeout")):
            assert mb.artist_exists("QualquerBanda") is True

    def test_artist_exists_false_para_string_vazia(self, mb):
        """String vazia → deve retornar False sem chamar a API."""
        with patch("musicbrainzngs.search_artists") as mock_search:
            assert mb.artist_exists("") is False
            mock_search.assert_not_called()

    def test_artist_exists_false_para_string_apenas_espacos(self, mb):
        """String de só espaços → deve retornar False sem chamar a API."""
        with patch("musicbrainzngs.search_artists") as mock_search:
            assert mb.artist_exists("   ") is False
            mock_search.assert_not_called()

    def test_artist_exists_score_exatamente_85_retorna_true(self, mb):
        """Score exatamente no limiar (85) → deve retornar True (>= 85)."""
        resp = {"artist-list": [{"ext:score": "85", "id": "lim", "name": "Limiar"}]}
        with patch("musicbrainzngs.search_artists", return_value=resp):
            assert mb.artist_exists("Limiar") is True

    def test_artist_exists_score_84_retorna_false(self, mb):
        """Score 84 (abaixo do limiar) → deve retornar False."""
        resp = {"artist-list": [{"ext:score": "84", "id": "sub", "name": "SubLimiar"}]}
        with patch("musicbrainzngs.search_artists", return_value=resp):
            assert mb.artist_exists("SubLimiar") is False

    def test_artist_exists_score_invalido_retorna_false(self, mb):
        """Score não-numérico → int() falha → score=0 → False."""
        resp = {"artist-list": [{"ext:score": "n/a", "id": "inv", "name": "ScoreInvalido"}]}
        with patch("musicbrainzngs.search_artists", return_value=resp):
            assert mb.artist_exists("ScoreInvalido") is False

    def test_artist_exists_sem_artist_list_retorna_false(self, mb):
        """Resposta sem chave 'artist-list' → deve retornar False."""
        resp = {}
        with patch("musicbrainzngs.search_artists", return_value=resp):
            assert mb.artist_exists("Fantasma") is False
