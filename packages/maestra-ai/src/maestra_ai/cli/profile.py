"""Subcomando `profile`: visão agregada do perfil de gosto + última análise."""
from __future__ import annotations

import argparse

from maestra_ai.cli import register
from maestra_ai.cli._common import output
from maestra_ai.core.profile_view import build_profile_view


def cmd_profile_show(args, **_):
    view = build_profile_view()
    if not args.human:
        output(view, args.human)
        return

    print(f"Estado: {view['state']}")
    print(f"Faixas analisadas: {view['total_tracks']}")
    fb = view["feedback"]
    print(f"Feedback: {fb['good']} positivos / {fb['bad']} negativos")
    if view["contexts"]:
        print(f"Contextos: {', '.join(view['contexts'])}")
    if view["last_analysis_at"]:
        print(f"Última análise: {view['last_analysis_at']}")

    suggestions = view["suggestions"]
    if suggestions:
        print("\nSugestões de contexto:")
        for i, s in enumerate(suggestions, 1):
            print(f"  {i}. {s['text']}")
            bits = []
            if s["genres"]:
                bits.append(f"gêneros={', '.join(s['genres'])}")
            if s["decades"]:
                bits.append(f"décadas={', '.join(s['decades'])}")
            if s["artists"]:
                bits.append(f"artistas={', '.join(s['artists'])}")
            if bits:
                print(f"     [{' | '.join(bits)}]")
            if s["track_count"]:
                print(f"     ({s['track_count']} faixas contribuintes)")


@register
def _register(subparsers: argparse._SubParsersAction) -> None:
    from maestra_ai.cli import group_help_handler

    profile_parser = subparsers.add_parser(
        "profile", help="Perfil agregado (gosto + última análise)",
    )
    profile_parser.set_defaults(func=group_help_handler(profile_parser))
    sub = profile_parser.add_subparsers(dest="profile_command", required=False)

    p = sub.add_parser("show", help="Resumo do perfil e sugestões")
    p.add_argument("--human", action="store_true", help="Saída legível (default: JSON)")
    p.set_defaults(func=cmd_profile_show, skip_deps=True)
