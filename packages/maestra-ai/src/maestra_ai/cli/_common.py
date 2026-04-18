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
    """Imprime erro em JSON para stderr e sai com código 1.

    A mensagem passa por `redact_str` antes da serialização para evitar
    vazamento de tokens Bearer ou secrets longos embutidos em strings
    de exceção (spotipy etc.) — ver P0-R1 do review pós-v0.2.3.
    """
    from maestra_ai.core.security import redact_str
    safe_message = redact_str(message)
    print(json.dumps({"error": safe_message, "code": code}, ensure_ascii=False), file=sys.stderr)
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
    """Shim — delega para core.taste._prune_candidates."""
    from maestra_ai.core import taste as taste_mod
    return taste_mod._prune_candidates(tracks, taste, context)


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


def _context_review(tracks, taste, context, prune_candidates=None, top=10):
    """Delega para core.taste.review — mantido como shim para callers em cli."""
    from maestra_ai.core import taste as taste_mod
    return taste_mod.review(taste, tracks, context, prune_candidates=prune_candidates, top=top)


def _signal_weight(signal):
    """Shim — delega para core.taste._signal_weight."""
    from maestra_ai.core import taste as taste_mod
    return taste_mod._signal_weight(signal)
