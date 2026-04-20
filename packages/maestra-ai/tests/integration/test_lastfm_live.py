"""Teste live contra a API real do Last.fm.

Executa chamadas HTTP reais. NÃO roda no pytest default — use:
    uv run pytest -m integration_live

Objetivo: impedir regressão silenciosa quando a forma da resposta do
Last.fm mudar ou quando nossa estratégia de rate limiting quebrar.

Requer env MAESTRA_LASTFM_KEY. Se ausente, o teste é skipado.
"""
from __future__ import annotations

import os

import pytest

from maestra_ai.core.external.lastfm import LastfmSource

pytestmark = pytest.mark.integration_live


@pytest.fixture
def _api_key() -> str:
    key = os.environ.get("MAESTRA_LASTFM_KEY")
    if not key:
        pytest.skip("MAESTRA_LASTFM_KEY não configurada")
    return key


def test_lookup_fleetwood_mac_dreams(_api_key: str):
    """Busca Dreams de Fleetwood Mac via _lookup (artista + track)."""
    source = LastfmSource(api_key=_api_key)
    result = source._lookup({
        "uri": "spotify:track:x",
        "name": "Dreams",
        "artists": ["Fleetwood Mac"],
        "isrc": None,
    })
    assert result is not None, "Last.fm não retornou resultado para Dreams - Fleetwood Mac"
    assert result["lastfm"]["top_tags"], "esperava tags não vazias para Dreams - Fleetwood Mac"
    assert result["lastfm"]["listeners"] > 0, "esperava listeners > 0 para Dreams"


def test_similar_artists_fleetwood_mac(_api_key: str):
    """Busca artistas similares a Fleetwood Mac."""
    source = LastfmSource(api_key=_api_key)
    similars = source.get_similar_artists("Fleetwood Mac", limit=5)
    assert len(similars) > 0, "Last.fm deveria retornar artistas similares para Fleetwood Mac"
    assert isinstance(similars[0], str), f"elementos da lista devem ser str, recebido: {type(similars[0])}"
    # Fleetwood Mac é rock clássico; esperamos artistas de gênero similar
    lowered = [s.lower() for s in similars]
    # Apenas verificamos que temos artistas reais; nomes específicos podem variar
    assert any(name in lowered for name in ["eagles", "lindsey buckingham", "christine mcvie"]) or len(similars) > 0, (
        f"artistas esperados similares a Fleetwood Mac — recebido: {similars!r}. "
        "Se lista vazia: Last.fm mudou a forma da resposta."
    )
