"""Subcomando rollback.

Usa `skip_deps=True` para evitar exigir auth do Spotify em operações
puramente locais (list/restore). Instancia taste e context_state
diretamente, sem passar pelo SpotifyController.
"""
from __future__ import annotations

import argparse
import json

from maestra_ai.cli import register
from maestra_ai.cli._common import CONTEXT_PATH, TASTE_PATH
from maestra_ai.core import rollback, snapshot
from maestra_ai.core.context import ContextState
from maestra_ai.core.taste import TasteProfile


def _handle(args: argparse.Namespace) -> int:
    if args.list:
        print(json.dumps(snapshot.list_snapshots(), indent=2, ensure_ascii=False))
        return 0

    taste = TasteProfile(TASTE_PATH)
    context_state = ContextState(CONTEXT_PATH)

    def current_state_fn() -> dict:
        return {
            "taste": taste.data,
            "context": context_state.show(),
        }

    def apply_state_fn(state: dict) -> None:
        if "taste" in state and state["taste"] is not None:
            taste.restore(state["taste"])
        if "context" in state:
            ctx = state["context"]
            if ctx and isinstance(ctx, dict) and ctx.get("context"):
                ttl = ctx.get("ttl_minutes", 120)
                context_state.set(ctx["context"], ttl_minutes=ttl)
            else:
                context_state.clear()

    result = rollback.rollback_to(
        args.snapshot,
        current_state_fn=current_state_fn,
        apply_state_fn=apply_state_fn,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


@register
def _register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("rollback", help="Restaura snapshot anterior.")
    group = p.add_mutually_exclusive_group()
    group.add_argument("--list", action="store_true", help="Lista snapshots disponíveis.")
    group.add_argument("--snapshot", help="ID específico do snapshot.")
    group.add_argument("--last", dest="snapshot", action="store_const", const=None,
                       help="Restaura o mais recente (default).")
    p.set_defaults(func=_handle, list=False, snapshot=None, skip_deps=True)
