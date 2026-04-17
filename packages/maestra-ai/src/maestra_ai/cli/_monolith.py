#!/usr/bin/env python3
"""Maestra — CLI Spotify Controller para Iris.

Uso: python cli.py <subcomando> [args]
Alias: maestra <subcomando> [args]
"""
import argparse
import json
import sys
import os
import time
import signal
import subprocess
from collections import Counter

# Garante que o diretório do script está no path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from maestra_ai.core.client import SpotifyController
from maestra_ai.core.taste import TasteProfile
from maestra_ai.core.curator import Curator, DEFAULT_CONTEXT
from maestra_ai.core.context import ContextState
from maestra_ai.core.playback import PlaybackObserver
from maestra_ai.core.playback_processor import PlaybackEventProcessor
from maestra_ai.core.feedback_prompt import FeedbackPrompter
from maestra_ai.core.history import HistoryAnalyzer
from maestra_ai.core.director import MusicDirector
from maestra_ai.core.flow import FlowAnalyzer

# Caminho dos dados — respeita MAESTRA_DATA_DIR (v0.1.0 fallback: workspace antigo do Léo).
# v0.2.0 substitui este bloco por maestra_ai.core.storage.
_DEFAULT_DATA_DIR = os.path.expanduser(
    "~/claude/.iris/projetos/pessoal/spotify-controller/workspace/dados"
)
BASE_DIR = os.environ.get("MAESTRA_DATA_DIR", _DEFAULT_DATA_DIR)
os.makedirs(BASE_DIR, exist_ok=True)
TASTE_PATH = os.path.join(BASE_DIR, "taste_profile.json")
CONTEXT_PATH = os.path.join(BASE_DIR,"current_context.json")
PLAYBACK_STATE_PATH = os.path.join(BASE_DIR,"playback_state.json")
PLAYBACK_EVENTS_PATH = os.path.join(BASE_DIR,"playback_events.jsonl")
FEEDBACK_PROMPT_STATE_PATH = os.path.join(BASE_DIR,"feedback_prompt_state.json")
DIRECTOR_PID_PATH = os.path.join(BASE_DIR,"director.pid")
DIRECTOR_STDOUT_LOG_PATH = os.path.join(BASE_DIR,"director.log")
DIRECTOR_DECISIONS_PATH = os.path.join(BASE_DIR,"director_decisions.jsonl")

# ID da playlist Sincronia Iris
PLAYLIST_ID = "1V2aEtKkJxLyJcxAz94nLY"


def output(data, human=False):
    """Imprime resultado em JSON ou texto legível."""
    if human:
        if isinstance(data, dict):
            for k, v in data.items():
                print(f"  {k}: {v}")
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    line = " | ".join(f"{k}: {v}" for k, v in item.items())
                    print(f"  {line}")
                else:
                    print(f"  {item}")
        else:
            print(data)
    else:
        print(json.dumps(data, indent=2, ensure_ascii=False))


def error(message, code="ERROR"):
    """Imprime erro em JSON para stderr e sai com código 1."""
    print(json.dumps({"error": message, "code": code}, ensure_ascii=False), file=sys.stderr)
    sys.exit(1)


def safe_call(fn, error_code):
    """Executa função e retorna valor ou erro serializável."""
    try:
        return fn()
    except Exception as e:
        return {"error": str(e), "code": error_code}


