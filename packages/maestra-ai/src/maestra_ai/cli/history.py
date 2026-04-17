"""Subcomando `history`: recent, top-tracks, top-artists, analyze,
outside-playlist, import-outside."""
from __future__ import annotations

import argparse

from maestra_ai.cli import register
from maestra_ai.cli._common import (
    PLAYLIST_ID,
    _curation_context,
    _record_curated_tracks,
    _signal_weight,
    output,
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


def cmd_history_import_outside(args, controller, taste, history_analyzer, context_state, **_):
    context, context_source = _curation_context(args, context_state)
    analysis = history_analyzer.outside_playlist(PLAYLIST_ID, recent_limit=args.recent_limit)
    candidates = [
        track
        for track in analysis["candidates"]
        if track["plays"] >= args.min_plays
    ][:args.count]

    if not candidates:
        output({
            "status": "unchanged",
            "reason": "no_outside_candidates",
            "context": context,
            "context_source": context_source,
            "recent_count": analysis["recent_count"],
            "outside_count": analysis["outside_count"],
        }, args.human)
        return

    if args.dry_run:
        output({
            "status": "dry_run",
            "context": context,
            "context_source": context_source,
            "would_add": len(candidates),
            "tracks": candidates,
            "note": "Nenhuma playlist ou memória foi alterada.",
        }, args.human)
        return

    controller.playlist_add(PLAYLIST_ID, [track["uri"] for track in candidates])
    _record_curated_tracks(taste, candidates, context, ["outside-playlist"])

    recorded_signals = 0
    for track in candidates:
        event_id = f"outside-playlist-import:{context}:{track['uri']}"
        if taste.record_context_signal(
            track["uri"],
            args.signal,
            context,
            source="outside_playlist_import",
            event_id=event_id,
            weight=_signal_weight(args.signal),
        ):
            recorded_signals += 1

    output({
        "status": "imported",
        "context": context,
        "context_source": context_source,
        "added": len(candidates),
        "signal": args.signal,
        "recorded_signals": recorded_signals,
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
    p.add_argument("--playlist-id", default=PLAYLIST_ID)
    p.set_defaults(func=cmd_history_outside_playlist)

    p = sub.add_parser("import-outside", help="Importa recentes fora da playlist para o contexto ativo")
    p.add_argument("--recent-limit", type=int, default=50)
    p.add_argument("--count", type=int, default=5)
    p.add_argument("--min-plays", type=int, default=1)
    p.add_argument("--context", help="Contexto para registrar as faixas; usa contexto ativo se omitido")
    p.add_argument("--signal", default="good", choices=["good", "bad", "skip"])
    p.add_argument("--dry-run", action="store_true",
                   help="Mostra candidatos sem alterar playlist ou memória")
    p.set_defaults(func=cmd_history_import_outside)
