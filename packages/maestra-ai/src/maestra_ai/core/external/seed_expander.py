"""Expande seed de artistas via Last.fm similar, com cache TTL 60d."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from maestra_ai.core.external import cache as cache_mod

if TYPE_CHECKING:
    from maestra_ai.core.external.lastfm import LastfmSource

_TTL_DAYS = 60


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _is_stale(fetched_at: str) -> bool:
    try:
        fetched = datetime.fromisoformat(fetched_at)
    except (ValueError, TypeError):
        return True
    return datetime.now() - fetched > timedelta(days=_TTL_DAYS)


class SeedExpander:
    """Gera seeds expandidos por similaridade. Consulta cache primeiro."""

    def __init__(self, *, lastfm_source: LastfmSource | None, limit: int = 10) -> None:
        self._lastfm = lastfm_source
        self._limit = limit

    def expand(self, artist_names: list[str]) -> list[str]:
        """Retorna lista deduplicada de artistas similares aos `artist_names`.

        - Cache hit (dentro do TTL): usa valor cacheado.
        - Miss ou stale: chama Last.fm e grava.
        - Sem Last.fm configurado: retorna [] (fallback silencioso).
        """
        if self._lastfm is None:
            return []

        seen: set[str] = set()
        result: list[str] = []
        cache = cache_mod.load_cache()
        dirty = False

        for artist in artist_names:
            key = artist.lower()
            entry = cache["similar_artists"].get(key)
            if entry and not _is_stale(entry.get("fetched_at", "")):
                similars = entry["similars"]
            else:
                similars = self._lastfm.get_similar_artists(artist, limit=self._limit)
                cache["similar_artists"][key] = {
                    "similars": similars,
                    "fetched_at": _now_iso(),
                }
                dirty = True

            for s in similars:
                if s not in seen:
                    seen.add(s)
                    result.append(s)

        if dirty:
            cache_mod.save_cache(cache)
        return result
