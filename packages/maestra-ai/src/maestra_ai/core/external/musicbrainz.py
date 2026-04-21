"""Fonte MusicBrainz — gêneros canônicos via ISRC (fallback name+artist).

Rate limit de 1 req/s gerenciado pela própria lib via `set_rate_limit`.
Gêneros são buscados diretamente via HTTP porque `musicbrainzngs 0.7.1` não
inclui "genres" em VALID_INCLUDES para artist, lançando InvalidIncludeError.
Sem API key — apenas User-Agent identificável (requisito do TOS).
"""
from __future__ import annotations

import json
import logging
import threading
import time
import urllib.request
from typing import TYPE_CHECKING

import musicbrainzngs

if TYPE_CHECKING:
    from maestra_ai.core.external.types import SourceResult, TrackInfo

logger = logging.getLogger(__name__)

# v0.9.0-alpha.2 G5: whitelist de keywords para promover tags do MB
# que parecem gênero para o campo `genres` efetivo. Filtro conservador —
# exclui tokens curtos/ambíguos. Revisar ocasionalmente conforme feedback.
GENRE_KEYWORDS = frozenset({
    "rock", "pop", "jazz", "electronic", "folk", "metal", "punk",
    "hip hop", "rap", "classical", "ambient", "indie", "alternative",
    "soul", "funk", "blues", "reggae", "country", "r&b", "rnb",
    "techno", "house", "trance", "edm", "experimental", "shoegaze",
    "grunge", "disco", "gospel", "latin",
})


def _promoted_genres_from_tags(tags: list[str]) -> list[str]:
    """Retorna subconjunto de `tags` que parecem gênero (match em GENRE_KEYWORDS).

    Deduplicação preserva ordem. Tags não promovidas NÃO são retornadas —
    elas continuam existindo na lista de tags do artista para uso futuro
    (mood, contexto).
    """
    seen: set[str] = set()
    promoted: list[str] = []
    for tag in tags:
        if not tag:
            continue
        lowered = tag.lower()
        if any(kw in lowered for kw in GENRE_KEYWORDS):
            if lowered not in seen:
                seen.add(lowered)
                promoted.append(tag)
    return promoted


_USER_AGENT_APP = "maestra-ai"
_USER_AGENT_CONTACT = "https://github.com/mencoding/maestra-ai"

# Lock + timestamp para rate limiting do helper HTTP (1 req/s, independente da lib)
_http_rate_lock = threading.Lock()
_http_last_request_time: float = 0.0

_MB_API_BASE = "https://musicbrainz.org/ws/2"


class MusicBrainzSource:
    """Cliente `EnhancementSource` para MusicBrainz."""

    name = "musicbrainz"

    def __init__(self, *, app_version: str) -> None:
        musicbrainzngs.set_useragent(
            _USER_AGENT_APP, app_version, _USER_AGENT_CONTACT,
        )
        musicbrainzngs.set_rate_limit(limit_or_interval=1.0, new_requests=1)
        # User-Agent idêntico ao que a lib monta internamente
        self._user_agent = f"{_USER_AGENT_APP}/{app_version} ({_USER_AGENT_CONTACT})"

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

    def artist_exists(self, name: str) -> bool:
        """Retorna True se houver match forte para o nome de artista no MusicBrainz.

        Usa search_artists com score >= 85 como critério. Fallback gracioso
        (retorna True) em caso de erro/timeout — evita penalizar usuário por
        instabilidade da API externa.
        """
        if not name or not name.strip():
            return False
        try:
            resp = musicbrainzngs.search_artists(artist=name, limit=1)
        except Exception as e:
            logger.debug("MB artist_exists falhou para %s: %s", name, e)
            return True  # fallback gracioso: não rejeitar por falha de rede
        artists = resp.get("artist-list") or []
        if not artists:
            return False
        top = artists[0]
        try:
            score = int(top.get("ext:score", 0))
        except (ValueError, TypeError):
            score = 0
        return score >= 85

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
        # Tags via lib (includes=["tags"] funciona em musicbrainzngs 0.7.1)
        tags: list[str] = []
        try:
            response = musicbrainzngs.get_artist_by_id(mbid, includes=["tags"])
            artist = response.get("artist", {})
            tags = [t["name"] for t in (artist.get("tag-list") or []) if t.get("name")]
        except Exception as e:
            logger.debug("MB artist (tags) lookup falhou para %s: %s", mbid, e)

        # Gêneros via HTTP direto — musicbrainzngs 0.7.1 não suporta inc=genres
        genres = self._fetch_artist_genres_http(mbid)

        # G5: promove tags que parecem gênero e faz merge com gêneros HTTP
        promoted = _promoted_genres_from_tags(tags)
        seen: set[str] = set()
        effective_genres: list[str] = []
        for g in list(genres) + promoted:
            lowered = g.lower()
            if lowered not in seen:
                seen.add(lowered)
                effective_genres.append(g)

        return effective_genres, tags

    def _fetch_artist_genres_http(self, mbid: str) -> list[str]:
        """Busca gêneros do artista via HTTP direto na API REST do MusicBrainz.

        Necessário porque `musicbrainzngs 0.7.1` não expõe "genres" em
        VALID_INCLUDES para artist, lançando InvalidIncludeError ao tentar
        usar a lib normalmente.

        Rate limit: 1 req/s via lock + timestamp monotônico.
        Retorna [] em caso de qualquer erro (rede, HTTP, JSON inválido).
        """
        global _http_last_request_time

        url = f"{_MB_API_BASE}/artist/{mbid}?inc=genres&fmt=json"
        req = urllib.request.Request(url, headers={"User-Agent": self._user_agent})

        # Aplica rate limit de 1 req/s independente do scheduler da lib
        with _http_rate_lock:
            now = time.monotonic()
            elapsed = now - _http_last_request_time
            if elapsed < 1.0:
                time.sleep(1.0 - elapsed)
            _http_last_request_time = time.monotonic()

        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read())
            return [g["name"] for g in (data.get("genres") or []) if g.get("name")]
        except Exception as e:
            logger.debug("MB artist (genres HTTP) falhou para %s: %s", mbid, e)
            return []

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
