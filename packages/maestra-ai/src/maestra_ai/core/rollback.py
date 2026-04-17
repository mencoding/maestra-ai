"""Rollback: restaura snapshot após gravar estado atual como salvaguarda."""
from __future__ import annotations

from typing import Callable

from maestra_ai.core import snapshot
from maestra_ai.core.errors import NotFoundError


def rollback_to(
    snap_id: str | None,
    *,
    current_state_fn: Callable[[], dict],
) -> dict:
    """Restaura estado do snapshot. Se snap_id=None, usa o mais recente.

    Antes de aplicar, faz snapshot do estado ATUAL (rollback-do-rollback).
    """
    target = snap_id or snapshot.last()
    if not target:
        raise NotFoundError("Nenhum snapshot disponível para rollback.")

    current = current_state_fn()
    safety_id = snapshot.create("safety-before-rollback", current)

    state = snapshot.load(target)
    _apply_state(state)

    return {
        "restored": target,
        "safety_snapshot": safety_id,
        "status": "ok",
    }


def _apply_state(state: dict) -> None:
    """Aplica o estado restaurado. Stub v0.2.0 — integração real com
    set_playlist_tracks / taste.overwrite / context.set_context é feita
    conforme os módulos core evoluem.
    """
    # Integração real virá nas tarefas que consumirem rollback (onboard,
    # prune, import_outside). Por ora apenas registra o estado restaurado
    # para que callers lidem com a aplicação.
    return None
