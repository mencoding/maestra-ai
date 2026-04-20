"""Agregador read-only do perfil: taste + rationale + state."""
from __future__ import annotations

import json
from typing import Any

from maestra_ai.core import storage
from maestra_ai.core.config import any_source_enabled


def _load_json(path) -> dict | None:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _build_external_block() -> dict:
    """Agrega estatísticas de uso de fontes externas."""
    from maestra_ai.core.external import cache as ext_cache

    cfg = storage.read_config()
    enabled = any_source_enabled(cfg)

    if not enabled:
        return {"enabled": False}

    cache = ext_cache.load_cache()
    tracks = cache.get("tracks", {})
    total = len(tracks)
    with_mb_genres = sum(
        1 for t in tracks.values()
        if t.get("musicbrainz") and t["musicbrainz"].get("genres")
    )
    return {
        "enabled": True,
        "musicbrainz": {
            "tracks_total": total,
            "tracks_with_genres": with_mb_genres,
        },
    }


def build_profile_view() -> dict[str, Any]:
    """Monta dict com estado atual + sinais do onboard + contadores do taste.

    Lê três fontes: init state, taste_profile.json, onboard_rationale.json.
    Todas opcionais — chaves faltantes viram zero/lista vazia/None.
    """
    from maestra_ai.core.init import detect_state

    state = detect_state()

    taste_data = _load_json(storage.data_dir() / "taste_profile.json") or {}
    tracks = taste_data.get("tracks", {}) or {}
    contexts = list((taste_data.get("context_queries") or {}).keys())

    good = sum(1 for t in tracks.values() if t.get("feedback") == "good")
    bad = sum(1 for t in tracks.values() if t.get("feedback") == "bad")

    rationale_data = _load_json(
        storage.state_dir() / "onboard_rationale.json",
    ) or {}
    suggestions_raw = rationale_data.get("suggestions") or []
    suggestions = [
        {
            "text": s.get("text") or "",
            "genres": (s.get("based_on") or {}).get("genres") or [],
            "decades": (s.get("based_on") or {}).get("decades") or [],
            "artists": (s.get("based_on") or {}).get("artists") or [],
            "track_count": len(s.get("contributing_tracks") or []),
        }
        for s in suggestions_raw
    ]

    external = _build_external_block()

    return {
        "state": state,
        "total_tracks": len(tracks),
        "feedback": {"good": good, "bad": bad},
        "contexts": contexts,
        "suggestions": suggestions,
        "last_analysis_at": rationale_data.get("generated_at"),
        "external": external,
    }
