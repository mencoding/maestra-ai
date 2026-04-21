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
class BpmRange:
    """Intervalo de BPM. Frozen pra ser hashable e coabitar com ParsedContext
    em caches por valor."""
    min: int | None = None
    max: int | None = None

    @classmethod
    def from_any(cls, value: BpmRange | dict | None) -> BpmRange | None:
        """Aceita BpmRange, dict com keys min/max, ou None. Normaliza para
        BpmRange. Usado por parse() e por ContextState.parsed() para ingress
        do formato {min, max} persistido em disco."""
        if value is None:
            return None
        if isinstance(value, cls):
            return value
        if isinstance(value, dict):
            return cls(min=value.get("min"), max=value.get("max"))
        raise TypeError(f"unsupported bpm type: {type(value).__name__}")


@dataclass(frozen=True)
class ParsedContext:
    text: str
    positive: tuple[str, ...] = ()
    negative: tuple[str, ...] = ()
    artists_hint: tuple[str, ...] = ()
    bpm: BpmRange | None = None


def _normalize_for_match(text: str) -> str:
    """NFKC + casefold pra match determinístico, invariante a acento/case."""
    return unicodedata.normalize("NFKC", text).casefold()


def _split_clauses(text: str) -> list[str]:
    """Quebra por vírgula, ponto, ponto-e-vírgula. Retorna fragmentos limpos."""
    return [c.strip() for c in re.split(r"[,.;]", text) if c.strip()]


def _extract_after_marker_pair(
    clause: str,
    clause_norm: str,
    markers_norm: tuple[str, ...],
) -> tuple[str, str] | None:
    """Tenta matchar algum marker (normalizado) em clause_norm e retorna
    (rest_norm, rest_original) stripped. Retorna None se nenhum marker bate.

    Pressupõe len(clause) == len(clause_norm), válido para ASCII e PT-BR
    (NFKC e casefold preservam comprimento para esses ranges). Se a
    invariante for violada (ex: 'İ'.casefold() = 'i̇', 2 chars), o fallback
    silencioso é usar clause_norm para ambos — sem crash, degradação leve.
    """
    for marker in markers_norm:
        idx = clause_norm.find(marker)
        if idx < 0:
            continue
        rest_start = idx + len(marker)
        if len(clause) == len(clause_norm):
            return clause_norm[rest_start:].strip(), clause[rest_start:].strip()
        # Fallback defensivo: índices não batem, usa o normalizado pros dois
        return clause_norm[rest_start:].strip(), clause_norm[rest_start:].strip()
    return None


def _extract_artists(original_clause: str) -> list[str]:
    """Extrai sequências capitalizadas do clause original (não normalizado).

    Regex: sequência de palavras capitalizadas (cada uma começa maiúscula).
    """
    pattern = r"\b([A-Z][A-Za-z]*(?:\s+[A-Z][A-Za-z]*)*)\b"
    matches = re.findall(pattern, original_clause)
    return [m for m in matches if len(m) > 1]


def parse(text: str, bpm: BpmRange | dict | None = None) -> ParsedContext:
    """Extrai intenção estruturada de texto livre.

    Puro, idempotente, determinístico. Nenhum I/O, nenhum logging.

    `bpm` aceita dict {min, max}, BpmRange ou None; normalizado para
    BpmRange internamente para preservar hashability do ParsedContext.
    """
    bpm_norm = BpmRange.from_any(bpm)

    if not text:
        return ParsedContext(text="", bpm=bpm_norm)

    neg_markers_norm = tuple(_normalize_for_match(m) for m in NEGATIVE_MARKERS)
    pos_markers_norm = tuple(_normalize_for_match(m) for m in POSITIVE_MARKERS)

    negative: list[str] = []
    positive: list[str] = []
    artists_hint: list[str] = []

    for clause in _split_clauses(text):
        clause_norm = _normalize_for_match(clause)

        neg = _extract_after_marker_pair(clause, clause_norm, neg_markers_norm)
        if neg is not None:
            _rest_norm, rest_orig = neg
            parts = rest_orig.split()
            if parts:
                negative.append(parts[0].casefold())
            continue

        pos = _extract_after_marker_pair(clause, clause_norm, pos_markers_norm)
        if pos is not None:
            _rest_norm, rest_orig = pos
            caps = _extract_artists(rest_orig)
            artists_hint.extend(caps)
            parts = rest_orig.split()
            # Só vira positive se primeiro token começa com minúscula no
            # texto original. Capitalizado = artist, tratado em _extract_artists.
            if parts and parts[0] and parts[0][0].islower():
                positive.append(parts[0].casefold())

    return ParsedContext(
        text=text,
        positive=tuple(positive),
        negative=tuple(negative),
        artists_hint=tuple(artists_hint),
        bpm=bpm_norm,
    )
