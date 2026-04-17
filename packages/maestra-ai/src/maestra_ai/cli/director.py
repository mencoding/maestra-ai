"""Subcomando `director`: once, run, start, stop, status."""
from __future__ import annotations

import argparse
import os
import signal as _signal
import subprocess
import sys
import time

from maestra_ai.cli import register
from maestra_ai.cli._common import (
    BASE_DIR,
    DIRECTOR_PID_PATH,
    DIRECTOR_STDOUT_LOG_PATH,
    _pid_running,
    output,
)


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
    os.makedirs(os.path.dirname(DIRECTOR_PID_PATH), exist_ok=True)
    if os.path.exists(DIRECTOR_PID_PATH):
        with open(DIRECTOR_PID_PATH, "r", encoding="utf-8") as f:
            pid = int(f.read().strip())
        if _pid_running(pid):
            output({"status": "running", "pid": pid}, args.human)
            return

    cmd = [
        sys.executable,
        "-m",
        "maestra_ai.cli",
        "director",
        "run",
        "--interval", str(args.interval),
        "--count", str(args.count),
        "--target", str(args.target),
        "--import-outside", args.import_outside,
        "--outside-min-plays", str(args.outside_min_plays),
        "--outside-count", str(args.outside_count),
        "--outside-recent-limit", str(args.outside_recent_limit),
        "--max-per-artist", str(args.max_per_artist),
        "--max-artist-share", str(args.max_artist_share),
    ]
    with open(DIRECTOR_STDOUT_LOG_PATH, "a", encoding="utf-8") as log:
        process = subprocess.Popen(
            cmd,
            stdout=log,
            stderr=log,
            start_new_session=True,
            cwd=BASE_DIR,
        )
    with open(DIRECTOR_PID_PATH, "w", encoding="utf-8") as f:
        f.write(str(process.pid))
    output({
        "status": "started",
        "pid": process.pid,
        "mode": "playlist-buffer",
        "interval": args.interval,
        "count": args.count,
        "target": args.target,
        "import_outside": args.import_outside,
        "outside_min_plays": args.outside_min_plays,
        "max_per_artist": args.max_per_artist,
        "max_artist_share": args.max_artist_share,
    }, args.human)


def cmd_director_stop(args, **_):
    if not os.path.exists(DIRECTOR_PID_PATH):
        output({"status": "stopped", "message": "Director não estava rodando."}, args.human)
        return

    with open(DIRECTOR_PID_PATH, "r", encoding="utf-8") as f:
        pid = int(f.read().strip())
    if _pid_running(pid):
        os.kill(pid, _signal.SIGTERM)
    os.remove(DIRECTOR_PID_PATH)
    output({"status": "stopped", "pid": pid}, args.human)


def cmd_director_status(args, **_):
    if not os.path.exists(DIRECTOR_PID_PATH):
        output({"status": "stopped"}, args.human)
        return
    with open(DIRECTOR_PID_PATH, "r", encoding="utf-8") as f:
        pid = int(f.read().strip())
    if _pid_running(pid):
        output({"status": "running", "pid": pid, "mode": "playlist-buffer"}, args.human)
        return
    os.remove(DIRECTOR_PID_PATH)
    output({"status": "stopped", "stale_pid": pid}, args.human)


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
