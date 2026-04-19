"""Helper para instanciar cores maestra_ai uma vez por processo MCP.

MCP stdio server tem vida longa (enquanto o agente estiver rodando),
então cacheamos as instâncias. SpotifyController é thread-safe via
rate limit persistente (v0.2.5).
"""
from __future__ import annotations

import threading


_CACHE: dict | None = None
# Fix M1: lock protege o double-checked assignment quando múltiplas
# threads chamam build_deps() antes do cache ser populado (ex.: SDKs MCP
# que despacham tools em thread pool).
_LOCK = threading.Lock()


def _reset() -> None:
    """Invalida o cache (uso: testes, ou após `auth login` rebuildar)."""
    global _CACHE
    with _LOCK:
        _CACHE = None


def build_deps() -> dict:
    """Retorna dict com controller, taste, curator, context_state, etc.

    Instancia cada classe uma vez por processo. Valores compatíveis com
    os handlers de tool.
    """
    global _CACHE
    # Double-checked locking: leitura sem lock no caminho quente,
    # lock só quando for realmente necessário inicializar.
    if _CACHE is not None:
        return _CACHE
    with _LOCK:
        if _CACHE is not None:
            return _CACHE
        return _build_and_cache()


def _build_and_cache() -> dict:
    """Constrói dependências e armazena em _CACHE. Chamar com _LOCK segurado."""
    global _CACHE

    from maestra_ai.core.client import SpotifyController
    from maestra_ai.core.context import ContextState
    from maestra_ai.core.curator import Curator
    from maestra_ai.core.director import MusicDirector
    from maestra_ai.core.flow import FlowAnalyzer
    from maestra_ai.core.history import HistoryAnalyzer
    from maestra_ai.core.playback import PlaybackObserver
    from maestra_ai.core.storage import data_dir
    from maestra_ai.core.taste import TasteProfile

    base = data_dir()
    taste = TasteProfile(str(base / "taste_profile.json"))
    context_state = ContextState(str(base / "current_context.json"))
    controller = SpotifyController()
    history_analyzer = HistoryAnalyzer(controller)
    flow_analyzer = FlowAnalyzer(taste)
    curator = Curator(controller, taste)
    playback_observer = PlaybackObserver(
        str(base / "playback_state.json"),
        str(base / "playback_events.jsonl"),
    )
    # v0.4.4 CRITICAL-2: resolve playlist_id via config. Se ausente, fica
    # None — tools que precisam da playlist (director_once) vão falhar com
    # erro tipado do core em vez de TypeError em .playlist_tracks(None).
    from maestra_mcp.config import resolve_playlist_id
    try:
        playlist_id = resolve_playlist_id()
    except Exception:
        playlist_id = None
    director = MusicDirector(
        controller, curator, taste, context_state,
        str(base / "director_decisions.jsonl"),
        playlist_id=playlist_id,
        history_analyzer=history_analyzer,
    )

    _CACHE = {
        "controller": controller,
        "taste": taste,
        "context_state": context_state,
        "curator": curator,
        "director": director,
        "flow_analyzer": flow_analyzer,
        "history_analyzer": history_analyzer,
        "playback_observer": playback_observer,
    }
    return _CACHE
