"""Helpers de configuração do core.

Centraliza utilitários puros de parsing/normalização que precisam ser
compartilhados entre CLI, MCP e core — evita duplicação inline de regex
em múltiplos módulos.
"""
from __future__ import annotations

import re

# ID Spotify = 22 caracteres base62.
# Regex canônica: prefere URIs/URLs oficiais para evitar que lixo de 22
# chars antes da URI seja capturado pelo fallback permissivo (S10).
_PLAYLIST_CANONICAL_RE = re.compile(
    r"(?:spotify:playlist:|open\.spotify\.com/playlist/)([a-zA-Z0-9]{22})"
)
_PLAYLIST_ID_RE = re.compile(r"[a-zA-Z0-9]{22}")


def normalize_playlist_id(value: str) -> str:
    """Extrai o ID canônico de 22 chars base62 de um identificador Spotify.

    Aceita:
    - ID puro (`37i9dQZF1DXcBWIGoYBM5M`)
    - URI (`spotify:playlist:<ID>`)
    - URL (`https://open.spotify.com/playlist/<ID>?si=...`)

    Quando a entrada contém uma URI/URL canônica, o ID dela é preferido
    sobre qualquer outra sequência de 22 chars base62 presente na string
    (evita capturar lixo que apareça antes da URI). Caso não haja forma
    canônica, cai no fallback permissivo (primeiro match de 22 base62).

    Levanta ValueError se o valor for vazio, não-string ou não contiver
    22 caracteres base62 consecutivos.
    """
    if not value or not isinstance(value, str):
        raise ValueError(f"playlist vazia ou tipo inválido: {value!r}")
    canonical = _PLAYLIST_CANONICAL_RE.search(value)
    if canonical:
        return canonical.group(1)
    fallback = _PLAYLIST_ID_RE.search(value)
    if fallback:
        return fallback.group(0)
    raise ValueError(f"formato de playlist inválido: {value!r}")
