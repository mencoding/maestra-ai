"""Testes para maestra_ai.core.config.normalize_playlist_id."""
from __future__ import annotations

import pytest

from maestra_ai.core.config import normalize_playlist_id

# ID base62 de 22 chars usado como fixture canônica.
_ID = "37i9dQZF1DXcBWIGoYBM5M"


def test_id_puro_passa_direto():
    assert normalize_playlist_id(_ID) == _ID


def test_uri_spotify_playlist():
    assert normalize_playlist_id(f"spotify:playlist:{_ID}") == _ID


def test_url_com_query_string():
    url = f"https://open.spotify.com/playlist/{_ID}?si=abc123def456"
    assert normalize_playlist_id(url) == _ID


def test_url_sem_query_string():
    url = f"https://open.spotify.com/playlist/{_ID}"
    assert normalize_playlist_id(url) == _ID


def test_string_vazia_levanta_value_error():
    with pytest.raises(ValueError):
        normalize_playlist_id("")


def test_menos_que_22_chars_levanta_value_error():
    with pytest.raises(ValueError):
        normalize_playlist_id("abc123")


def test_none_levanta_value_error():
    # Implementação levanta ValueError para tipo inválido.
    with pytest.raises(ValueError):
        normalize_playlist_id(None)  # type: ignore[arg-type]


def test_caracteres_invalidos_nao_match():
    # String com 22 chars mas com traço no meio: regex não acha 22 válidos
    # consecutivos, então deve falhar.
    invalid = "abc-def-ghi-jkl-mno-pq"  # 22 chars com traços
    with pytest.raises(ValueError):
        normalize_playlist_id(invalid)


def test_extrai_22_validos_quando_embutidos():
    # String maior contendo 22 chars válidos deve extrair esse trecho.
    extra = f"garbage---{_ID}---more"
    assert normalize_playlist_id(extra) == _ID


def test_normalize_playlist_id_preferencia_uri_canonica_quando_presente():
    # S10: quando há URI/URL canônica presente, extrair o ID canônico
    # e não um pseudo-ID de 22 chars que aparece antes no lixo.
    sid = "cccccccccccccccccccccc"  # 22 c's (ID canônico desejado)
    garbage = "xxxxxxxxxxxxxxxxxxxxxx"  # 22 x's — outra sequência 22-char
    # Entrada com garbage + URI canônica → retorna ID da URI, não do garbage.
    assert normalize_playlist_id(f"{garbage} spotify:playlist:{sid}") == sid
    assert normalize_playlist_id(
        f"{garbage} https://open.spotify.com/playlist/{sid}"
    ) == sid
    # URI canônica pura continua funcionando.
    assert normalize_playlist_id(f"spotify:playlist:{sid}") == sid
    # ID isolado: fallback permissivo.
    assert normalize_playlist_id(sid) == sid
