"""CLI da Maestra.

Arquitetura (v0.2.0 Task 0):
- cada subcomando vive em `cli/<grupo>.py` e registra seus parsers via
  decorador `@register`.
- `_build_parser()` coleta todos os registrars e monta o parser raiz.
- `main()` parseia args, instancia componentes core, e despacha para
  `args.func(args, **deps)`.
"""
from __future__ import annotations

import argparse
import sys
from typing import Callable

from maestra_ai.cli._common import (
    BASE_DIR,
    CONTEXT_PATH,
    DIRECTOR_DECISIONS_PATH,
    FEEDBACK_PROMPT_STATE_PATH,
    PLAYBACK_EVENTS_PATH,
    PLAYBACK_STATE_PATH,
    PLAYLIST_ID,
    TASTE_PATH,
    error,
)


_REGISTRARS: list[Callable[[argparse._SubParsersAction], None]] = []


def register(fn: Callable[[argparse._SubParsersAction], None]) -> Callable:
    """Decorador: registra função que adiciona subparsers ao parser raiz."""
    _REGISTRARS.append(fn)
    return fn


def _import_subcommands() -> None:
    """Importa os módulos de subcomando para que seus @register rodem."""
    from maestra_ai.cli import (  # noqa: F401
        auth,
        basic,
        context as context_cmd,
        curate,
        director,
        feedback,
        flow,
        history,
        onboard,
        playback,
        playlist,
        taste,
    )
    _ = (auth, basic, context_cmd, curate, director, feedback, flow, history,
         onboard, playback, playlist, taste)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="maestra",
        description="Spotify Controller para Iris",
    )
    parser.add_argument("--human", "-H", action="store_true",
                        help="Saída legível em vez de JSON")
    subparsers = parser.add_subparsers(dest="command", required=True)

    _import_subcommands()
    for fn in _REGISTRARS:
        fn(subparsers)
    return parser


def _build_deps(args: argparse.Namespace) -> dict:
    """Instancia todos os componentes core e devolve como kwargs de dispatch."""
    from maestra_ai.core.client import SpotifyController
    from maestra_ai.core.context import ContextState
    from maestra_ai.core.curator import Curator
    from maestra_ai.core.director import MusicDirector
    from maestra_ai.core.feedback_prompt import FeedbackPrompter
    from maestra_ai.core.flow import FlowAnalyzer
    from maestra_ai.core.history import HistoryAnalyzer
    from maestra_ai.core.playback import PlaybackObserver
    from maestra_ai.core.playback_processor import PlaybackEventProcessor
    from maestra_ai.core.taste import TasteProfile

    try:
        controller = SpotifyController()
    except Exception as e:
        error(f"Falha ao conectar com Spotify: {e}", "AUTH_ERROR")

    taste = TasteProfile(TASTE_PATH)
    context_state = ContextState(CONTEXT_PATH)
    playback_observer = PlaybackObserver(PLAYBACK_STATE_PATH, PLAYBACK_EVENTS_PATH)
    playback_processor = PlaybackEventProcessor(PLAYBACK_EVENTS_PATH, taste)
    feedback_prompter = FeedbackPrompter(FEEDBACK_PROMPT_STATE_PATH)
    history_analyzer = HistoryAnalyzer(controller)
    flow_analyzer = FlowAnalyzer(taste)
    curator = Curator(controller, taste)
    director = MusicDirector(
        controller,
        curator,
        taste,
        context_state,
        DIRECTOR_DECISIONS_PATH,
        PLAYLIST_ID,
        history_analyzer=history_analyzer,
    )

    return {
        "controller": controller,
        "taste": taste,
        "curator": curator,
        "context_state": context_state,
        "playback_observer": playback_observer,
        "playback_processor": playback_processor,
        "feedback_prompter": feedback_prompter,
        "history_analyzer": history_analyzer,
        "flow_analyzer": flow_analyzer,
        "director": director,
    }


def main(argv: list[str] | None = None) -> int:
    old_argv = None
    if argv is not None:
        old_argv = sys.argv
        sys.argv = ["maestra", *argv]
    try:
        parser = _build_parser()
        args = parser.parse_args()

        # Subcomandos com short-circuit (stubs v0.1.x) definem
        # args.skip_deps=True via set_defaults para não instanciar deps.
        if getattr(args, "skip_deps", False):
            result = args.func(args)
        else:
            deps = _build_deps(args)
            result = args.func(args, **deps)
        return int(result) if result is not None else 0
    finally:
        if old_argv is not None:
            sys.argv = old_argv


if __name__ == "__main__":
    sys.exit(main())
