"""Subcomando `playlist`: list, add, top-up, clean, remove, prune, clear."""
from __future__ import annotations

import argparse

from maestra_ai.cli import register
from maestra_ai.cli._common import (
    _curation_context,
    _record_curated_tracks,
    error,
    output,
    resolve_playlist_id,
)


def cmd_playlist_list(args, controller, **_):
    playlist_id = resolve_playlist_id()
    tracks = controller.playlist_tracks(playlist_id)
    output(tracks, args.human)


def cmd_playlist_add(args, controller, taste, curator, context_state, **_):
    playlist_id = resolve_playlist_id()
    context, context_source = _curation_context(args, context_state)
    results, queries_used, _sources = curator.curate(context, count=args.count)
    if not results:
        error("Não consegui encontrar faixas para esse contexto.", "NO_RESULTS")
    uris = [r["uri"] for r in results]
    controller.playlist_add(playlist_id, uris)
    _record_curated_tracks(taste, results, context, queries_used)
    output({
        "added": len(results),
        "context": context,
        "context_source": context_source,
        "tracks": results,
    }, args.human)


def cmd_playlist_top_up(args, controller, taste, curator, context_state, **_):
    playlist_id = resolve_playlist_id()
    context, context_source = _curation_context(args, context_state)
    tracks = controller.playlist_tracks(playlist_id)
    existing_uris = {t["uri"] for t in tracks}
    needed = max(args.target - len(existing_uris), 0)

    if needed == 0:
        output({
            "status": "unchanged",
            "current": len(existing_uris),
            "target": args.target,
            "added": 0,
            "context": context,
            "context_source": context_source,
            "message": "Playlist já atingiu o alvo.",
        }, args.human)
        return

    results, queries_used, _sources = curator.curate(
        context,
        count=needed,
        exclude_uris=existing_uris,
    )
    if not results:
        error("Não consegui encontrar faixas novas para complementar a playlist.", "NO_RESULTS")

    uris = [r["uri"] for r in results]
    controller.playlist_add(playlist_id, uris)
    _record_curated_tracks(taste, results, context, queries_used)

    output({
        "status": "topped_up",
        "previous": len(existing_uris),
        "target": args.target,
        "added": len(results),
        "context": context,
        "context_source": context_source,
        "tracks": results,
    }, args.human)


def cmd_playlist_clean(args, controller, taste, **_):
    playlist_id = resolve_playlist_id()
    tracks = controller.playlist_tracks(playlist_id)
    to_remove = [t["uri"] for t in tracks if taste.should_remove(t["uri"])]
    if not to_remove:
        output({"removed": 0, "message": "Nenhuma faixa pra remover."}, args.human)
        return
    controller.playlist_remove(playlist_id, to_remove)
    output({"removed": len(to_remove), "uris": to_remove}, args.human)


def cmd_playlist_remove(args, controller, **_):
    playlist_id = resolve_playlist_id()
    uris = list(dict.fromkeys(args.uris))
    controller.playlist_remove(playlist_id, uris)
    output({"status": "removed", "removed": len(uris), "uris": uris}, args.human)


def cmd_playlist_prune(args, controller, taste, context_state, curator, **_):
    playlist_id = resolve_playlist_id()
    context = context_state.show() or {}
    context_name = context.get("context") if isinstance(context, dict) else None

    result = curator.prune(
        playlist_id=playlist_id,
        context=context_name or "",
        confirm=not args.dry_run,
    )
    output(result, args.human)


def cmd_playlist_clear(args, controller, **_):
    playlist_id = resolve_playlist_id()
    tracks = controller.playlist_tracks(playlist_id)
    if not tracks:
        output({"removed": 0, "message": "Playlist já está vazia."}, args.human)
        return
    uris = [t["uri"] for t in tracks]
    controller.playlist_remove(playlist_id, uris)
    output({"removed": len(uris)}, args.human)


@register
def _register(subparsers: argparse._SubParsersAction) -> None:
    from maestra_ai.cli import group_help_handler
    playlist_parser = subparsers.add_parser("playlist", help="Gerencia Sincronia Iris")
    playlist_parser.set_defaults(func=group_help_handler(playlist_parser))
    sub = playlist_parser.add_subparsers(dest="playlist_command", required=False)

    p = sub.add_parser("list", help="Lista faixas da playlist")
    p.set_defaults(func=cmd_playlist_list)

    p = sub.add_parser("add", help="Adiciona faixas por contexto")
    p.add_argument("context", nargs="?", default=None, help="Contexto: mood, atividade ou referência")
    p.add_argument("--count", type=int, default=5)
    p.set_defaults(func=cmd_playlist_add)

    p = sub.add_parser("top-up", help="Complementa a playlist até um alvo de faixas")
    p.add_argument("context", nargs="?", default=None, help="Contexto usado para buscar novas faixas")
    p.add_argument("--target", type=int, default=15, help="Quantidade alvo de faixas na playlist")
    p.set_defaults(func=cmd_playlist_top_up)

    p = sub.add_parser("clean", help="Remove faixas rejeitadas")
    p.set_defaults(func=cmd_playlist_clean)

    p = sub.add_parser("remove", help="Remove URIs específicas da playlist")
    p.add_argument("uris", nargs="+", help="URIs das faixas a remover")
    p.set_defaults(func=cmd_playlist_remove)

    p = sub.add_parser("prune", help="Poda contextual da playlist; dry-run por padrão")
    p.add_argument("--context", help="Contexto para avaliar; usa contexto ativo se omitido")
    p.add_argument("--dry-run", action="store_true", default=True, help="Simula sem remover (padrão)")
    p.add_argument("--confirm", dest="dry_run", action="store_false", help="Aplica a remoção dos candidatos")
    p.set_defaults(func=cmd_playlist_prune)

    p = sub.add_parser("clear", help="Limpa toda a playlist")
    p.set_defaults(func=cmd_playlist_clear)
