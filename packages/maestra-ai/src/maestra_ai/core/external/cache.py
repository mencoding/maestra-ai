"""Cache persistente de metadata externa por URI Spotify.

Schema v1: {"version": 1, "tracks": {uri: EnhancedTrack}}. Lock + rename
atômico via `storage.atomic_write_json`.
"""
from __future__ import annotations

import json
from typing import Any, cast

from maestra_ai.core import storage
from maestra_ai.core.external.types import EnhancedTrack

CACHE_SCHEMA_VERSION = 1


def _cache_path():
    return storage.data_dir() / "external_cache.json"


def _default_cache() -> dict[str, Any]:
    return {"version": CACHE_SCHEMA_VERSION, "tracks": {}}


def load_cache() -> dict[str, Any]:
    """Carrega o cache; retorna default vazio se ausente ou corrompido."""
    path = _cache_path()
    if not path.exists():
        return _default_cache()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return _default_cache()
    if not isinstance(data, dict) or data.get("version") != CACHE_SCHEMA_VERSION:
        return _default_cache()
    data.setdefault("tracks", {})
    return data


def save_cache(cache: dict[str, Any]) -> None:
    """Persiste o cache completo com lock + rename atômico."""
    storage.ensure_dirs()
    storage.atomic_write_json(_cache_path(), cache)


def get_track(uri: str) -> EnhancedTrack | None:
    """Retorna `EnhancedTrack` se presente no cache; None caso contrário."""
    cache = load_cache()
    track = cache["tracks"].get(uri)
    if track is None:
        return None
    return cast(EnhancedTrack, track)


def put_track(track: EnhancedTrack) -> None:
    """Grava (ou atualiza) uma entry no cache."""
    cache = load_cache()
    cache["tracks"][track["uri"]] = track
    save_cache(cache)
