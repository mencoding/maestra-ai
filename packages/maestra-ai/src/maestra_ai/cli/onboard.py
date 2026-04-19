"""Subcomando onboard — UX rich: progress, preview de custo, panel final.

v0.4.5 parte 2: modo interativo em TTY com escolha entre criar nova
playlist buffer ou apontar para uma existente. Flags `--name` e
`--playlist-id` preservam modo non-interactive para uso scriptado.
"""
from __future__ import annotations

import argparse
import json
import sys

from maestra_ai.cli import register
from maestra_ai.core import onboard
from maestra_ai.core.config import normalize_playlist_id
from maestra_ai.core.reporting import format_estimate

_DEFAULT_NAME = "Maestra Seeds"


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


def _build_playlist_selector(args, progress):
    """v0.5.3: constrói callback para expansão via playlists.

    Três modos:
    - `--no-expand`: None (core pula expansão).
    - `--expand-playlists "id1,id2"`: selector fixo sem prompt.
    - TTY + Rich/questionary disponível: checkbox interativo.
    - Non-TTY ou --non-interactive sem --expand-playlists: None.
    """
    if getattr(args, "no_expand", False):
        return None

    preset = getattr(args, "expand_playlists", None)
    if preset:
        ids = [s.strip() for s in preset.split(",") if s.strip()]

        def _fixed_selector(_playlists):
            return ids

        return _fixed_selector

    if getattr(args, "non_interactive", False):
        return None
    if not sys.stdin.isatty():
        return None

    def _interactive_selector(playlists):
        # v0.5.5 #4: core já filtrou playlists vazias em _fetch_own_playlists,
        # CLI não precisa duplicar. Lista vazia aqui = usuário sem playlists
        # próprias utilizáveis.
        if not playlists:
            _humanized_no_playlists_message()
            return []
        # Pausa Rich Progress enquanto questionary toma o terminal.
        if progress is not None:
            progress.stop()
        try:
            # v0.5.3.1 (C1): Ctrl+C durante o prompt NÃO pode abortar o
            # onboard — top/saved/recent já foram buscados e devem ser
            # persistidos. Degrada silenciosamente para [] (sem expansão)
            # para que o core continue o fluxo normal.
            try:
                confirm = _prompt_expansion_confirm()
            except KeyboardInterrupt:
                return []
            if not confirm:
                return []
            try:
                return _prompt_playlists_checkbox(playlists)
            except KeyboardInterrupt:
                return []
        finally:
            if progress is not None:
                progress.start()

    return _interactive_selector


def _prompt_expansion_confirm() -> bool:
    """Pergunta ao usuário se quer expandir via playlists próprias."""
    try:
        import questionary
        return questionary.confirm(
            "Sua amostra inicial é menor que 5000 faixas. "
            "Quer expandir usando suas próprias playlists?",
            default=True,
        ).ask() or False
    except Exception:
        r = input("Expandir com suas playlists? [Y/n]: ").strip().lower()
        return r != "n"


def _prompt_playlists_checkbox(playlists: list[dict]) -> list[str]:
    """Checkbox interativo com nome + quantidade de faixas."""
    try:
        import questionary
        choices = [
            questionary.Choice(
                title=f"{p['name']}  ({p['track_count']} faixas)",
                value=p["id"],
            )
            for p in playlists
        ]
        selected = questionary.checkbox(
            "Marque as playlists para incluir (espaço = marcar, enter = confirmar):",
            choices=choices,
        ).ask()
        return selected or []
    except Exception:
        # Fallback: numerado + vírgulas
        print("Playlists disponíveis:")
        for i, p in enumerate(playlists, 1):
            print(f"  [{i}] {p['name']} ({p['track_count']} faixas)")
        raw = input("Números separados por vírgula (ou 'all'): ").strip()
        if raw.lower() == "all":
            return [p["id"] for p in playlists]
        try:
            idxs = [int(x.strip()) for x in raw.split(",") if x.strip()]
            return [playlists[i - 1]["id"] for i in idxs if 1 <= i <= len(playlists)]
        except ValueError:
            return []


