"""Subcomando `playback`: observe, session-end, process-events."""
from __future__ import annotations

import argparse

from maestra_ai.cli import register
from maestra_ai.cli._common import _active_context_value, output


def cmd_playback_observe(args, controller, context_state, playback_observer, **_):
    result = playback_observer.observe(
        controller.now(),
        context=_active_context_value(context_state),
    )
    output(result, args.human)


def cmd_playback_session_end(args, context_state, playback_observer, **_):
    result = playback_observer.session_end(context=_active_context_value(context_state))
    output(result, args.human)


def cmd_playback_process_events(args, playback_processor, **_):
    output(playback_processor.process(), args.human)


@register
def _register(subparsers: argparse._SubParsersAction) -> None:
    playback_parser = subparsers.add_parser(
        "playback", help="Observa eventos conservadores de playback",
    )
    sub = playback_parser.add_subparsers(dest="playback_command", required=True)

    p = sub.add_parser("observe", help="Observa o playback atual e registra eventos")
    p.set_defaults(func=cmd_playback_observe)

    p = sub.add_parser("session-end", help="Registra encerramento neutro da sessão")
    p.set_defaults(func=cmd_playback_session_end)

    p = sub.add_parser("process-events", help="Converte eventos elegíveis em sinais contextuais")
    p.set_defaults(func=cmd_playback_process_events)
