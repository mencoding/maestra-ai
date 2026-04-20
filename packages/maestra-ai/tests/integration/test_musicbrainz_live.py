"""Teste ao vivo contra a API pública do MusicBrainz.

Executa chamadas HTTP reais. NÃO roda no pytest default — use:
    uv run pytest -m integration_live

Objetivo: impedir regressão silenciosa quando a forma da resposta do
MusicBrainz mudar ou quando nossa estratégia de obter gêneros quebrar
(ex.: a lib `musicbrainzngs` não expõe `inc=genres`, então buscamos via
HTTP direto — se o endpoint mudar, este teste pega).

MBID usado: Fleetwood Mac (bd13909f-1c29-4c27-a874-d4aaf27c5b1a) —
artista mainstream com gêneros bem documentados no MB desde ~2019.
"""
import pytest

from maestra_ai.core.external.musicbrainz import MusicBrainzSource

_FLEETWOOD_MAC_MBID = "bd13909f-1c29-4c27-a874-d4aaf27c5b1a"


@pytest.fixture
def mb_live():
    return MusicBrainzSource(app_version="v0.9-live-test")


@pytest.mark.integration_live
def test_fetch_artist_genres_http_retorna_generos_reais(mb_live):
    genres = mb_live._fetch_artist_genres_http(_FLEETWOOD_MAC_MBID)
    assert isinstance(genres, list), "retorno deve ser lista"
    assert len(genres) > 0, (
        f"MB deveria ter gêneros para Fleetwood Mac — recebido: {genres!r}. "
        "Se vazio: MB mudou a forma da resposta ou removeu genres do ws/2."
    )
    lowered = [g.lower() for g in genres]
    assert "rock" in lowered, (
        f"'rock' esperado nos gêneros — recebido: {genres!r}"
    )


@pytest.mark.integration_live
def test_enhance_track_end_to_end_retorna_generos(mb_live):
    track = {
        "uri": "spotify:track:0ofHAoxe9vBkTCp2UQIavz",
        "name": "Dreams",
        "artists": ["Fleetwood Mac"],
        "isrc": "USUM71807351",
    }
    result = mb_live.enhance_track(track)
    assert result is not None, "MB não retornou resultado para Dreams (ISRC USUM71807351)"
    assert result["match_method"] in ("isrc", "name")
    assert result["musicbrainz"]["genres"], (
        f"gêneros vazios — resposta: {result['musicbrainz']!r}. "
        "Se ISRC mudou de mapeamento no MB, este teste precisa de outra faixa."
    )
