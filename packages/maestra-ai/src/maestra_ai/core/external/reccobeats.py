"""Fonte Reccobeats — audio features completas via API aberta.

Endpoint: https://api.reccobeats.com/v1/
- Lookup 2-step: ISRC via /v1/track → rb_id → /v1/audio-features
- Sem API key, sem Cloudflare, batch por múltiplos IDs em 1 request
- Rate limit conservador: 1 req/s via Lock + monotonic

Substitui o endpoint de audio features do Spotify (depreciado em 2024).
"""
from __future__ import annotations

import json
import logging
import threading
import time
import urllib.parse
import urllib.request
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from maestra_ai.core.external.types import SourceResult, TrackInfo

logger = logging.getLogger(__name__)

_API_BASE = "https://api.reccobeats.com"
_MIN_INTERVAL_SECONDS = 1.0  # conservador


class ReccoBeatsSource:
    """Cliente `EnhancementSource` para Reccobeats.

    Reccobeats é grátis, sem API key — sempre `is_configured() → True`.
    Lookup é 2-step: ISRC → rb_id → audio_features. Para batches,
    a implementação atual faz uma chamada por faixa; otimização em batch
    pode vir via enhance_many custom se houver necessidade.
    """

    name = "reccobeats"

    def __init__(self, *, user_agent: str | None = None) -> None:
        self._user_agent = user_agent or "maestra-ai"
        self._lock = threading.Lock()
        self._last_request_at: float = float("-inf")

    def is_configured(self) -> bool:
        return True

    def _respect_rate_limit(self) -> None:
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_request_at
            if elapsed < _MIN_INTERVAL_SECONDS:
                time.sleep(_MIN_INTERVAL_SECONDS - elapsed)
            self._last_request_at = time.monotonic()

    def _get(self, path: str, params: dict) -> dict | None:
        url = f"{_API_BASE}{path}?{urllib.parse.urlencode(params)}"
        try:
            self._respect_rate_limit()
            req = urllib.request.Request(
                url,
                headers={"User-Agent": self._user_agent, "Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            logger.debug("reccobeats GET %s failed: %s", path, exc)
            return None

    def _resolve_rb_id(self, isrc: str) -> str | None:
        data = self._get("/v1/track", {"ids": isrc})
        if not data:
            return None
        content = data.get("content") or []
        for t in content:
            if t.get("isrc") == isrc:
                return t.get("id")
        return None

    def enhance_track(self, track: TrackInfo) -> SourceResult | None:
        isrc = track.get("isrc")
        if not isrc:
            return None
        rb_id = self._resolve_rb_id(isrc)
        if not rb_id:
            return None
        data = self._get("/v1/audio-features", {"ids": rb_id})
        if not data:
            return None
        content = data.get("content") or []
        if not content:
            return None
        feats = content[0]
        try:
            tempo = float(feats.get("tempo") or 0)
        except (ValueError, TypeError):
            return None
        if tempo <= 0:
            return None
        return {
            "reccobeats": {
                "tempo": tempo,
                "key": int(feats.get("key") or 0),
                "mode": int(feats.get("mode") or 0),
                "loudness": float(feats.get("loudness") or 0),
                "acousticness": float(feats.get("acousticness") or 0),
                "danceability": float(feats.get("danceability") or 0),
                "energy": float(feats.get("energy") or 0),
                "instrumentalness": float(feats.get("instrumentalness") or 0),
                "liveness": float(feats.get("liveness") or 0),
                "speechiness": float(feats.get("speechiness") or 0),
                "valence": float(feats.get("valence") or 0),
            },
            "match_method": "isrc",
        }
