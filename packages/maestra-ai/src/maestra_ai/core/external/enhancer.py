"""Orquestrador de fontes externas + cache.

Não paraleliza em v0.9 (única fonte ativa é MB, com rate limit de 1 req/s).
Paralelismo via ThreadPoolExecutor entra em v0.10 quando há múltiplas fontes.
"""
from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Callable, Iterable
from datetime import datetime
from typing import cast

from maestra_ai.core.config import load_and_migrate
from maestra_ai.core.external import cache as cache_mod
from maestra_ai.core.external.types import (
    EnhancedTrack,
    EnhancementSource,
    SourceResult,
    TrackInfo,
)

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(dt.UTC).astimezone().replace(microsecond=0).isoformat()


class Enhancer:
    """Orquestra fontes ativas e gerencia cache."""

    def __init__(self, sources: list[EnhancementSource]):
        self._sources = sources

    def active_sources(self) -> list[str]:
        return [s.name for s in self._sources if s.is_configured()]

    def enhance_track(self, track: TrackInfo) -> EnhancedTrack:
        uri = track["uri"]
        cached = cache_mod.get_track(uri)
        if cached is not None:
            return cached

        merged: dict = {
            "uri": uri,
            "isrc": track.get("isrc"),
            "artist_mbid": None,
            "musicbrainz": None,
            "lastfm": None,
            "bpm": None,
            "sources": [],
            "enhanced_at": _now_iso(),
            "match_method": "isrc",
        }

        for source in self._sources:
            if not source.is_configured():
                continue
            try:
                result = source.enhance_track(track)
            except Exception as e:
                logger.warning(
                    "Source %s falhou para %s: %s", source.name, uri, e,
                )
                continue
            if result is None:
                continue
            _apply_source_result(merged, source.name, result)

        enhanced = cast(EnhancedTrack, merged)
        cache_mod.put_track(enhanced)
        return enhanced

    def enhance_many(
        self,
        tracks: Iterable[TrackInfo],
        *,
        progress_cb: Callable[[dict], None] | None = None,
    ) -> list[EnhancedTrack]:
        tracks_list = list(tracks)
        total = len(tracks_list)
        results: list[EnhancedTrack] = []
        for i, t in enumerate(tracks_list, 1):
            results.append(self.enhance_track(t))
            if progress_cb:
                progress_cb({
                    "step": i,
                    "total": total,
                    "name": "enhance",
                    "detail": f"{i}/{total}",
                })
        return results


def _apply_source_result(merged: dict, source_name: str, result: SourceResult) -> None:
    if source_name == "musicbrainz" and "musicbrainz" in result:
        merged["musicbrainz"] = result["musicbrainz"]
        if result.get("artist_mbid"):
            merged["artist_mbid"] = result["artist_mbid"]
        if result.get("match_method"):
            merged["match_method"] = result["match_method"]
    if source_name == "lastfm" and "lastfm" in result:
        merged["lastfm"] = result["lastfm"]
    if source_name == "getsongbpm" and "bpm" in result:
        merged["bpm"] = result["bpm"]
    merged["sources"].append(source_name)


def _load_cfg() -> dict:
    """Hook de carregamento — facilita mock em teste."""
    return load_and_migrate()


def default_enhancer() -> Enhancer:
    """Monta enhancer com sources habilitadas conforme config.

    v0.10: MusicBrainz + Last.fm (quando ativo + api_key presente).
    """
    from maestra_ai import __version__
    from maestra_ai.core.external.lastfm import LastfmSource
    from maestra_ai.core.external.musicbrainz import MusicBrainzSource

    cfg = _load_cfg()
    sources: list[EnhancementSource] = []

    ext = cfg.get("external_sources") or {}
    if ext.get("musicbrainz", {}).get("enabled"):
        sources.append(MusicBrainzSource(app_version=__version__))
    lf = ext.get("lastfm") or {}
    if lf.get("enabled") and lf.get("api_key"):
        sources.append(LastfmSource(api_key=lf["api_key"]))

    return Enhancer(sources=sources)
