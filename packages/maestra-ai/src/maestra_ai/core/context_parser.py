"""Parser puro de contexto musical livre para ParsedContext estruturada.

Módulo sem dependências do core — só stdlib. Consumido por ContextState
(memoização) e por Curator (_build_informed_query, _apply_negative_filter).

Issue #8, v0.13.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


NEGATIVE_MARKERS: tuple[str, ...] = ("evitar ", "sem ", "não ", "nao ")


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


def parse(text: str, bpm: dict | None = None) -> ParsedContext:
    """Extrai intenção estruturada de texto livre.

    Puro, idempotente, determinístico. Nenhum I/O, nenhum logging.
    """
    if not text:
        return ParsedContext(text="", bpm=bpm)

    negative: list[str] = []
    for clause in _split_clauses(text):
        rest = _extract_after_marker(clause, NEGATIVE_MARKERS)
        if rest:
            # Pega o primeiro termo (primeira "palavra-chave" do rest)
            first_token = rest.split()[0] if rest.split() else ""
            if first_token:
                negative.append(first_token)

    return ParsedContext(
        text=text,
        negative=tuple(negative),
        bpm=bpm,
    )
