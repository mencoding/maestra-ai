"""Subcomando `feedback`: suggest, mark-prompted."""
from __future__ import annotations

import argparse

from maestra_ai.cli import register
from maestra_ai.cli._common import _active_context_value, error, output


def cmd_feedback_suggest(args, taste, context_state, feedback_prompter, **_):
    context = args.context or _active_context_value(context_state)
    output(feedback_prompter.suggest(taste, context=context), args.human)


def cmd_feedback_mark_prompted(args, context_state, feedback_prompter, **_):
    context = args.context or _active_context_value(context_state)
    if not context:
        error("Nenhum contexto informado ou ativo.", "NO_CONTEXT")
    output(feedback_prompter.mark_prompted(context), args.human)


@register
def _register(subparsers: argparse._SubParsersAction) -> None:
    feedback_parser = subparsers.add_parser("feedback", help="Sugere microperguntas de feedback")
    sub = feedback_parser.add_subparsers(dest="feedback_command", required=True)

    p = sub.add_parser("suggest", help="Sugere se vale perguntar algo ao usuário")
    p.add_argument("--context", help="Contexto a avaliar; usa contexto ativo se omitido")
    p.set_defaults(func=cmd_feedback_suggest)

    p = sub.add_parser("mark-prompted", help="Registra que a pergunta foi feita")
    p.add_argument("--context", help="Contexto perguntado; usa contexto ativo se omitido")
    p.set_defaults(func=cmd_feedback_mark_prompted)
