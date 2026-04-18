"""Subcomando `director`: once, run, start, stop, status."""
from __future__ import annotations

import argparse
import time

from maestra_ai.cli import register
from maestra_ai.cli._common import output


def cmd_director_once(args, director, **_):
    output(
        director.run_once(
            target=args.target,
            add_count=args.count,
            dry_run=args.dry_run,
            import_outside=args.import_outside,
            outside_min_plays=args.outside_min_plays,
            outside_count=args.outside_count,
            outside_recent_limit=args.outside_recent_limit,
            max_per_artist=args.max_per_artist,
            max_artist_share=args.max_artist_share,
        ),
        args.human,
    )


def cmd_director_run(args, director, **_):
    while True:
        director.run_once(
            target=args.target,
            add_count=args.count,
            import_outside=args.import_outside,
            outside_min_plays=args.outside_min_plays,
            outside_count=args.outside_count,
            outside_recent_limit=args.outside_recent_limit,
            max_per_artist=args.max_per_artist,
            max_artist_share=args.max_artist_share,
        )
        time.sleep(args.interval)


def cmd_director_start(args, **_):
    from maestra_ai.core import director as director_mod
    result = director_mod.start(
        interval=args.interval,
        target=args.target,
        max_per_artist=args.max_per_artist,
        max_artist_share=args.max_artist_share,
        import_outside=args.import_outside,
    )
    output(result, args.human)


def cmd_director_stop(args, **_):
    from maestra_ai.core import director as director_mod
    output(director_mod.stop(), args.human)


def cmd_director_status(args, **_):
    from maestra_ai.core import director as director_mod
    output(director_mod.status(), args.human)


def _add_director_args(p):
    p.add_argument("--count", type=int, default=2)
    p.add_argument("--target", type=int, default=40)
    p.add_argument("--import-outside", default="off", choices=["off", "safe"])
    p.add_argument("--outside-min-plays", type=int, default=2)
    p.add_argument("--outside-count", type=int, default=2)
    p.add_argument("--outside-recent-limit", type=int, default=50)
    p.add_argument("--max-per-artist", type=int, default=1)
    p.add_argument("--max-artist-share", type=float, default=0.25)


@register
def _register(subparsers: argparse._SubParsersAction) -> None:
    director_parser = subparsers.add_parser(
        "director", help="Diretor musical do repertorio contextual",
    )
    sub = director_parser.add_subparsers(dest="director_command", required=True)

    p = sub.add_parser("once", help="Executa um ciclo do director")
    _add_director_args(p)
    p.add_argument("--dry-run", action="store_true", help="Decide sem alterar playlist")
    p.set_defaults(func=cmd_director_once)
    # sobrescreve help do --count/--target com o da versão once
    # (os defaults são os mesmos, mantém UX).

    p = sub.add_parser("run", help="Loop interno usado por start")
    p.add_argument("--interval", type=int, default=180)
    _add_director_args(p)
    p.set_defaults(func=cmd_director_run)

    p = sub.add_parser("start", help="Inicia director em background")
    p.add_argument("--interval", type=int, default=180)
    _add_director_args(p)
    p.set_defaults(func=cmd_director_start)

    p = sub.add_parser("stop", help="Para director em background")
    p.set_defaults(func=cmd_director_stop)

    p = sub.add_parser("status", help="Mostra estado do director")
    p.set_defaults(func=cmd_director_status)
