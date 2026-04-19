"""Subcomando `flow`: review."""
from __future__ import annotations

import argparse

from maestra_ai.cli import register
from maestra_ai.cli._common import _curation_context, output


def cmd_flow_review(args, context_state, flow_analyzer, **_):
    context, context_source = _curation_context(args, context_state)
    result = flow_analyzer.review(
        context,
        window=args.window,
        streak_threshold=args.streak_threshold,
        negative_rate_threshold=args.negative_rate_threshold,
    )
    output({"context_source": context_source, **result}, args.human)


@register
def _register(subparsers: argparse._SubParsersAction) -> None:
    from maestra_ai.cli import group_help_handler
    flow_parser = subparsers.add_parser("flow", help="Analisa saúde do fluxo musical")
    flow_parser.set_defaults(
        func=group_help_handler(flow_parser), skip_deps=True,
    )
    sub = flow_parser.add_subparsers(dest="flow_command", required=False)

    p = sub.add_parser("review", help="Detecta deriva negativa por sequência/taxa")
    p.add_argument("--context", help="Contexto para revisar; usa contexto ativo se omitido")
    p.add_argument("--window", type=int, default=10, help="Quantidade de sinais recentes a considerar")
    p.add_argument("--streak-threshold", type=int, default=3, help="Sequência negativa para alerta")
    p.add_argument("--negative-rate-threshold", type=float, default=0.3, help="Taxa negativa para alerta")
    p.set_defaults(func=cmd_flow_review)
