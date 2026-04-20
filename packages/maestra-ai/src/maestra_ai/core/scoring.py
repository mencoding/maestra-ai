"""Componentes e composição do score de curadoria v0.10.

Componentes puros (tag_similarity, decade_match, bpm_proximity) +
effective_weights (degradação graciosa quando sinal falta) + compose_score.
"""
from __future__ import annotations


def tag_similarity(tags_a: set[str], tags_b: set[str]) -> float:
    """Jaccard entre dois conjuntos de tags (case-insensitive)."""
    if not tags_a or not tags_b:
        return 0.0
    a = {t.lower() for t in tags_a}
    b = {t.lower() for t in tags_b}
    inter = len(a & b)
    union = len(a | b)
    if union == 0:
        return 0.0
    return inter / union


def decade_match(release_date: str | None, dominant_decades: set[str]) -> float:
    """1.0 se a década de `release_date` ∈ `dominant_decades`, senão 0.0.

    `release_date` aceita ISO-like ou só ano (Spotify envia variados).
    Década em formato "YYYYs" (ex: "2010s").
    """
    if not release_date or not dominant_decades:
        return 0.0
    try:
        year = int(release_date[:4])
    except (ValueError, TypeError):
        return 0.0
    decade = f"{(year // 10) * 10}s"
    return 1.0 if decade in dominant_decades else 0.0


def bpm_proximity(*, track_bpm: float | None, target: dict | None) -> float:
    """Proximidade do BPM da faixa à janela `target = {min, max}`.

    Dentro da janela → próximo de 1 (1.0 no centro). Fora com tolerância
    de 10 BPM em cada lado → fall-off linear até 0. Muito longe → 0.
    """
    if track_bpm is None or not target:
        return 0.0
    lo = target.get("min")
    hi = target.get("max")
    if lo is None or hi is None or hi <= lo:
        return 0.0
    center = (lo + hi) / 2
    half_range = (hi - lo) / 2 + 10
    if half_range <= 0:
        return 0.0
    distance = abs(track_bpm - center)
    prox = 1.0 - distance / half_range
    return max(0.0, prox)


def effective_weights(
    defaults: dict[str, float],
    *,
    has_lastfm: bool,
    has_bpm_target: bool,
    track_has_bpm: bool,
    has_decade: bool,
) -> dict[str, float]:
    """Redistribui pesos quando sinal indisponível → somam em taste."""
    w = dict(defaults)
    if not has_lastfm:
        w["taste"] += w["tag"]
        w["tag"] = 0.0
    if not has_bpm_target or not track_has_bpm:
        w["taste"] += w["bpm"]
        w["bpm"] = 0.0
    if not has_decade:
        w["taste"] += w["decade"]
        w["decade"] = 0.0
    return w


def compose_score(
    *,
    weights: dict[str, float],
    taste: float,
    tag: float,
    decade: float,
    bpm: float,
) -> float:
    """Combina componentes ponderados: taste ∈ [-1,1], outros ∈ [0,1]."""
    return (
        weights["taste"]  * taste
        + weights["tag"]    * tag
        + weights["decade"] * decade
        + weights["bpm"]    * bpm
    )
