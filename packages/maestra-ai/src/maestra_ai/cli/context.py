"""Subcomando `context`: set, show, clear."""
from __future__ import annotations

import argparse

from maestra_ai.cli import register
from maestra_ai.cli._common import output


def cmd_context_set(args, context_state, **_):
    result = context_state.set(args.context, ttl_minutes=args.ttl)
    output({"status": "set", **result}, args.human)


def cmd_context_show(args, context_state, **_):
    result = context_state.show()
    if result is None:
        output({"status": "unset", "context": None}, args.human)
        return
    output({"status": "active", **result}, args.human)


def cmd_context_clear(args, context_state, **_):
    output(context_state.clear(), args.human)


@register
def _register(subparsers: argparse._SubParsersAction) -> None:
    context_parser = subparsers.add_parser("context", help="Contexto musical ativo")
    sub = context_parser.add_subparsers(dest="context_command", required=True)

    p = sub.add_parser("set", help="Define o contexto ativo")
    p.add_argument("context", help="Contexto: foco, energia, revisão, etc.")
    p.add_argument("--ttl", type=int, default=120, help="Validade em minutos")
    p.set_defaults(func=cmd_context_set)

    p = sub.add_parser("show", help="Mostra o contexto ativo")
    p.set_defaults(func=cmd_context_show)

    p = sub.add_parser("clear", help="Limpa o contexto ativo")
    p.set_defaults(func=cmd_context_clear)
