"""Helpers e constantes compartilhados entre subcomandos do CLI."""
from __future__ import annotations

import json
import os
import sys
from collections import Counter

from maestra_ai.core.curator import DEFAULT_CONTEXT
from maestra_ai.core.storage import data_dir


BASE_DIR = str(data_dir())
os.makedirs(BASE_DIR, exist_ok=True)

TASTE_PATH = os.path.join(BASE_DIR, "taste_profile.json")
CONTEXT_PATH = os.path.join(BASE_DIR, "current_context.json")
PLAYBACK_STATE_PATH = os.path.join(BASE_DIR, "playback_state.json")
PLAYBACK_EVENTS_PATH = os.path.join(BASE_DIR, "playback_events.jsonl")
FEEDBACK_PROMPT_STATE_PATH = os.path.join(BASE_DIR, "feedback_prompt_state.json")
DIRECTOR_PID_PATH = os.path.join(BASE_DIR, "director.pid")
DIRECTOR_STDOUT_LOG_PATH = os.path.join(BASE_DIR, "director.log")
DIRECTOR_DECISIONS_PATH = os.path.join(BASE_DIR, "director_decisions.jsonl")

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


def _curation_context(args, context_state):
    """Resolve contexto de curadoria: argumento, contexto ativo ou fallback."""
    raw_context = getattr(args, "context", None)
    if raw_context and raw_context.strip():
        return raw_context.strip(), "argument"

    active_context = context_state.show()
    if active_context:
        return active_context["context"], "active"

    return DEFAULT_CONTEXT, "default"


def _record_curated_tracks(taste, tracks, context, queries_used):
    tracks_info = [{"uri": r["uri"], "name": r["track"], "artist": r["artist"]} for r in tracks]
    taste.record_added(tracks_info, context=context, queries_used=queries_used)


def _active_context_value(context_state):
    active_context = context_state.show()
    if not active_context:
        return None
    return active_context["context"]


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


def _signal_weight(signal):
    if signal == "good":
        return 1
    if signal in ("bad", "skip"):
        return -1
    return 0
