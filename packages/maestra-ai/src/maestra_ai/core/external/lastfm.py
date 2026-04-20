"""Fonte Last.fm — tags folksonômicas ricas e artistas similares.

Via pylast. Rate limit ~5 req/s via Lock + monotonic. Sem ISRC direto na
API pública do Last.fm; lookup é sempre por nome (artista + track).
"""
from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING

import pylast

if TYPE_CHECKING:
    from maestra_ai.core.external.types import SourceResult, TrackInfo

logger = logging.getLogger(__name__)

_MIN_INTERVAL_SECONDS = 0.2  # 5 req/s


class LastfmSource:
    """Cliente `EnhancementSource` para Last.fm."""

    name = "lastfm"

    def __init__(self, *, api_key: str) -> None:
        self._network = pylast.LastFMNetwork(api_key=api_key)
        self._rate_lock = threading.Lock()
        # Inicializa com -inf para garantir que a primeira chamada nunca dorme
        self._last_request_at: float = float("-inf")

    def _respect_rate_limit(self) -> None:
        with self._rate_lock:
            now = time.monotonic()
            elapsed = now - self._last_request_at
            if elapsed < _MIN_INTERVAL_SECONDS:
                wait = _MIN_INTERVAL_SECONDS - elapsed
                time.sleep(wait)
            # Reutiliza `now` para o update; evita segunda chamada redundante
            self._last_request_at = now

    def _lookup(self, track: TrackInfo) -> SourceResult | None:
        """Busca por artista+track. Last.fm não aceita ISRC no lookup público."""
        artists = track.get("artists") or []
        if not artists or not track.get("name"):
            return None
        artist_name = artists[0]
        try:
            self._respect_rate_limit()
            lf_track = self._network.get_track(artist_name, track["name"])
            tags = [t.item.get_name() for t in lf_track.get_top_tags()]
            playcount = int(lf_track.get_playcount() or 0)
            listeners = int(lf_track.get_listener_count() or 0)
        except Exception as exc:  # noqa: BLE001 — pylast lança vários tipos
            logger.debug("lastfm lookup failed for %s - %s: %s", artist_name, track["name"], exc)
            return None
        return {
            "lastfm": {
                "top_tags": tags,
                "playcount": playcount,
                "listeners": listeners,
                "similar_artists": [],
            },
            "match_method": "name",
        }

    def get_similar_artists(self, artist_name: str, *, limit: int = 10) -> list[str]:
        """Retorna até `limit` artistas similares. Lista vazia em qualquer erro."""
        try:
            self._respect_rate_limit()
            artist = self._network.get_artist(artist_name)
            entries = artist.get_similar(limit=limit)
            return [e.item.get_name() for e in entries]
        except Exception as exc:  # noqa: BLE001
            logger.debug("lastfm get_similar failed for %s: %s", artist_name, exc)
            return []
