"""Subcomando `context`: set, show, clear."""
from __future__ import annotations

import argparse
import re

from maestra_ai.cli import register
from maestra_ai.cli._common import output

_BPM_PATTERN = re.compile(r"^(\d{2,3})-(\d{2,3})$")


def _parse_bpm_flag(raw: str) -> dict:
    """Parseia formato N-N para BPM (ex: 60-100).

    Retorna dict com 'min' e 'max', ambos inteiros.
    Levanta ValueError se formato inválido ou min >= max.
    """
    m = _BPM_PATTERN.match(raw)
    if not m:
        raise ValueError(
            f"formato de --bpm inválido: {raw!r} (esperado N-N, ex: 60-100)"
        )
    lo = int(m.group(1))
    hi = int(m.group(2))
    if lo >= hi:
        raise ValueError(f"min deve ser < max: {raw!r}")
    return {"min": lo, "max": hi}


def cmd_context_set(args, context_state, **_):
    bpm = None
    if getattr(args, "bpm", None):
        try:
            bpm = _parse_bpm_flag(args.bpm)
        except ValueError as e:
            output({"error": str(e)}, getattr(args, "human", False))
            return
    result = context_state.set(
        args.context, bpm=bpm, ttl_minutes=args.ttl
    )
    output({"status": "set", **result}, args.human)


def cmd_context_show(args, context_state, **_):
    result = context_state.show()
    if result is None:
        output({"status": "unset", "context": None}, args.human)
        return
    output({"status": "active", **result}, args.human)


def cmd_context_clear(args, context_state, **_):
    output(context_state.clear(), args.human)


def cmd_context_clear_bpm(args, context_state, **_):
    """Remove BPM target sem mexer no texto do contexto."""
    result = context_state.clear_bpm()
    output(result, getattr(args, "human", False))


@register
def _register(subparsers: argparse._SubParsersAction) -> None:
    from maestra_ai.cli import group_help_handler
    context_parser = subparsers.add_parser("context", help="Contexto musical ativo")
    context_parser.set_defaults(func=group_help_handler(context_parser))
    sub = context_parser.add_subparsers(dest="context_command", required=False)

    p = sub.add_parser("set", help="Define o contexto ativo")
    p.add_argument("context", help="Contexto: foco, energia, revisão, etc.")
    p.add_argument("--ttl", type=int, default=120, help="Validade em minutos")
    p.add_argument(
        "--bpm",
        help="Target de BPM como N-N (ex: 60-100)",
    )
    p.set_defaults(func=cmd_context_set)

    p = sub.add_parser("show", help="Mostra o contexto ativo")
    p.set_defaults(func=cmd_context_show)

    p = sub.add_parser("clear", help="Limpa o contexto ativo")
    p.set_defaults(func=cmd_context_clear)

    p = sub.add_parser("clear-bpm", help="Remove BPM target sem mexer no texto")
    p.set_defaults(func=cmd_context_clear_bpm, skip_deps=True)
