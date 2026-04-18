"""Subcomando onboard — UX rich: progress, preview de custo, panel final."""
from __future__ import annotations

import argparse
import json

from maestra_ai.cli import register
from maestra_ai.core import onboard
from maestra_ai.core.reporting import format_estimate


def _preview() -> str:
    components = [
        ("Top tracks (3 janelas)", 3, "requests"),
        ("Saved tracks (até 1000)", 20, "requests"),
        ("Recently played", 1, "requests"),
    ]
    text, _ = format_estimate(components, unit="requests", bytes_per_unit=2000)
    return (
        "O onboard vai fazer:\n"
        f"{text}\n"
        "  Tempo estimado:     ~8s (rate-limited a 60 req/min)"
    )


def _prompt_playlist_name(default: str) -> str:
    try:
        from rich.prompt import Prompt
        return Prompt.ask("Nome da sua playlist Maestra", default=default)
    except ImportError:
        r = input(f"Nome da sua playlist Maestra [{default}]: ").strip()
        return r or default


def _print_report(report: dict) -> None:
    try:
        from rich.console import Console
        from rich.panel import Panel
        console = Console()
        body = (
            f"Playlist:         {report['playlist_name']} "
            f"({report.get('playlist_id') or '—'})\n"
            f"Top tracks:       long={report['top_long_count']} "
            f"medium={report['top_medium_count']} short={report['top_short_count']}\n"
            f"Saved tracks:     {report['saved_tracks_fetched']}\n"
            f"Recently played:  {report['recent_count']}\n"
            f"Faixas pontuadas: {report['unique_tracks_scored']}\n"
            f"Faixas semeadas:  {report['seeded']}\n\n"
            "[bold]Sugestões de contextos iniciais:[/bold]\n"
            + "\n".join(f"  • {s}" for s in report["context_suggestions"])
            + "\n\n"
            "Use: [cyan]maestra context set \"<contexto>\"[/] "
            "e depois [cyan]maestra curate[/]"
        )
        console.print(Panel(body, title="✓ Onboard concluído", border_style="green"))
    except ImportError:
        for k, v in report.items():
            print(f"  {k}: {v}")


def _handle(args: argparse.Namespace, controller, taste, **_) -> int:
    playlist_name = args.playlist_name

    if not args.yes and not args.json:
        try:
            from rich.console import Console
            from rich.prompt import Confirm
            console = Console()
            console.print(_preview())
            if not Confirm.ask("Continuar?", default=True):
                return 0
            playlist_name = _prompt_playlist_name(playlist_name)
        except ImportError:
            print(_preview())
            response = input("Continuar? [Y/n]: ").strip().lower()
            if response == "n":
                return 0

    cb = None
    progress = None
    try:
        from rich.progress import Progress, SpinnerColumn, TextColumn
        progress = Progress(SpinnerColumn(), TextColumn("{task.description}"))
        progress.start()
        task_id = progress.add_task("Iniciando...", total=None)

        def _cb(ev):
            desc = f"[{ev.get('step')}/6] {ev.get('name', '')}"
            if ev.get("detail"):
                desc += f" — {ev['detail']}"
            progress.update(task_id, description=desc)
        cb = _cb
    except ImportError:
        pass

    try:
        report = onboard.run(
            controller.sp,
            taste,
            playlist_name=playlist_name,
            seed_count=args.seed_playlist,
            dry_run=args.dry_run,
            progress_cb=cb,
        )
    finally:
        if progress is not None:
            progress.stop()

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        _print_report(report)
    return 0


@register
def _register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("onboard", help="Bootstrap do perfil por histórico")
    p.add_argument("--playlist-name", default="Maestra")
    p.add_argument("--seed-playlist", type=int, default=30,
                   help="Faixas iniciais na playlist (0 = não semeia).")
    p.add_argument("--dry-run", action="store_true",
                   help="Não cria playlist nem escreve no taste_profile; só simula.")
    p.add_argument("--yes", action="store_true", help="Pula confirmação.")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=_handle)
