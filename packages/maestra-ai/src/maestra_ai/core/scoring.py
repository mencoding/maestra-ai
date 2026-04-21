"""Componentes e composição do score de curadoria v0.10.

Componentes puros (tag_similarity, decade_match, bpm_proximity) +
effective_weights (degradação graciosa quando sinal falta) + compose_score +
anti_tag_penalty (penalidade para tags negadas em modo degraded).
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Pesos de penalidade
# ---------------------------------------------------------------------------

W_ANTI_TAG: float = 0.4  # calibrar após primeira semana de uso (issue #13)


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


def anti_tag_penalty(
    track_tags: set[str],
    negative_tags: set[str],
    *,
    degraded: bool,
) -> float:
    """Penalty negativa para candidatos com tag negada, ativa só em modo degraded.

    Retorna 0.0 quando:
    - degraded=False (hard filter já tratou, não penalizar duas vezes).
    - Sem overlap entre track_tags e negative_tags.

    Escala: proporcional ao overlap, limitado em 3 tags pra evitar crescimento
    descontrolado. Fórmula: -W_ANTI_TAG * min(overlap_count, 3) / 3.
    """
    if not degraded or not negative_tags:
        return 0.0
    overlap = len(track_tags & negative_tags)
    if overlap == 0:
        return 0.0
    capped = min(overlap, 3)
    return -W_ANTI_TAG * (capped / 3)
