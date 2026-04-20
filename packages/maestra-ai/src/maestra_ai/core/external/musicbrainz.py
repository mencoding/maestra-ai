"""Fonte MusicBrainz — gêneros canônicos via ISRC (fallback name+artist).

Rate limit de 1 req/s gerenciado pela própria lib via `set_rate_limit`.
Sem API key — apenas User-Agent identificável (requisito do TOS).
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import musicbrainzngs

if TYPE_CHECKING:
    from maestra_ai.core.external.types import SourceResult, TrackInfo

logger = logging.getLogger(__name__)

_USER_AGENT_APP = "maestra-ai"
_USER_AGENT_CONTACT = "https://github.com/mencoding/maestra-ai"


class MusicBrainzSource:
    """Cliente `EnhancementSource` para MusicBrainz."""

    name = "musicbrainz"

    def __init__(self, *, app_version: str) -> None:
        musicbrainzngs.set_useragent(
            _USER_AGENT_APP, app_version, _USER_AGENT_CONTACT,
        )
        musicbrainzngs.set_rate_limit(limit_or_interval=1.0, new_requests=1)

    def is_configured(self) -> bool:
        return True

    def enhance_track(self, track: TrackInfo) -> SourceResult | None:
        isrc = track.get("isrc")
        if isrc:
            result = self._lookup_by_isrc(isrc)
            if result is not None:
                return result
        name = track.get("name") or ""
        artists = track.get("artists") or []
        if name and artists:
            return self._lookup_by_name(name, artists[0])
        return None

    def _lookup_by_isrc(self, isrc: str) -> SourceResult | None:
        try:
            response = musicbrainzngs.get_recordings_by_isrc(isrc)
        except Exception as e:
            logger.debug("MB ISRC lookup falhou para %s: %s", isrc, e)
            return None
        recordings = response.get("recording-list") or []
        if not recordings:
            return None
        recording = recordings[0]
        recording_mbid = recording.get("id", "")
        artist_mbid = _extract_first_artist_mbid(recording)
        genres, tags = self._artist_genres_and_tags(artist_mbid) if artist_mbid else ([], [])
        return {
            "musicbrainz": {
                "mbid": recording_mbid,
                "genres": genres,
                "tags": tags,
            },
            "artist_mbid": artist_mbid or "",
            "match_method": "isrc",
        }

    def _artist_genres_and_tags(self, mbid: str) -> tuple[list[str], list[str]]:
        try:
            response = musicbrainzngs.get_artist_by_id(
                mbid, includes=["genres", "tags"],
            )
        except Exception as e:
            logger.debug("MB artist lookup falhou para %s: %s", mbid, e)
            return [], []
        artist = response.get("artist", {})
        genres = [g["name"] for g in (artist.get("genre-list") or []) if g.get("name")]
        tags = [t["name"] for t in (artist.get("tag-list") or []) if t.get("name")]
        return genres, tags


    def _lookup_by_name(self, name: str, artist: str) -> SourceResult | None:
        query = f'recording:"{name}" AND artist:"{artist}"'
        try:
            response = musicbrainzngs.search_recordings(query=query, limit=1)
        except Exception as e:
            logger.debug("MB name search falhou para %s/%s: %s", name, artist, e)
            return None
        recordings = response.get("recording-list") or []
        if not recordings:
            return None
        recording = recordings[0]
        recording_mbid = recording.get("id", "")
        artist_mbid = _extract_first_artist_mbid(recording)
        genres, tags = self._artist_genres_and_tags(artist_mbid) if artist_mbid else ([], [])
        return {
            "musicbrainz": {
                "mbid": recording_mbid,
                "genres": genres,
                "tags": tags,
            },
            "artist_mbid": artist_mbid or "",
            "match_method": "name",
        }


def _extract_first_artist_mbid(recording: dict) -> str:
    credits = recording.get("artist-credit") or []
    for credit in credits:
        if isinstance(credit, dict):
            artist = credit.get("artist") or {}
            mbid = artist.get("id")
            if mbid:
                return mbid
    return ""
