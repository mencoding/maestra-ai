"""Helpers de config específicos para MCP."""
from __future__ import annotations


def resolve_playlist_id() -> str | None:
    # Retorna playlist_id a partir do config persistido, ou None se ausente.
    from maestra_ai.core import storage
    cfg = storage.read_config()
    return cfg.get("playlist_id")
