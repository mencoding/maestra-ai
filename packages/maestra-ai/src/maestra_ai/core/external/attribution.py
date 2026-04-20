"""Bloco de atribuição com links clicáveis (OSC 8 via rich).

Seletivo: só renderiza fontes efetivamente usadas. Cumpre TOS do
GetSongBPM e dá visibilidade honesta às demais fontes gratuitas.
"""
from __future__ import annotations

_SOURCES = {
    "musicbrainz": ("MusicBrainz", "https://musicbrainz.org/doc/About"),
    "lastfm": ("Last.fm", "https://www.last.fm/about"),
    "getsongbpm": ("GetSongBPM.com", "https://getsongbpm.com/about"),
}


def render_attribution(sources_used: list[str]) -> str:
    """Retorna string (rich markup) do bloco de atribuição.

    `sources_used` deve conter apenas nomes internos ("musicbrainz",
    "lastfm", "getsongbpm"). Nomes desconhecidos são ignorados.
    String vazia se não há fontes.
    """
    known = [s for s in sources_used if s in _SOURCES]
    if not known:
        return ""
    lines = ["\n[bold]Fontes usadas nesta curadoria:[/bold]"]
    for source in known:
        label, url = _SOURCES[source]
        lines.append(f"  • [link={url}]{label}[/link]")
    return "\n".join(lines) + "\n"
