"""Filtro de tags Last.fm para remover ruído (meta-tags, avaliativos).

Complemento puro do enhancer. Input: lista bruta de dicts do pylast
(cada item com keys `name` e `count`). Output: set de tags normalizadas,
filtradas por relevância.

Issue #8, v0.13.
"""
from __future__ import annotations


META_TAGS: frozenset[str] = frozenset({
    # Décadas
    "1950s", "1960s", "1970s", "1980s", "1990s", "2000s", "2010s", "2020s",
    # Países / nacionalidade
    "american", "british", "french", "german", "japanese", "brazilian",
    "italian", "spanish", "swedish", "norwegian", "canadian", "australian",
    "irish", "finnish", "dutch", "polish", "russian", "chinese", "korean",
    # Avaliativos / vazios
    "awesome", "favorite", "favourite", "good", "great", "amazing",
    "best", "love", "loved", "cool", "nice", "music", "songs", "song",
    "seen live",
})


def filter_lastfm_tags(raw: list[dict], *, top_n: int = 10) -> set[str]:
    """Retorna set de tags significativas (normalizadas, sem meta-tags).

    - `raw`: lista de dicts com `name` (obrigatório) e `count` (opcional, default 0).
    - `top_n`: corta pelo top `top_n` ordenado por `count` desc depois do filter.
    """
    if not raw:
        return set()

    # Normaliza (lowercase + strip) e filtra meta-tags
    normalized = []
    for item in raw:
        name = (item.get("name") or "").strip().lower()
        if not name or name in META_TAGS:
            continue
        count = item.get("count") or 0
        normalized.append((name, count))

    # Ordena por count desc, pega top_n, deduplica pelo set
    normalized.sort(key=lambda x: x[1], reverse=True)
    top = normalized[:top_n]
    return {name for name, _ in top}
