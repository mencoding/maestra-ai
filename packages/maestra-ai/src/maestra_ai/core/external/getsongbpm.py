"""Fonte GetSongBPM — BPM, key, time signature.

API pública: https://api.getsongbpm.com/search/?api_key=X&type=both&lookup=...
JSON plano; rate limit 60 req/min (janela deslizante). HTTP direto via
urllib.request, padrão estabelecido para fontes externas em v0.9.
"""
from __future__ import annotations

import json
import logging
import threading
import time
import urllib.parse
import urllib.request
from collections import deque
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from maestra_ai.core.external.types import SourceResult, TrackInfo

logger = logging.getLogger(__name__)

_API_BASE = "https://api.getsongbpm.com"
_MAX_REQS_PER_MINUTE = 60
_WINDOW_SECONDS = 60


class GetSongBpmSource:
    """Cliente `EnhancementSource` para GetSongBPM."""

    name = "getsongbpm"

    def __init__(self, *, api_key: str) -> None:
        self._api_key = api_key
        self._lock = threading.Lock()
        self._timestamps: deque[float] = deque()

    def is_configured(self) -> bool:
        return bool(self._api_key)

    def enhance_track(self, track: TrackInfo) -> SourceResult | None:
        return self._lookup(track)

    def _respect_rate_limit(self) -> None:
        with self._lock:
            now = time.monotonic()
            # Drop timestamps fora da janela
            while self._timestamps and now - self._timestamps[0] > _WINDOW_SECONDS:
                self._timestamps.popleft()
            if len(self._timestamps) >= _MAX_REQS_PER_MINUTE:
                wait = _WINDOW_SECONDS - (now - self._timestamps[0])
                if wait > 0:
                    time.sleep(wait)
                self._timestamps.popleft()
            self._timestamps.append(time.monotonic())

    def _lookup(self, track: TrackInfo) -> SourceResult | None:
        artists = track.get("artists") or []
        if not artists or not track.get("name"):
            return None
        lookup = f"song:{track['name']} artist:{artists[0]}"
        params = urllib.parse.urlencode({"api_key": self._api_key, "type": "both", "lookup": lookup})
        url = f"{_API_BASE}/search/?{params}"
        try:
            self._respect_rate_limit()
            req = urllib.request.Request(url, headers={"User-Agent": "maestra-ai"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            logger.debug("getsongbpm lookup failed for %s: %s", lookup, exc)
            return None
        song = payload.get("song") if isinstance(payload, dict) else None
        if not isinstance(song, dict):
            return None
        try:
            tempo = float(song.get("tempo") or 0)
        except (ValueError, TypeError):
            tempo = 0.0
        if tempo <= 0:
            return None
        return {
            "bpm": {
                "bpm": tempo,
                "key": str(song.get("key_of") or ""),
                "time_signature": str(song.get("time_sig") or ""),
            }
        }
