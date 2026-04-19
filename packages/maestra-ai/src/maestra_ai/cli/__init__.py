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
import json
import sys
from collections.abc import Callable

from maestra_ai.cli._common import (
    CONTEXT_PATH,
    DIRECTOR_DECISIONS_PATH,
    FEEDBACK_PROMPT_STATE_PATH,
    PLAYBACK_EVENTS_PATH,
    PLAYBACK_STATE_PATH,
    TASTE_PATH,
    resolve_playlist_id,
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
        curate,
        director,
        doctor,
        feedback,
        flow,
        history,
        onboard,
        playback,
        playlist,
        rollback,
        taste,
    )
    from maestra_ai.cli import (
        config as config_cmd,
    )
    from maestra_ai.cli import (
        context as context_cmd,
    )
    from maestra_ai.cli import (
        help as help_cmd,
    )
    _ = (auth, basic, config_cmd, context_cmd, curate, director, doctor,
         feedback, flow, help_cmd, history, onboard, playback, playlist,
         rollback, taste)


def _build_parser() -> argparse.ArgumentParser:
    try:
        from rich_argparse import RichHelpFormatter
        formatter_class = RichHelpFormatter
    except ImportError:
        formatter_class = argparse.HelpFormatter

    parser = argparse.ArgumentParser(
        prog="maestra",
        description="Spotify controller com curadoria contextual para agentes de IA.",
        formatter_class=formatter_class,
    )
    parser.add_argument("--human", "-H", action="store_true",
                        help="Saída legível em vez de JSON")
    parser.add_argument("--json", action="store_true",
                        help="Força saída estruturada em JSON (erros e resultados).")
    # required=False: quando rodado sem subcomando, main() intercepta e
    # mostra quickstart em vez do wall-of-text do argparse help.
    subparsers = parser.add_subparsers(dest="command", required=False)

    _import_subcommands()
    for fn in _REGISTRARS:
        fn(subparsers)
    return parser


_QUICKSTART_BANNER = """\
Maestra AI — Spotify controller para agentes de IA.

Primeira vez?
  maestra help onboarding       Fluxo completo de bootstrap (OAuth + perfil)
  maestra doctor                Diagnóstico do ambiente
  maestra --help                Lista todos os 28 subcomandos

Já autenticado?
  maestra onboard               Bootstrap do perfil por histórico
  maestra now                   O que está tocando
  maestra director start        Curador musical em background

Guias: maestra help mcp | maestra help onboarding
"""


def _print_quickstart_banner() -> None:
    try:
        from rich.console import Console
        from rich.panel import Panel
        Console().print(Panel.fit(
            _QUICKSTART_BANNER.rstrip(),
            title="[bold]maestra[/bold]",
            border_style="cyan",
        ))
    except ImportError:
        print(_QUICKSTART_BANNER)


def _print_rich_error(err: dict) -> None:
    try:
        from rich.console import Console
        from rich.panel import Panel
        console = Console()
        body = (
            f"[bold]O que aconteceu:[/bold]\n   {err['what_happened']}\n\n"
            f"[bold]Causa provável:[/bold]\n"
            + "\n".join(f"   • {c}" for c in err["probable_causes"])
            + "\n\n[bold]O que fazer:[/bold]\n"
            + "\n".join(
                f"   {i+1}. {a['command']} — {a['description']}"
                for i, a in enumerate(err["suggested_actions"])
            )
        )
        console.print(Panel(body, title=f"✗ {err['title']}", border_style="red"))
    except ImportError:
        print(f"✗ {err['title']}: {err['what_happened']}")


def _build_deps(args: argparse.Namespace) -> dict:
    """Instancia todos os componentes core e devolve como kwargs de dispatch."""
    from maestra_ai.core.client import SpotifyController
    from maestra_ai.core.context import ContextState
    from maestra_ai.core.curator import Curator
    from maestra_ai.core.director import MusicDirector
    from maestra_ai.core.errors import AuthError, ConfigError, MaestraError
    from maestra_ai.core.feedback_prompt import FeedbackPrompter
    from maestra_ai.core.flow import FlowAnalyzer
    from maestra_ai.core.history import HistoryAnalyzer
    from maestra_ai.core.playback import PlaybackObserver
    from maestra_ai.core.playback_processor import PlaybackEventProcessor
    from maestra_ai.core.taste import TasteProfile
    try:
        controller = SpotifyController()
    except MaestraError:
        raise
    except Exception as e:
        raise AuthError(f"Falha ao conectar com Spotify: {e}") from e

    taste = TasteProfile(TASTE_PATH)
    context_state = ContextState(CONTEXT_PATH)
    playback_observer = PlaybackObserver(PLAYBACK_STATE_PATH, PLAYBACK_EVENTS_PATH)
    playback_processor = PlaybackEventProcessor(PLAYBACK_EVENTS_PATH, taste)
    feedback_prompter = FeedbackPrompter(FEEDBACK_PROMPT_STATE_PATH)
    history_analyzer = HistoryAnalyzer(controller)
    flow_analyzer = FlowAnalyzer(taste)
    curator = Curator(controller, taste)
    # Subcomandos como auth, doctor, onboard podem rodar sem playlist_id.
    # Validação individual fica a cargo do caller que realmente precisa.
    try:
        playlist_id = resolve_playlist_id()
    except ConfigError:
        playlist_id = None
    director = MusicDirector(
        controller,
        curator,
        taste,
        context_state,
        DIRECTOR_DECISIONS_PATH,
        playlist_id,
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

        # Sem subcomando → quickstart banner (não o wall-of-text do argparse).
        if not getattr(args, "command", None):
            _print_quickstart_banner()
            return 0

        # Subcomandos com short-circuit (stubs v0.1.x) definem
        # args.skip_deps=True via set_defaults para não instanciar deps.
        from maestra_ai.core.errors import MaestraError
        try:
            if getattr(args, "skip_deps", False):
                result = args.func(args)
            else:
                deps = _build_deps(args)
                result = args.func(args, **deps)
            return int(result) if result is not None else 0
        except MaestraError as e:
            # Redact consolidado: cobre what_happened, title, where e body.
            # Fecha P0-R1 (bypass via str(SpotifyException) em what_happened).
            from maestra_ai.core.security import redact_error_dict
            err_dict = redact_error_dict(e.to_human_dict())
            if getattr(args, "json", False):
                print(json.dumps({"error": err_dict}, indent=2, ensure_ascii=False))
            else:
                _print_rich_error(err_dict)
            return 2
    finally:
        if old_argv is not None:
            sys.argv = old_argv


if __name__ == "__main__":
    sys.exit(main())
