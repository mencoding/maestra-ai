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


# Type alias exportado para anotações.
PlaylistSelector = Callable[[list[OwnPlaylist], ExpansionContext], list[str]]
