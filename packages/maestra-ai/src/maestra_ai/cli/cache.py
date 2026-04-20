"""Subcomando `cache`: refresh do cache externo."""
from __future__ import annotations

import argparse

from maestra_ai.cli import register
from maestra_ai.cli._common import output
from maestra_ai.core.external import cache as cache_mod


def cmd_cache_refresh(args, **_):
    """Remove entries do cache para forçar re-fetch na próxima ação.

    Sem flags: limpa tudo. `--uri X`: limpa só a entry X. `--source X`:
    zera apenas a sub-chave da fonte em todas as entries (mantém o
    cache de outras fontes).
    """
    cache = cache_mod.load_cache()

    if args.uri:
        cache["tracks"].pop(args.uri, None)
    elif args.source:
        for entry in cache["tracks"].values():
            if args.source in entry.get("sources", []):
                entry[args.source] = None
                entry["sources"] = [s for s in entry["sources"] if s != args.source]
    else:
        cache["tracks"] = {}

    cache_mod.save_cache(cache)
    output(
        {
            "status": "refreshed",
            "source": args.source,
            "uri": args.uri,
            "tracks_remaining": len(cache["tracks"]),
        },
        getattr(args, "human", False),
    )


@register
def _register(subparsers: argparse._SubParsersAction) -> None:
    from maestra_ai.cli import group_help_handler
    cache_parser = subparsers.add_parser(
        "cache", help="Cache de metadata externa",
    )
    cache_parser.set_defaults(func=group_help_handler(cache_parser))
    sub = cache_parser.add_subparsers(dest="cache_command", required=False)

    p = sub.add_parser("refresh", help="Força re-fetch na próxima ação")
    p.add_argument("--source", help="Limpa só esta fonte (musicbrainz, etc)")
    p.add_argument("--uri", help="Limpa só esta URI Spotify")
    p.add_argument("--human", action="store_true")
    p.set_defaults(func=cmd_cache_refresh, skip_deps=True)
