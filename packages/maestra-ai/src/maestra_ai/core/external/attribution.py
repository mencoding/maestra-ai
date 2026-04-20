"""Bloco de atribuição com links clicáveis (OSC 8 via rich).

Seletivo: só renderiza fontes efetivamente usadas. Cumpre TOS do
GetSongBPM e dá visibilidade honesta às demais fontes gratuitas.
"""
from __future__ import annotations

_ATTRIBUTIONS = {
    "musicbrainz": ("MusicBrainz", "https://musicbrainz.org"),
    "lastfm": ("Last.fm", "https://www.last.fm/about"),
    "getsongbpm": ("GetSongBPM", "https://getsongbpm.com/about"),
}


def render_attribution(sources_used: list[str]) -> str:
    """Retorna string (rich markup) do bloco de atribuição.

    `sources_used` deve conter apenas nomes internos ("musicbrainz",
    "lastfm", "getsongbpm"). Nomes desconhecidos são ignorados.
    String vazia se não há fontes.

    Retorna inline com separador "·" e markup rich para links clicáveis.
    """
    if not sources_used:
        return ""
    parts = []
    for s in sources_used:
        if s in _ATTRIBUTIONS:
            name, url = _ATTRIBUTIONS[s]
            parts.append(f"[link={url}]{name}[/link]")
    if not parts:
        return ""
    return "Metadata: " + " · ".join(parts)
