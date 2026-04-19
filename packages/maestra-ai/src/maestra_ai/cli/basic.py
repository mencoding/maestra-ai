"""Subcomandos top-level: status, start, now, devices, play, pause, next, search,
queue, queue-add, queue-context, play-context."""
from __future__ import annotations

import argparse
import sys
import time

from maestra_ai.cli import register
from maestra_ai.cli._common import (
    _curation_context,
    _record_curated_tracks,
    error,
    output,
    resolve_playlist_id,
    safe_call,
    taste_summary,
)


def cmd_start(args, controller, **_):
    playlist_id = resolve_playlist_id()
    playlist_uri = f"spotify:playlist:{playlist_id}"

    # v0.5.5 #1: DeviceError (MaestraError) sobe direto para main() e
    # renderiza painel Rich padronizado; não precisa do except local.
    controller.ensure_active_device()

    try:
        controller.play(uri=playlist_uri)
    except Exception as e:
        error(f"Falha ao iniciar playlist: {e}", "PLAYBACK_ERROR")

    result = None
    for attempt in range(3):
        time.sleep(2)
        result = controller.now()
        if result and result.get("is_playing"):
            output(result, args.human)
            return
        if attempt < 2:
            try:
                controller.play(uri=playlist_uri)
            except Exception:
                pass

    if result:
        result["warning"] = "Faixa carregada mas is_playing=false após 3 tentativas"
        output(result, args.human)
        sys.exit(1)
    else:
        error("Não consegui confirmar playback após 3 tentativas.", "START_FAILED")


def cmd_now(args, controller, **_):
    result = controller.now()
    if result is None:
        error("Nada tocando no momento ou dispositivo inativo.", "NO_PLAYBACK")
    output(result, args.human)


def cmd_devices(args, controller, **_):
    result = controller.devices()
    if not result:
        error("Nenhum dispositivo Spotify ativo.", "NO_DEVICE")
    output(result, args.human)


def cmd_play(args, controller, **_):
    try:
        controller.play(uri=args.uri if args.uri else None)
        result = controller.now()
        output(result or {"status": "playing"}, args.human)
    except Exception as e:
        error(str(e), "PLAYBACK_ERROR")


def cmd_pause(args, controller, **_):
    try:
        controller.pause()
        output({"status": "paused"}, args.human)
    except Exception as e:
        error(str(e), "PLAYBACK_ERROR")


def cmd_next(args, controller, **_):
    try:
        controller.next_track()
        time.sleep(0.5)
        result = controller.now()
        output(result or {"status": "next"}, args.human)
    except Exception as e:
        error(str(e), "PLAYBACK_ERROR")


def cmd_search(args, controller, **_):
    results = controller.search(args.query, type=args.type, limit=args.limit)
    if not results:
        error("Nenhum resultado encontrado.", "NO_RESULTS")
    output(results, args.human)


def cmd_queue(args, controller, **_):
    result = controller.queue_list()
    output(result, args.human)


def cmd_queue_add(args, controller, **_):
    try:
        controller.queue_add(args.uri)
        output({"status": "added", "uri": args.uri}, args.human)
    except Exception as e:
        error(str(e), "QUEUE_ERROR")


def cmd_queue_context(args, controller, taste, curator, context_state, **_):
    context, context_source = _curation_context(args, context_state)
    results, queries_used = curator.curate(context, count=args.count)
    if not results:
        error("Sem resultados para esse contexto.", "NO_RESULTS")

    added = []
    for track in results:
        try:
            controller.queue_add(track["uri"])
            added.append(track)
        except Exception as e:
            error(str(e), "QUEUE_ERROR")

    _record_curated_tracks(taste, added, context, queries_used)
    output({
        "status": "queued",
        "context": context,
        "context_source": context_source,
        "added": len(added),
        "tracks": added,
    }, args.human)


def cmd_play_context(args, controller, taste, curator, context_state, **_):
    context, context_source = _curation_context(args, context_state)
    results, queries_used = curator.curate(context, count=1)
    if not results:
        error("Sem resultados para esse contexto.", "NO_RESULTS")

    track = results[0]
    try:
        controller.play(track["uri"])
    except Exception as e:
        error(str(e), "PLAYBACK_ERROR")

    _record_curated_tracks(taste, [track], context, queries_used)
    output({
        "status": "playing",
        "context": context,
        "context_source": context_source,
        "track": track,
    }, args.human)


def cmd_status(args, controller, taste, context_state, feedback_prompter, **_):
    active_context = context_state.show()
    context = active_context["context"] if active_context else None
    try:
        playlist_id = resolve_playlist_id()
    except Exception:
        playlist_id = None
    if playlist_id:
        playlist_tracks = safe_call(lambda: controller.playlist_tracks(playlist_id), "PLAYLIST_ERROR")
    else:
        playlist_tracks = {"error": "playlist_id não configurado", "code": "PLAYLIST_UNSET"}
    playlist_count = len(playlist_tracks) if isinstance(playlist_tracks, list) else None

    output({
        "now": safe_call(controller.now, "PLAYBACK_ERROR"),
        "context": active_context or {"status": "unset", "context": None},
        "playlist": {
            "id": playlist_id,
            "count": playlist_count,
            "error": playlist_tracks if isinstance(playlist_tracks, dict) else None,
        },
        "taste": taste_summary(taste),
        "feedback_suggestion": feedback_prompter.suggest(taste, context=context),
    }, args.human)


@register
def _register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("status", help="Estado agregado para agentes de IA")
    p.set_defaults(func=cmd_status)

    p = subparsers.add_parser(
        "start",
        help="Inicializa: ativa dispositivo, toca Sincronia Iris, confirma playback",
    )
    p.set_defaults(func=cmd_start)

    p = subparsers.add_parser("now", help="O que está tocando")
    p.set_defaults(func=cmd_now)

    p = subparsers.add_parser("devices", help="Dispositivos ativos")
    p.set_defaults(func=cmd_devices)

    p = subparsers.add_parser("play", help="Toca URI ou resume")
    p.add_argument("uri", nargs="?", default=None, help="URI do Spotify (track, playlist, album)")
    p.set_defaults(func=cmd_play)

    p = subparsers.add_parser("pause", help="Pausa playback")
    p.set_defaults(func=cmd_pause)

    p = subparsers.add_parser("next", help="Próxima faixa")
    p.set_defaults(func=cmd_next)

    p = subparsers.add_parser("search", help="Busca no Spotify")
    p.add_argument("query", help="Termo de busca")
    p.add_argument("--type", default="track", choices=["track", "artist", "album"])
    p.add_argument("--limit", type=int, default=10)
    p.set_defaults(func=cmd_search)

    p = subparsers.add_parser("queue", help="Lista fila atual")
    p.set_defaults(func=cmd_queue)

    p = subparsers.add_parser("queue-add", help="Adiciona à fila")
    p.add_argument("uri", help="URI da faixa")
    p.set_defaults(func=cmd_queue_add)

    p = subparsers.add_parser("queue-context", help="Curadoria por contexto e adiciona à fila")
    p.add_argument("context", nargs="?", default=None, help="Contexto musical")
    p.add_argument("--count", type=int, default=3)
    p.set_defaults(func=cmd_queue_context)

    p = subparsers.add_parser("play-context", help="Curadoria por contexto e toca imediatamente")
    p.add_argument("context", nargs="?", default=None, help="Contexto musical")
    p.set_defaults(func=cmd_play_context)
