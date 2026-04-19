"""Subcomando `history`: recent, top-tracks, top-artists, analyze,
outside-playlist, import-outside."""
from __future__ import annotations

import argparse

from maestra_ai.cli import register
from maestra_ai.cli._common import (
    _curation_context,
    _record_curated_tracks,
    output,
    resolve_playlist_id,
)


def cmd_history_recent(args, controller, **_):
    output(controller.recently_played(limit=args.limit), args.human)


def cmd_history_top_tracks(args, controller, **_):
    output(controller.top_tracks(time_range=args.range, limit=args.limit), args.human)


def cmd_history_top_artists(args, controller, **_):
    output(controller.top_artists(time_range=args.range, limit=args.limit), args.human)


def cmd_history_analyze(args, history_analyzer, **_):
    output(
        history_analyzer.analyze(
            recent_limit=args.recent_limit,
            top_limit=args.top_limit,
        ),
        args.human,
    )


def cmd_history_outside_playlist(args, history_analyzer, **_):
    output(
        history_analyzer.outside_playlist(
            args.playlist_id,
            recent_limit=args.recent_limit,
        ),
        args.human,
    )


def _outside_playlist_resolve_default(args, history_analyzer, **kw):
    # Resolve default via config quando --playlist-id não foi passado.
    if not args.playlist_id:
        args.playlist_id = resolve_playlist_id()
    return cmd_history_outside_playlist(args, history_analyzer, **kw)


def cmd_history_import_outside(args, controller, taste, history_analyzer, context_state, **_):
    playlist_id = resolve_playlist_id()
    context, context_source = _curation_context(args, context_state)

    # Delega ao core.HistoryAnalyzer.import_outside — signal é aplicado lá.
    result = history_analyzer.import_outside(
        playlist_id=playlist_id,
        context=context,
        confirm=not args.dry_run,
        count=args.count,
        min_plays=args.min_plays,
        recent_limit=args.recent_limit,
        taste=taste,
        signal=args.signal,
    )

    candidates = result.get("candidates", [])

    if not candidates:
        # Re-obtém contadores do outside_playlist para payload informativo.
        analysis_info = history_analyzer.outside_playlist(
            playlist_id, recent_limit=args.recent_limit
        )
        output({
            "status": "unchanged",
            "reason": "no_outside_candidates",
            "context": context,
            "context_source": context_source,
            "recent_count": analysis_info["recent_count"],
            "outside_count": analysis_info["outside_count"],
        }, args.human)
        return

    if args.dry_run:
        output({
            "status": "dry_run",
            "context": context,
            "context_source": context_source,
            "would_add": len(candidates),
            "tracks": candidates,
            "signal": args.signal,
            "note": "Nenhuma playlist ou memória foi alterada.",
        }, args.human)
        return

    # Registro adicional de bookkeeping (taste.record_added) — distinto do
    # sinal contextual, já aplicado pelo core.
    _record_curated_tracks(taste, candidates, context, ["outside-playlist"])

    output({
        "status": "imported",
        "context": context,
        "context_source": context_source,
        "added": result.get("imported", len(candidates)),
        "signal": result.get("signal", args.signal),
        "recorded_signals": result.get("recorded_signals", 0),
        "snapshot_id": result.get("snapshot_id"),
        "tracks": candidates,
    }, args.human)


@register
def _register(subparsers: argparse._SubParsersAction) -> None:
    history_parser = subparsers.add_parser("history", help="Analisa histórico Spotify sem alterar gosto")
    sub = history_parser.add_subparsers(dest="history_command", required=True)

    p = sub.add_parser("recent", help="Lista faixas tocadas recentemente")
    p.add_argument("--limit", type=int, default=50)
    p.set_defaults(func=cmd_history_recent)

    p = sub.add_parser("top-tracks", help="Lista top faixas")
    p.add_argument("--range", default="medium_term",
                   choices=["short_term", "medium_term", "long_term"])
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_history_top_tracks)

    p = sub.add_parser("top-artists", help="Lista top artistas")
    p.add_argument("--range", default="medium_term",
                   choices=["short_term", "medium_term", "long_term"])
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_history_top_artists)

    p = sub.add_parser("analyze", help="Análise pontual do histórico")
    p.add_argument("--recent-limit", type=int, default=50)
    p.add_argument("--top-limit", type=int, default=20)
    p.set_defaults(func=cmd_history_analyze)

    p = sub.add_parser("outside-playlist", help="Lista recentes fora da Sincronia Iris")
    p.add_argument("--recent-limit", type=int, default=50)
    p.add_argument(
        "--playlist-id",
        default=None,
        help="ID da playlist; default resolve via config (playlist_id).",
    )
    p.set_defaults(func=_outside_playlist_resolve_default)

    p = sub.add_parser("import-outside", help="Importa recentes fora da playlist para o contexto ativo")
    p.add_argument("--recent-limit", type=int, default=50)
    p.add_argument("--count", type=int, default=5)
    p.add_argument("--min-plays", type=int, default=1)
    p.add_argument("--context", help="Contexto para registrar as faixas; usa contexto ativo se omitido")
    p.add_argument("--signal", default="good", choices=["good", "bad", "skip"])
    p.add_argument("--dry-run", action="store_true",
                   help="Mostra candidatos sem alterar playlist ou memória")
    p.set_defaults(func=cmd_history_import_outside)
