"""Subcomando rollback."""
from __future__ import annotations

import argparse
import json

from maestra_ai.cli import register
from maestra_ai.core import rollback, snapshot


def _handle(args: argparse.Namespace) -> int:
    if args.list:
        print(json.dumps(snapshot.list_snapshots(), indent=2, ensure_ascii=False))
        return 0
    try:
        result = rollback.rollback_to(
            args.snapshot,
            current_state_fn=_current_state,
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except Exception as e:
        print(json.dumps({"error": str(e)}, indent=2))
        return 1


def _current_state() -> dict:
    """Coleta estado atual — evolui conforme os módulos core crescem."""
    return {}


@register
def _register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("rollback", help="Restaura snapshot anterior.")
    group = p.add_mutually_exclusive_group()
    group.add_argument("--list", action="store_true", help="Lista snapshots disponíveis.")
    group.add_argument("--snapshot", help="ID específico do snapshot.")
    group.add_argument("--last", dest="snapshot", action="store_const", const=None,
                       help="Restaura o mais recente (default).")
    p.set_defaults(func=_handle, list=False, snapshot=None, skip_deps=True)
