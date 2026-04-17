"""Rollback: restaura snapshot após gravar estado atual como salvaguarda."""
from __future__ import annotations

from typing import Callable

from maestra_ai.core import snapshot
from maestra_ai.core.errors import NotFoundError


def rollback_to(
    snap_id: str | None,
    *,
    current_state_fn: Callable[[], dict],
    apply_state_fn: Callable[[dict], None],
) -> dict:
    """Restaura estado do snapshot. Se snap_id=None, usa o mais recente.

    Antes de aplicar, faz snapshot do estado ATUAL (rollback-do-rollback).
    `apply_state_fn` recebe o dict do snapshot-alvo e deve aplicá-lo
    aos módulos relevantes (taste, context, playlist, …).
    """
    target = snap_id or snapshot.last()
    if not target:
        raise NotFoundError("Nenhum snapshot disponível para rollback.")

    current = current_state_fn()
    safety_id = snapshot.create("safety-before-rollback", current)

    state = snapshot.load(target)
    apply_state_fn(state)

    return {
        "restored": target,
        "safety_snapshot": safety_id,
        "status": "ok",
    }
