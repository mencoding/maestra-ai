"""Parser puro de contexto musical livre para ParsedContext estruturada.

Módulo sem dependências do core — só stdlib. Consumido por ContextState
(memoização) e por Curator (_build_informed_query, _apply_negative_filter).

Issue #8, v0.13.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


NEGATIVE_MARKERS: tuple[str, ...] = ("evitar ", "sem ", "não ", "nao ")

# Ordenados do mais longo para o mais curto: "algo tipo " deve ser testado
# antes de "tipo " para evitar match parcial incorreto em "algo tipo X".
POSITIVE_MARKERS: tuple[str, ...] = (
    "algo tipo ",
    "parecido com ",
    "tipo ",
    "como ",
    "mais ",
)


@dataclass(frozen=True)
class ParsedContext:
    text: str
    positive: tuple[str, ...] = ()
    negative: tuple[str, ...] = ()
    artists_hint: tuple[str, ...] = ()
    bpm: dict | None = None


def _normalize_for_match(text: str) -> str:
    """NFKC + casefold pra match determinístico, invariante a acento/case."""
    return unicodedata.normalize("NFKC", text).casefold()


def _split_clauses(text: str) -> list[str]:
    """Quebra por vírgula, ponto, ponto-e-vírgula. Retorna fragmentos limpos."""
    return [c.strip() for c in re.split(r"[,.;]", text) if c.strip()]


def _extract_after_marker(clause: str, markers: tuple[str, ...]) -> str | None:
    """Se clause começa com um marker, retorna o resto. Caso contrário, None."""
    for marker in markers:
        idx = clause.find(marker)
        if idx >= 0:
            return clause[idx + len(marker):].strip()
    return None


def _extract_artists(original_clause: str, term: str) -> list[str]:
    """Se o term extraído começa com maiúscula(s), considera artista.

    Recebe o original_clause (não normalizado) e o term já extraído.
    Procura a sequência capitalizada começando na posição do term.
    """
    # Regex: sequência de palavras capitalizadas (cada uma começa maiúscula)
    pattern = r"\b([A-Z][A-Za-z]*(?:\s+[A-Z][A-Za-z]*)*)\b"
    matches = re.findall(pattern, original_clause)
    return [m for m in matches if len(m) > 1]


def parse(text: str, bpm: dict | None = None) -> ParsedContext:
    """Extrai intenção estruturada de texto livre.

    Puro, idempotente, determinístico. Nenhum I/O, nenhum logging.
    O matching é feito sobre texto normalizado (NFKC + casefold); o texto
    original é preservado em ParsedContext.text.
    """
    if not text:
        return ParsedContext(text="", bpm=bpm)

    # Markers normalizados (computados uma vez para comparação)
    neg_markers_norm = tuple(_normalize_for_match(m) for m in NEGATIVE_MARKERS)
    pos_markers_norm = tuple(_normalize_for_match(m) for m in POSITIVE_MARKERS)

    negative: list[str] = []
    positive: list[str] = []
    artists_hint: list[str] = []

    for clause in _split_clauses(text):
        clause_norm = _normalize_for_match(clause)

        neg_rest_norm = _extract_after_marker(clause_norm, neg_markers_norm)
        pos_rest_norm = _extract_after_marker(clause_norm, pos_markers_norm)

        # Negativos têm prioridade sobre positivos em caso de conflito
        if neg_rest_norm is not None:
            first = neg_rest_norm.split()[0] if neg_rest_norm.split() else ""
            if first:
                negative.append(first)
            continue  # não processa positivo nesta cláusula

        if pos_rest_norm is not None:
            # Para artists_hint: coleta palavras capitalizadas do clause ORIGINAL
            # (clause_norm perde as maiúsculas; artistas precisam de capitalização)
            caps = _extract_artists(clause, pos_rest_norm)
            artists_hint.extend(caps)
            # Para positive: primeiro token do rest normalizado
            first = pos_rest_norm.split()[0] if pos_rest_norm.split() else ""
            if first and first[0].islower():
                positive.append(first)

    return ParsedContext(
        text=text,
        positive=tuple(positive),
        negative=tuple(negative),
        artists_hint=tuple(artists_hint),
        bpm=bpm,
    )
