"""Parser puro de contexto musical livre para ParsedContext estruturada.

Módulo sem dependências do core — só stdlib. Consumido por ContextState
(memoização) e por Curator (_build_informed_query, _apply_negative_filter).

Issue #8, v0.13.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ParsedContext:
    """Estrutura derivada do texto cru do contexto.

    - text: texto original preservado (sem normalização) para log/debug.
    - positive: termos após marker positivo ("tipo X", "como Y").
    - negative: termos após marker negativo ("evitar X", "sem Y").
    - artists_hint: nomes próprios capitalizados após marker positivo.
    - bpm: objeto {min, max} repassado do ContextState.
    """
    text: str
    positive: tuple[str, ...] = ()
    negative: tuple[str, ...] = ()
    artists_hint: tuple[str, ...] = ()
    bpm: dict | None = None


def parse(text: str, bpm: dict | None = None) -> ParsedContext:
    """Extrai intenção estruturada de texto livre.

    Puro, idempotente, determinístico. Nenhum I/O, nenhum logging.
    """
    return ParsedContext(text=text or "", bpm=bpm)
