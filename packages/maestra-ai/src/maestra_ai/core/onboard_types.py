"""Tipos compartilhados do fluxo de onboard (v0.6.0).

Mantidos fora de `onboard.py` para poderem ser importados por:
- Core (`onboard.py`) sem import circular
- CLI (`cli/onboard.py`) para anotações de selector
- MCP futuro (expor onboard como tool)
- Agentes externos consumindo via stubs
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Literal, TypedDict


class OwnPlaylist(TypedDict):
    """Uma playlist própria oferecida ao selector durante a expansão."""

    id: str
    name: str
    track_count: int


class ExpansionContext(TypedDict):
    """Contexto passado ao selector durante a expansão.

    - total_cap: teto desejado de faixas únicas (default 5000).
    - current_total: faixas únicas já coletadas antes da expansão
      (top_long + top_medium + top_short + saved + recent).
    - remaining: total_cap - current_total. Já calculado para evitar
      que cada selector recompute.
    """

    total_cap: int
    current_total: int
    remaining: int


class SelectedPlaylist(TypedDict):
    id: str
    name: str


class FailedPlaylist(TypedDict):
    id: str
    reason: str  # truncado em 80 chars


ExpansionReason = Literal[
    "ok",
    "selector_not_provided",
    "cap_already_reached",
    "no_own_playlists",
    "only_empty_playlists",
    "selector_returned_empty",
]


class ExpansionInfo(TypedDict):
    attempted: bool
    reason: ExpansionReason
    offered_playlists: int
    own_playlists_empty_count: int
    selected_playlists: list[SelectedPlaylist]
    tracks_added: int
    failed_playlists: list[FailedPlaylist]


class OnboardSignals(TypedDict):
    """Agregados brutos computados no onboard para consumo por CLI/MCP/agentes.

    - top_genres: lista (genero, peso_total) ordenada desc, limite 10.
    - dominant_decades: lista (decada, peso_total) ordenada desc, limite 3.
    - top_artists: lista (nome_artista, peso_total) ordenada desc, limite 10.

    Peso é float (afetado por adjustments do TasteProfile em v0.7.0).
    """

    top_genres: list[tuple[str, float]]
    dominant_decades: list[tuple[str, float]]
    top_artists: list[tuple[str, float]]


class TrackRationale(TypedDict):
    """Uma faixa que contribuiu para gerar uma sugestão."""

    uri: str
    name: str
    artist: str
    weight: float
    feedback: str | None  # "good"/"bad"/None (global, do TasteProfile)
    skip_count: int  # acumulado de skips registrados pelo TasteProfile


class RationaleEntry(TypedDict):
    """Por que uma sugestão específica apareceu no onboard."""

    text: str
    based_on: dict  # {"genres": [...], "decades": [...], "artists": [...]}
    contributing_tracks: list[TrackRationale]


# Type alias exportado para anotações.
PlaylistSelector = Callable[[list[OwnPlaylist], ExpansionContext], list[str]]
