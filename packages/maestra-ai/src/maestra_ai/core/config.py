"""Helpers de configuração do core.

Centraliza utilitários puros de parsing/normalização que precisam ser
compartilhados entre CLI, MCP e core — evita duplicação inline de regex
em múltiplos módulos.
"""
from __future__ import annotations

import re

# ID Spotify = 22 caracteres base62.
_PLAYLIST_ID_RE = re.compile(r"[a-zA-Z0-9]{22}")


def normalize_playlist_id(value: str) -> str:
    """Extrai o ID canônico de 22 chars base62 de um identificador Spotify.

    Aceita:
    - ID puro (`37i9dQZF1DXcBWIGoYBM5M`)
    - URI (`spotify:playlist:<ID>`)
    - URL (`https://open.spotify.com/playlist/<ID>?si=...`)

    Levanta ValueError se o valor for vazio, não-string ou não contiver
    22 caracteres base62 consecutivos.
    """
    if not value or not isinstance(value, str):
        raise ValueError(f"playlist vazia ou tipo inválido: {value!r}")
    m = _PLAYLIST_ID_RE.search(value)
    if not m:
        raise ValueError(f"formato de playlist inválido: {value!r}")
    return m.group(0)