def _pid_running(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def cmd_start(args, controller, **_):
    """Inicializa a maestra: ativa dispositivo, toca Sincronia Iris, confirma playback."""
    playlist_uri = f"spotify:playlist:{PLAYLIST_ID}"

    # 1. Garantir dispositivo ativo
    try:
        device_id = controller.ensure_active_device()
    except RuntimeError as e:
        error(str(e), "DEVICE_ERROR")

    # 2. Tocar a playlist
    try:
        controller.play(uri=playlist_uri)
    except Exception as e:
        error(f"Falha ao iniciar playlist: {e}", "PLAYBACK_ERROR")

    # 3. Confirmar que está tocando (até 3 tentativas com 2s de intervalo)
    for attempt in range(3):
        time.sleep(2)
        result = controller.now()
        if result and result.get("is_playing"):
            output(result, args.human)
            return
        # Se carregou mas não tocou, tenta play de novo
        if attempt < 2:
            try:
                controller.play(uri=playlist_uri)
            except Exception:
                pass

    # Falhou após tentativas — reporta o estado atual
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


def _record_curated_tracks(taste, tracks, context, queries_used):
    tracks_info = [{"uri": r["uri"], "name": r["track"], "artist": r["artist"]} for r in tracks]
    taste.record_added(tracks_info, context=context, queries_used=queries_used)


def _curation_context(args, context_state):
    """Resolve contexto de curadoria: argumento, contexto ativo ou fallback."""
    raw_context = getattr(args, "context", None)
    if raw_context and raw_context.strip():
        return raw_context.strip(), "argument"

    active_context = context_state.show()
    if active_context:
        return active_context["context"], "active"

    return DEFAULT_CONTEXT, "default"


def cmd_playlist_list(args, controller, **_):
    tracks = controller.playlist_tracks(PLAYLIST_ID)
    output(tracks, args.human)


def cmd_playlist_add(args, controller, taste, curator, context_state, **_):
    context, context_source = _curation_context(args, context_state)
    results, queries_used = curator.curate(context, count=args.count)
    if not results:
        error("Não consegui encontrar faixas para esse contexto.", "NO_RESULTS")
    uris = [r["uri"] for r in results]
    controller.playlist_add(PLAYLIST_ID, uris)
    _record_curated_tracks(taste, results, context, queries_used)
    output({
        "added": len(results),
        "context": context,
        "context_source": context_source,
        "tracks": results,
    }, args.human)


def cmd_playlist_top_up(args, controller, taste, curator, context_state, **_):
    context, context_source = _curation_context(args, context_state)
    tracks = controller.playlist_tracks(PLAYLIST_ID)
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

    results, queries_used = curator.curate(
        context,
        count=needed,
        exclude_uris=existing_uris,
    )
    if not results:
        error("Não consegui encontrar faixas novas para complementar a playlist.", "NO_RESULTS")

    uris = [r["uri"] for r in results]
    controller.playlist_add(PLAYLIST_ID, uris)
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
    tracks = controller.playlist_tracks(PLAYLIST_ID)
    to_remove = [t["uri"] for t in tracks if taste.should_remove(t["uri"])]
    if not to_remove:
        output({"removed": 0, "message": "Nenhuma faixa pra remover."}, args.human)
        return
    controller.playlist_remove(PLAYLIST_ID, to_remove)
    output({"removed": len(to_remove), "uris": to_remove}, args.human)


def cmd_playlist_remove(args, controller, **_):
    uris = list(dict.fromkeys(args.uris))
    controller.playlist_remove(PLAYLIST_ID, uris)
    output({"status": "removed", "removed": len(uris), "uris": uris}, args.human)


def _prune_candidates(tracks, taste, context):
    candidates = []
    for track in tracks:
        uri = track["uri"]
        global_bad = taste.should_remove(uri)
        context_score = taste.context_score(uri, context) if context else 0
        if not global_bad and context_score >= 0:
            continue
        reason = "global_bad" if global_bad else "context_negative"
        candidates.append({
            **track,
            "reason": reason,
            "context_score": context_score,
            "context": context,
        })
    return candidates


def cmd_playlist_prune(args, controller, taste, context_state, **_):
    context, context_source = _curation_context(args, context_state)
    tracks = controller.playlist_tracks(PLAYLIST_ID)
    candidates = _prune_candidates(tracks, taste, context)

    if not candidates:
        output({
            "status": "unchanged",
            "removed": 0,
            "context": context,
            "context_source": context_source,
            "message": "Nenhuma faixa candidata à poda.",
        }, args.human)
        return

    if not args.confirm:
        output({
            "status": "dry_run",
            "context": context,
            "context_source": context_source,
            "would_remove": len(candidates),
            "tracks": candidates,
            "note": "Nenhuma faixa removida. Use --confirm para aplicar.",
        }, args.human)
        return

    uris = [track["uri"] for track in candidates]
    controller.playlist_remove(PLAYLIST_ID, uris)
    output({
        "status": "pruned",
        "context": context,
        "context_source": context_source,
        "removed": len(candidates),
        "tracks": candidates,
    }, args.human)


def cmd_playlist_clear(args, controller, **_):
    tracks = controller.playlist_tracks(PLAYLIST_ID)
    if not tracks:
        output({"removed": 0, "message": "Playlist já está vazia."}, args.human)
        return
    uris = [t["uri"] for t in tracks]
    controller.playlist_remove(PLAYLIST_ID, uris)
    output({"removed": len(uris)}, args.human)


def taste_summary(taste):
    """Retorna resumo do perfil de gosto."""
    all_signals = [
        signal
        for t in taste.data["tracks"].values()
        for signal in t.get("context_signals", [])
    ]
    return {
        "version": taste.data.get("version"),
        "total_tracks": len(taste.data["tracks"]),
        "good": sum(1 for t in taste.data["tracks"].values() if t.get("feedback") == "good"),
        "bad": sum(1 for t in taste.data["tracks"].values() if t.get("feedback") == "bad"),
        "contextual_signals": len(all_signals),
        "contextual_positive": sum(1 for s in all_signals if s.get("signal") in ("good", "positive")),
        "contextual_negative": sum(1 for s in all_signals if s.get("signal") in ("bad", "skip", "negative")),
        "contexts": list(taste.data["context_queries"].keys()),
        "preferred_artists": taste.get_preferred_artists(),
        "rejected_artists": taste.get_rejected_artists(),
    }


def _track_context_signals(taste, uri, context):
    return taste.get_context_signals(uri, context=context)


def _context_review(tracks, taste, context, prune_candidates=None, top=10):
    playlist_uris = {track["uri"] for track in tracks}
    rows = []
    artist_counts = Counter()
    source_counts = Counter()

    for track in tracks:
        uri = track["uri"]
        artist_counts.update([track["artist"]])
        profile_track = taste.data.get("tracks", {}).get(uri, {})
        source_counts.update([profile_track.get("added_in_context") or "unknown"])
        signals = _track_context_signals(taste, uri, context)
        rows.append({
            **track,
            "score": taste.context_score(uri, context),
            "signals": len(signals),
            "positive": sum(1 for s in signals if s.get("signal") in ("good", "positive")),
            "negative": sum(1 for s in signals if s.get("signal") in ("bad", "skip", "negative")),
            "added_in_context": profile_track.get("added_in_context"),
        })

    tracked_outside = []
    for uri, profile_track in taste.data.get("tracks", {}).items():
        if uri in playlist_uris:
            continue
        signals = _track_context_signals(taste, uri, context)
        if not signals:
            continue
        tracked_outside.append({
            "track": profile_track.get("name", "unknown"),
            "artist": profile_track.get("artist", "unknown"),
            "uri": uri,
            "score": taste.context_score(uri, context),
            "signals": len(signals),
            "in_playlist": False,
        })

    positive_rows = sorted(
        [row for row in rows if row["score"] > 0],
        key=lambda row: (row["score"], row["signals"], row["track"]),
        reverse=True,
    )
    negative_rows = sorted(
        [row for row in rows if row["score"] < 0],
        key=lambda row: (row["score"], row["track"]),
    )
    unscored_rows = [row for row in rows if row["score"] == 0]
    prune_candidates = prune_candidates if prune_candidates is not None else _prune_candidates(tracks, taste, context)

    return {
        "context": context,
        "playlist_count": len(tracks),
        "profile_tracks": len(taste.data.get("tracks", {})),
        "tracked_in_playlist": sum(1 for row in rows if row["signals"] > 0),
        "unscored_in_playlist": len(unscored_rows),
        "positive_signals": sum(row["positive"] for row in rows),
        "negative_signals": sum(row["negative"] for row in rows),
        "top_positive": positive_rows[:top],
        "top_negative": negative_rows[:top],
        "prune_candidates": prune_candidates[:top],
        "dominant_artists": [
            {"artist": artist, "count": count}
            for artist, count in artist_counts.most_common(top)
        ],
        "source_contexts": [
            {"context": source, "count": count}
            for source, count in source_counts.most_common(top)
        ],
        "tracked_outside_playlist": sorted(
            tracked_outside,
            key=lambda row: (abs(row["score"]), row["signals"], row["track"]),
            reverse=True,
        )[:top],
        "notes": [
            "Leitura apenas; nenhuma playlist ou memória foi alterada.",
            "Use playlist prune para aplicar remoções candidatas.",
        ],
    }


def cmd_taste_show(args, taste, **_):
    output(taste_summary(taste), args.human)


def cmd_taste_review(args, controller, taste, context_state, **_):
    context, context_source = _curation_context(args, context_state)
    tracks = controller.playlist_tracks(PLAYLIST_ID)
    review = _context_review(
        tracks,
        taste,
        context,
        prune_candidates=_prune_candidates(tracks, taste, context),
        top=args.top,
    )
    output({
        "context_source": context_source,
        **review,
    }, args.human)


def cmd_taste_feedback(args, taste, context_state, **_):
    active_context = context_state.show()
    context = args.context
    context_source = "argument"
    if context is None and active_context:
        context = active_context["context"]
        context_source = "active"

    taste.record_feedback(
        args.uri,
        args.feedback,
        context=context,
        source=args.source,
        global_feedback=args.global_feedback,
    )
    output({
        "status": "recorded",
        "uri": args.uri,
        "feedback": args.feedback,
        "context": context,
        "context_source": context_source if context else None,
        "source": args.source,
        "global": args.global_feedback or context is None,
    }, args.human)


def cmd_taste_context_map(args, taste, **_):
    output(taste.data.get("context_queries", {}), args.human)


def cmd_curate(args, curator, context_state, **_):
    context, _ = _curation_context(args, context_state)
    results, _ = curator.curate(context, count=args.count)
    if not results:
        error("Sem resultados para esse contexto.", "NO_RESULTS")
    output(results, args.human)


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


def cmd_context_set(args, context_state, **_):
    result = context_state.set(args.context, ttl_minutes=args.ttl)
    output({"status": "set", **result}, args.human)


def cmd_context_show(args, context_state, **_):
    result = context_state.show()
    if result is None:
        output({"status": "unset", "context": None}, args.human)
        return
    output({"status": "active", **result}, args.human)


def cmd_context_clear(args, context_state, **_):
    output(context_state.clear(), args.human)


def _active_context_value(context_state):
    active_context = context_state.show()
    if not active_context:
        return None
    return active_context["context"]


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


def cmd_feedback_suggest(args, taste, context_state, feedback_prompter, **_):
    context = args.context or _active_context_value(context_state)
    output(feedback_prompter.suggest(taste, context=context), args.human)


def cmd_feedback_mark_prompted(args, context_state, feedback_prompter, **_):
    context = args.context or _active_context_value(context_state)
    if not context:
        error("Nenhum contexto informado ou ativo.", "NO_CONTEXT")
    output(feedback_prompter.mark_prompted(context), args.human)


def cmd_flow_review(args, context_state, flow_analyzer, **_):
    context, context_source = _curation_context(args, context_state)
    result = flow_analyzer.review(
        context,
        window=args.window,
        streak_threshold=args.streak_threshold,
        negative_rate_threshold=args.negative_rate_threshold,
    )
    output({"context_source": context_source, **result}, args.human)


def cmd_status(args, controller, taste, context_state, feedback_prompter, **_):
    active_context = context_state.show()
    context = active_context["context"] if active_context else None
    playlist_tracks = safe_call(lambda: controller.playlist_tracks(PLAYLIST_ID), "PLAYLIST_ERROR")
    playlist_count = len(playlist_tracks) if isinstance(playlist_tracks, list) else None

    output({
        "now": safe_call(controller.now, "PLAYBACK_ERROR"),
        "context": active_context or {"status": "unset", "context": None},
        "playlist": {
            "id": PLAYLIST_ID,
            "count": playlist_count,
            "error": playlist_tracks if isinstance(playlist_tracks, dict) else None,
        },
        "taste": taste_summary(taste),
        "feedback_suggestion": feedback_prompter.suggest(taste, context=context),
    }, args.human)


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


def _signal_weight(signal):
    if signal == "good":
        return 1
    if signal in ("bad", "skip"):
        return -1
    return 0


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
        os.path.abspath(__file__),
        "director",
        "run",
        "--interval",
        str(args.interval),
        "--count",
        str(args.count),
        "--target",
        str(args.target),
        "--import-outside",
        args.import_outside,
        "--outside-min-plays",
        str(args.outside_min_plays),
        "--outside-count",
        str(args.outside_count),
        "--outside-recent-limit",
        str(args.outside_recent_limit),
        "--max-per-artist",
        str(args.max_per_artist),
        "--max-artist-share",
        str(args.max_artist_share),
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
        os.kill(pid, signal.SIGTERM)
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


def main():
    parser = argparse.ArgumentParser(prog="maestra", description="Spotify Controller para Iris")
    parser.add_argument("--human", "-H", action="store_true", help="Saída legível em vez de JSON")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # status
    subparsers.add_parser("status", help="Estado agregado para agentes de IA")

    # start
    subparsers.add_parser("start", help="Inicializa: ativa dispositivo, toca Sincronia Iris, confirma playback")

    # now
    subparsers.add_parser("now", help="O que está tocando")

    # devices
    subparsers.add_parser("devices", help="Dispositivos ativos")

    # play
    p = subparsers.add_parser("play", help="Toca URI ou resume")
    p.add_argument("uri", nargs="?", default=None, help="URI do Spotify (track, playlist, album)")

    # pause
    subparsers.add_parser("pause", help="Pausa playback")

    # next
    subparsers.add_parser("next", help="Próxima faixa")

    # search
    p = subparsers.add_parser("search", help="Busca no Spotify")
    p.add_argument("query", help="Termo de busca")
    p.add_argument("--type", default="track", choices=["track", "artist", "album"])
    p.add_argument("--limit", type=int, default=10)

    # queue
    subparsers.add_parser("queue", help="Lista fila atual")

    # queue-add
    p = subparsers.add_parser("queue-add", help="Adiciona à fila")
    p.add_argument("uri", help="URI da faixa")

    # queue-context
    p = subparsers.add_parser("queue-context", help="Curadoria por contexto e adiciona à fila")
    p.add_argument("context", nargs="?", default=None, help="Contexto musical")
    p.add_argument("--count", type=int, default=3)

    # play-context
    p = subparsers.add_parser("play-context", help="Curadoria por contexto e toca imediatamente")
    p.add_argument("context", nargs="?", default=None, help="Contexto musical")

    # playlist
    playlist_parser = subparsers.add_parser("playlist", help="Gerencia Sincronia Iris")
    playlist_sub = playlist_parser.add_subparsers(dest="playlist_command", required=True)

    playlist_sub.add_parser("list", help="Lista faixas da playlist")

    p = playlist_sub.add_parser("add", help="Adiciona faixas por contexto")
    p.add_argument("context", nargs="?", default=None, help="Contexto: mood, atividade ou referência")
    p.add_argument("--count", type=int, default=5)

    p = playlist_sub.add_parser("top-up", help="Complementa a playlist até um alvo de faixas")
    p.add_argument("context", nargs="?", default=None, help="Contexto usado para buscar novas faixas")
    p.add_argument("--target", type=int, default=15, help="Quantidade alvo de faixas na playlist")

    playlist_sub.add_parser("clean", help="Remove faixas rejeitadas")
    p = playlist_sub.add_parser("remove", help="Remove URIs específicas da playlist")
    p.add_argument("uris", nargs="+", help="URIs das faixas a remover")
    p = playlist_sub.add_parser("prune", help="Poda contextual da playlist; dry-run por padrão")
    p.add_argument("--context", help="Contexto para avaliar; usa contexto ativo se omitido")
    p.add_argument("--confirm", action="store_true", help="Aplica a remoção dos candidatos")
    playlist_sub.add_parser("clear", help="Limpa toda a playlist")

    # taste
    taste_parser = subparsers.add_parser("taste", help="Perfil de gosto")
    taste_sub = taste_parser.add_subparsers(dest="taste_command", required=True)

    taste_sub.add_parser("show", help="Resumo do perfil")
    p = taste_sub.add_parser("review", help="Revisão contextual da playlist e dos sinais")
    p.add_argument("--context", help="Contexto para revisar; usa contexto ativo se omitido")
    p.add_argument("--top", type=int, default=10, help="Quantidade de itens por seção")

    p = taste_sub.add_parser("feedback", help="Registra feedback")
    p.add_argument("uri", help="URI da faixa")
    p.add_argument("feedback", choices=["good", "bad", "skip"])
    p.add_argument("--context", help="Contexto em que o feedback vale")
    p.add_argument("--source", default="explicit", choices=["explicit", "implicit", "listened_to_end", "replay"])
    p.add_argument("--global", dest="global_feedback", action="store_true", help="Registra feedback global, mesmo com contexto")

    taste_sub.add_parser("context-map", help="Mapeamento contexto→busca")

    # context
    context_parser = subparsers.add_parser("context", help="Contexto musical ativo")
    context_sub = context_parser.add_subparsers(dest="context_command", required=True)

    p = context_sub.add_parser("set", help="Define o contexto ativo")
    p.add_argument("context", help="Contexto: foco, energia, revisão, etc.")
    p.add_argument("--ttl", type=int, default=120, help="Validade em minutos")

    context_sub.add_parser("show", help="Mostra o contexto ativo")
    context_sub.add_parser("clear", help="Limpa o contexto ativo")

    # playback
    playback_parser = subparsers.add_parser("playback", help="Observa eventos conservadores de playback")
    playback_sub = playback_parser.add_subparsers(dest="playback_command", required=True)
    playback_sub.add_parser("observe", help="Observa o playback atual e registra eventos")
    playback_sub.add_parser("session-end", help="Registra encerramento neutro da sessão")
    playback_sub.add_parser("process-events", help="Converte eventos elegíveis em sinais contextuais")

    # feedback
    feedback_parser = subparsers.add_parser("feedback", help="Sugere microperguntas de feedback")
    feedback_sub = feedback_parser.add_subparsers(dest="feedback_command", required=True)

    p = feedback_sub.add_parser("suggest", help="Sugere se vale perguntar algo ao usuário")
    p.add_argument("--context", help="Contexto a avaliar; usa contexto ativo se omitido")

    p = feedback_sub.add_parser("mark-prompted", help="Registra que a pergunta foi feita")
    p.add_argument("--context", help="Contexto perguntado; usa contexto ativo se omitido")

    # flow
    flow_parser = subparsers.add_parser("flow", help="Analisa saúde do fluxo musical")
    flow_sub = flow_parser.add_subparsers(dest="flow_command", required=True)

    p = flow_sub.add_parser("review", help="Detecta deriva negativa por sequência/taxa")
    p.add_argument("--context", help="Contexto para revisar; usa contexto ativo se omitido")
    p.add_argument("--window", type=int, default=10, help="Quantidade de sinais recentes a considerar")
    p.add_argument("--streak-threshold", type=int, default=3, help="Sequência negativa para alerta")
    p.add_argument("--negative-rate-threshold", type=float, default=0.3, help="Taxa negativa para alerta")

    # history
    history_parser = subparsers.add_parser("history", help="Analisa histórico Spotify sem alterar gosto")
    history_sub = history_parser.add_subparsers(dest="history_command", required=True)

    p = history_sub.add_parser("recent", help="Lista faixas tocadas recentemente")
    p.add_argument("--limit", type=int, default=50)

    p = history_sub.add_parser("top-tracks", help="Lista top faixas")
    p.add_argument("--range", default="medium_term", choices=["short_term", "medium_term", "long_term"])
    p.add_argument("--limit", type=int, default=20)

    p = history_sub.add_parser("top-artists", help="Lista top artistas")
    p.add_argument("--range", default="medium_term", choices=["short_term", "medium_term", "long_term"])
    p.add_argument("--limit", type=int, default=20)

    p = history_sub.add_parser("analyze", help="Análise pontual do histórico")
    p.add_argument("--recent-limit", type=int, default=50)
    p.add_argument("--top-limit", type=int, default=20)

    p = history_sub.add_parser("outside-playlist", help="Lista recentes fora da Sincronia Iris")
    p.add_argument("--recent-limit", type=int, default=50)
    p.add_argument("--playlist-id", default=PLAYLIST_ID)

    p = history_sub.add_parser("import-outside", help="Importa recentes fora da playlist para o contexto ativo")
    p.add_argument("--recent-limit", type=int, default=50)
    p.add_argument("--count", type=int, default=5)
    p.add_argument("--min-plays", type=int, default=1)
    p.add_argument("--context", help="Contexto para registrar as faixas; usa contexto ativo se omitido")
    p.add_argument("--signal", default="good", choices=["good", "bad", "skip"])
    p.add_argument("--dry-run", action="store_true", help="Mostra candidatos sem alterar playlist ou memória")

    # curate
    p = subparsers.add_parser("curate", help="Gera faixas sem adicionar (dry-run)")
    p.add_argument("context", nargs="?", default=None, help="Contexto")
    p.add_argument("--count", type=int, default=5)

    # director
    director_parser = subparsers.add_parser("director", help="Diretor musical do repertorio contextual")
    director_sub = director_parser.add_subparsers(dest="director_command", required=True)

    p = director_sub.add_parser("once", help="Executa um ciclo do director")
    p.add_argument("--count", type=int, default=2, help="Quantidade de faixas a adicionar quando agir")
    p.add_argument("--target", type=int, default=40, help="Alvo de faixas no buffer do contexto ativo")
    p.add_argument("--dry-run", action="store_true", help="Decide sem alterar playlist")
    p.add_argument("--import-outside", default="off", choices=["off", "safe"], help="Importa recentes fora da playlist em modo seguro")
    p.add_argument("--outside-min-plays", type=int, default=2, help="Mínimo de execuções para import automático seguro")
    p.add_argument("--outside-count", type=int, default=2, help="Máximo de faixas fora da playlist por ciclo")
    p.add_argument("--outside-recent-limit", type=int, default=50, help="Janela de histórico recente para import automático")
    p.add_argument("--max-per-artist", type=int, default=1, help="Máximo de faixas por artista em cada lote curado")
    p.add_argument("--max-artist-share", type=float, default=0.25, help="Bloqueia artista que exceder essa fração da playlist")

    p = director_sub.add_parser("run", help="Loop interno usado por start")
    p.add_argument("--interval", type=int, default=180)
    p.add_argument("--count", type=int, default=2)
    p.add_argument("--target", type=int, default=40)
    p.add_argument("--import-outside", default="off", choices=["off", "safe"])
    p.add_argument("--outside-min-plays", type=int, default=2)
    p.add_argument("--outside-count", type=int, default=2)
    p.add_argument("--outside-recent-limit", type=int, default=50)
    p.add_argument("--max-per-artist", type=int, default=1)
    p.add_argument("--max-artist-share", type=float, default=0.25)

    p = director_sub.add_parser("start", help="Inicia director em background")
    p.add_argument("--interval", type=int, default=180)
    p.add_argument("--count", type=int, default=2)
    p.add_argument("--target", type=int, default=40)
    p.add_argument("--import-outside", default="off", choices=["off", "safe"])
    p.add_argument("--outside-min-plays", type=int, default=2)
    p.add_argument("--outside-count", type=int, default=2)
    p.add_argument("--outside-recent-limit", type=int, default=50)
    p.add_argument("--max-per-artist", type=int, default=1)
    p.add_argument("--max-artist-share", type=float, default=0.25)

    director_sub.add_parser("stop", help="Para director em background")
    director_sub.add_parser("status", help="Mostra estado do director")

    # auth (stub v0.1.0 — implementado no Plano 3)
    auth_parser = subparsers.add_parser("auth", help="Autenticação Spotify")
    auth_sub = auth_parser.add_subparsers(dest="auth_command", required=True)
    auth_sub.add_parser("setup", help="Configura client_id/secret")
    auth_sub.add_parser("login", help="Autentica via OAuth")

    # onboard (stub v0.1.0 — implementado no Plano 3)
    onboard_parser = subparsers.add_parser("onboard", help="Bootstrap do perfil por histórico")
    onboard_parser.add_argument("--playlist-name", default="Maestra")
    onboard_parser.add_argument("--seed-playlist", type=int, default=30)

    args = parser.parse_args()

    # Short-circuit stubs antes de instanciar SpotifyController
    if args.command == "auth":
        print(f"auth {args.auth_command}: stub v0.1.0 — implementado no Plano 3")
        return 0
    if args.command == "onboard":
        print("onboard: stub v0.1.0 — implementado no Plano 3")
        return 0

    # Inicializa componentes
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

    # Dispatch
    dispatch = {
        "status": cmd_status,
        "start": cmd_start,
        "now": cmd_now,
        "devices": cmd_devices,
        "play": cmd_play,
        "pause": cmd_pause,
        "next": cmd_next,
        "search": cmd_search,
        "queue": cmd_queue,
        "queue-add": cmd_queue_add,
        "queue-context": cmd_queue_context,
        "play-context": cmd_play_context,
        "curate": cmd_curate,
    }

    playlist_dispatch = {
        "list": cmd_playlist_list,
        "add": cmd_playlist_add,
        "top-up": cmd_playlist_top_up,
        "clean": cmd_playlist_clean,
        "remove": cmd_playlist_remove,
        "prune": cmd_playlist_prune,
        "clear": cmd_playlist_clear,
    }

    taste_dispatch = {
        "show": cmd_taste_show,
        "review": cmd_taste_review,
        "feedback": cmd_taste_feedback,
        "context-map": cmd_taste_context_map,
    }

    context_dispatch = {
        "set": cmd_context_set,
        "show": cmd_context_show,
        "clear": cmd_context_clear,
    }

    playback_dispatch = {
        "observe": cmd_playback_observe,
        "session-end": cmd_playback_session_end,
        "process-events": cmd_playback_process_events,
    }

    feedback_dispatch = {
        "suggest": cmd_feedback_suggest,
        "mark-prompted": cmd_feedback_mark_prompted,
    }

    flow_dispatch = {
        "review": cmd_flow_review,
    }

    history_dispatch = {
        "recent": cmd_history_recent,
        "top-tracks": cmd_history_top_tracks,
        "top-artists": cmd_history_top_artists,
        "analyze": cmd_history_analyze,
        "outside-playlist": cmd_history_outside_playlist,
        "import-outside": cmd_history_import_outside,
    }

    director_dispatch = {
        "once": cmd_director_once,
        "run": cmd_director_run,
        "start": cmd_director_start,
        "stop": cmd_director_stop,
        "status": cmd_director_status,
    }

    if args.command == "playlist":
        handler = playlist_dispatch[args.playlist_command]
    elif args.command == "taste":
        handler = taste_dispatch[args.taste_command]
    elif args.command == "context":
        handler = context_dispatch[args.context_command]
    elif args.command == "playback":
        handler = playback_dispatch[args.playback_command]
    elif args.command == "feedback":
        handler = feedback_dispatch[args.feedback_command]
    elif args.command == "flow":
        handler = flow_dispatch[args.flow_command]
    elif args.command == "history":
        handler = history_dispatch[args.history_command]
    elif args.command == "director":
        handler = director_dispatch[args.director_command]
    else:
        handler = dispatch[args.command]

    handler(
        args,
        controller=controller,
        taste=taste,
        curator=curator,
        context_state=context_state,
        playback_observer=playback_observer,
        playback_processor=playback_processor,
        feedback_prompter=feedback_prompter,
        history_analyzer=history_analyzer,
        flow_analyzer=flow_analyzer,
        director=director,
    )


if __name__ == "__main__":
    main()
