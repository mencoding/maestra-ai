"""Parser puro de contexto musical livre para ParsedContext estruturada.

Módulo sem dependências do core — só stdlib. Consumido por ContextState
(memoização) e por Curator (_build_informed_query, _apply_negative_filter).

Issue #8, v0.13.
"""
from __future__ import annotations

import re
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
    """
    if not text:
        return ParsedContext(text="", bpm=bpm)

    negative: list[str] = []
    positive: list[str] = []
    artists_hint: list[str] = []

    for clause in _split_clauses(text):
        neg_rest = _extract_after_marker(clause, NEGATIVE_MARKERS)
        pos_rest = _extract_after_marker(clause, POSITIVE_MARKERS)

        # Negativos têm prioridade sobre positivos em caso de conflito
        if neg_rest is not None:
            first = neg_rest.split()[0] if neg_rest.split() else ""
            if first:
                negative.append(first)
            continue  # não processa positivo nesta cláusula

        if pos_rest is not None:
            # Para artists_hint: coleta palavras capitalizadas da cláusula
            caps = _extract_artists(clause, pos_rest)
            artists_hint.extend(caps)
            # Para positive: primeiro token do rest (pode ser "rock", "lo-fi", etc.)
            first = pos_rest.split()[0] if pos_rest.split() else ""
            if first and first[0].islower():
                positive.append(first)

    return ParsedContext(
        text=text,
        positive=tuple(positive),
        negative=tuple(negative),
        artists_hint=tuple(artists_hint),
        bpm=bpm,
    )
