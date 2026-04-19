"""Subcomando `taste`: show, review, feedback, context-map."""
from __future__ import annotations

import argparse

from maestra_ai.cli import register
from maestra_ai.cli._common import (
    _context_review,
    _curation_context,
    _prune_candidates,
    output,
    resolve_playlist_id,
    taste_summary,
)


def cmd_taste_show(args, taste, **_):
    output(taste_summary(taste), args.human)


def cmd_taste_review(args, controller, taste, context_state, **_):
    playlist_id = resolve_playlist_id()
    context, context_source = _curation_context(args, context_state)
    tracks = controller.playlist_tracks(playlist_id)
    review = _context_review(
        tracks,
        taste,
        context,
        prune_candidates=_prune_candidates(tracks, taste, context),
        top=args.top,
    )
    output({
        "context_source": context_source,
        **review,
    }, args.human)


def cmd_taste_feedback(args, taste, context_state, **_):
    active_context = context_state.show()
    context = args.context
    context_source = "argument"
    if context is None and active_context:
        context = active_context["context"]
        context_source = "active"

    taste.record_feedback(
        args.uri,
        args.feedback,
        context=context,
        source=args.source,
        global_feedback=args.global_feedback,
    )
    output({
        "status": "recorded",
        "uri": args.uri,
        "feedback": args.feedback,
        "context": context,
        "context_source": context_source if context else None,
        "source": args.source,
        "global": args.global_feedback or context is None,
    }, args.human)


def cmd_taste_context_map(args, taste, **_):
    output(taste.data.get("context_queries", {}), args.human)


@register
def _register(subparsers: argparse._SubParsersAction) -> None:
    from maestra_ai.cli import group_help_handler
    taste_parser = subparsers.add_parser("taste", help="Perfil de gosto")
    taste_parser.set_defaults(func=group_help_handler(taste_parser))
    sub = taste_parser.add_subparsers(dest="taste_command", required=False)

    p = sub.add_parser("show", help="Resumo do perfil")
    p.set_defaults(func=cmd_taste_show)

    p = sub.add_parser("review", help="Revisão contextual da playlist e dos sinais")
    p.add_argument("--context", help="Contexto para revisar; usa contexto ativo se omitido")
    p.add_argument("--top", type=int, default=10, help="Quantidade de itens por seção")
    p.set_defaults(func=cmd_taste_review)

    p = sub.add_parser("feedback", help="Registra feedback")
    p.add_argument("uri", help="URI da faixa")
    p.add_argument("feedback", choices=["good", "bad", "skip"])
    p.add_argument("--context", help="Contexto em que o feedback vale")
    p.add_argument("--source", default="explicit",
                   choices=["explicit", "implicit", "listened_to_end", "replay"])
    p.add_argument("--global", dest="global_feedback", action="store_true",
                   help="Registra feedback global, mesmo com contexto")
    p.set_defaults(func=cmd_taste_feedback)

    p = sub.add_parser("context-map", help="Mapeamento contexto→busca")
    p.set_defaults(func=cmd_taste_context_map)
