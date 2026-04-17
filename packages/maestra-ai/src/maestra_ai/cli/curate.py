"""Subcomando `curate`: dry-run de curadoria."""
from __future__ import annotations

import argparse

from maestra_ai.cli import register
from maestra_ai.cli._common import _curation_context, error, output


def cmd_curate(args, curator, context_state, **_):
    context, _ = _curation_context(args, context_state)
    results, _ = curator.curate(context, count=args.count)
    if not results:
        error("Sem resultados para esse contexto.", "NO_RESULTS")
    output(results, args.human)


@register
def _register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("curate", help="Gera faixas sem adicionar (dry-run)")
    p.add_argument("context", nargs="?", default=None, help="Contexto")
    p.add_argument("--count", type=int, default=5)
    p.set_defaults(func=cmd_curate)