def _humanized_no_playlists_message() -> None:
    """Mensagem calorosa quando o usuário não tem playlists próprias."""
    msg = (
        "Você ainda não criou nenhuma playlist no Spotify — tudo bem, "
        "vou aprender seus gostos ao longo das nossas interações."
    )
    try:
        from rich.console import Console
        Console().print(f"[cyan]{msg}[/cyan]")
    except ImportError:
        print(msg)


def _print_report(report: dict) -> None:
    try:
        from rich.console import Console
        from rich.panel import Panel
        console = Console()

        expansion = report.get("playlist_expansion") or {}
        expansion_line = ""
        if expansion.get("attempted"):
            added = expansion.get("tracks_added", 0)
            picked = expansion.get("selected_playlists", [])
            reason = expansion.get("reason")
            failed = expansion.get("failed_playlists") or []
            if added:
                expansion_line = (
                    f"Expansão:         +{added} faixas de "
                    f"{len(picked)} playlist(s) própria(s)"
                )
                if failed:
                    expansion_line += f" ({len(failed)} falhou/falharam)"
                expansion_line += "\n"
            elif reason == "no_own_playlists":
                expansion_line = "Expansão:         — (sem playlists próprias)\n"
            elif reason == "user_skipped":
                expansion_line = "Expansão:         — (dispensada)\n"

        body = (
            f"Playlist:         {report['playlist_name']} "
            f"({report.get('playlist_id') or '—'})\n"
            f"Top tracks:       long={report['top_long_count']} "
            f"medium={report['top_medium_count']} short={report['top_short_count']}\n"
            f"Saved tracks:     {report['saved_tracks_fetched']}\n"
            f"Recently played:  {report['recent_count']}\n"
            + expansion_line
            + f"Faixas pontuadas: {report['unique_tracks_scored']}\n"
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


def _interactive_choose(controller) -> tuple[str | None, str | None]:
    """Fluxo interativo de escolha.

    Retorna `(playlist_name, existing_playlist_id)` — exatamente um dos
    dois é não-None. Se o usuário abortar por erro, levanta SystemExit.
    """
    print("Onboard — configuração inicial da Maestra")
    print("Como quer configurar a playlist buffer?")
    print("  [1] Criar uma nova playlist (default)")
    print("  [2] Apontar para uma playlist existente")
    escolha = (input("Escolha [1]: ").strip() or "1")

    if escolha == "1":
        nome = input(f"Nome da playlist [{_DEFAULT_NAME}]: ").strip() or _DEFAULT_NAME
        return (nome, None)

    if escolha == "2":
        # Lista até 20 playlists do usuário.
        try:
            resp = controller.sp.current_user_playlists(limit=20)
        except Exception as e:
            print(f"Erro ao listar playlists: {e}")
            raise SystemExit(1) from e
        items = (resp or {}).get("items", []) or []
        print("\nTuas playlists (primeiras 20):")
        for i, pl in enumerate(items, start=1):
            name = pl.get("name") or "(sem nome)"
            total = ((pl.get("tracks") or {}).get("total")) or 0
            print(f"  [{i:2d}] {name} ({total} faixas)")
        # Até 3 tentativas para input válido (número ou ID/URI/URL).
        for _ in range(3):
            raw = input("Digite número ou cole ID/URL: ").strip()
            if raw.isdigit():
                idx = int(raw)
                if 1 <= idx <= len(items):
                    chosen = items[idx - 1]
                    return (None, chosen.get("id"))
                print("Número fora do intervalo.")
                continue
            try:
                pid = normalize_playlist_id(raw)
                return (None, pid)
            except ValueError:
                print("Entrada inválida — tente de novo.")
        print("3 tentativas inválidas; abortando.")
        raise SystemExit(1)

    # Entrada inesperada — trata como default (criar nova).
    return (_DEFAULT_NAME, None)


def _handle(args: argparse.Namespace, controller, taste, **_) -> int:
    playlist_name = getattr(args, "playlist_name", None)
    explicit_id = getattr(args, "playlist_id", None)
    non_interactive = getattr(args, "non_interactive", False)

    existing_playlist_id: str | None = None

    # 1) Flag --playlist-id tem prioridade (non-interactive implícito).
    if explicit_id:
        try:
            existing_playlist_id = normalize_playlist_id(explicit_id)
        except ValueError as e:
            print(f"--playlist-id inválido: {e}")
            return 2
        playlist_name = None  # não usa nome no fluxo "apontar"
    else:
        # 2) Detecta se pode entrar em modo interativo.
        is_tty = sys.stdin.isatty() and sys.stdout.isatty()
        if non_interactive:
            if not playlist_name:
                print(
                    "--non-interactive requer --name ou --playlist-id. "
                    "Passe uma das flags explicitamente."
                )
                return 2
        elif is_tty:
            # Interativo: pergunta criar vs apontar.
            try:
                name, pid = _interactive_choose(controller)
            except SystemExit as e:
                return int(e.code) if isinstance(e.code, int) else 1
            playlist_name = name
            existing_playlist_id = pid
        else:
            # Não-TTY sem flags explícitas: mantém comportamento legado
            # (default "Maestra" quando playlist_name está definido).
            if not playlist_name:
                print("Nenhum --name ou --playlist-id informado e não há TTY.")
                return 2

    if not args.yes and not args.json and existing_playlist_id is None:
        try:
            from rich.console import Console
            from rich.prompt import Confirm
            console = Console()
            console.print(_preview())
            if not Confirm.ask("Continuar?", default=True):
                return 0
            if playlist_name:
                playlist_name = _prompt_playlist_name(playlist_name)
        except ImportError:
            print(_preview())
            response = input("Continuar? [Y/n]: ").strip().lower()
            if response == "n":
                return 0

    # v0.5.2 (bug 4): top_short tem cap 50 na API Spotify. Pedir mais é
    # silenciosamente clampeado. Avisa o usuário antes de gastar ~8s.
    warnings: list[str] = []
    if args.seed_playlist > 50:
        msg = (
            f"--seed-playlist={args.seed_playlist} será clampeado para 50 "
            f"(Spotify limita top_short_term a 50 faixas)."
        )
        warnings.append(msg)
        if not args.json:
            try:
                from rich.console import Console
                Console().print(f"[yellow]⚠ {msg}[/yellow]")
            except ImportError:
                print(f"[WARN] {msg}")

    cb = None
    progress = None
    # v0.5.2: em modo JSON não renderizar progress (polui stdout e
    # quebra parsing por agente).
    if not args.json:
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

    # v0.5.3: monta o playlist_selector conforme flags + TTY.
    playlist_selector = _build_playlist_selector(args, progress)

    try:
        report = onboard.run(
            controller.sp,
            taste,
            playlist_name=playlist_name or "",
            seed_count=args.seed_playlist,
            dry_run=args.dry_run,
            progress_cb=cb,
            existing_playlist_id=existing_playlist_id,
            total_cap=args.total_cap,
            playlist_selector=playlist_selector,
        )
    finally:
        if progress is not None:
            progress.stop()

    if warnings:
        report = dict(report)
        report["warnings"] = warnings

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        _print_report(report)
    return 0


@register
def _register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("onboard", help="Bootstrap do perfil por histórico")
    # Sem default: ausência sinaliza "não foi passado".
    p.add_argument("--playlist-name", "--name", dest="playlist_name", default=None,
                   help="Nome da nova playlist buffer a criar.")
    p.add_argument("--playlist-id", dest="playlist_id", default=None,
                   help="ID/URI/URL de playlist existente para usar como buffer "
                        "(pula criação).")
    p.add_argument("--non-interactive", action="store_true",
                   help="Força modo não-interativo; exige --name ou --playlist-id.")
    p.add_argument("--seed-playlist", type=int, default=30,
                   help="Faixas iniciais na playlist (0 = não semeia).")
    p.add_argument("--dry-run", action="store_true",
                   help="Não cria playlist nem escreve no taste_profile; só simula.")
    p.add_argument("--yes", action="store_true", help="Pula confirmação.")
    # v0.5.3: expansão opcional via playlists próprias.
    p.add_argument("--total-cap", type=int, default=5000,
                   help="Teto desejado de faixas únicas pontuadas. Se após "
                        "top+saved+recent ficar abaixo e modo interativo, "
                        "oferece expansão via playlists próprias (default 5000).")
    p.add_argument("--no-expand", action="store_true",
                   help="Desativa a oferta de expansão por playlists.")
    p.add_argument("--expand-playlists", default=None,
                   help="Lista de IDs de playlist separados por vírgula para "
                        "usar na expansão (pula o prompt interativo).")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=_handle)
