"""Registry de tools MCP e handlers (Task 8: playback + contexto + curate)."""
from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from maestra_mcp.deps import build_deps  # noqa: F401 — reexportado para patch em testes


@dataclass
class ToolDef:
    name: str
    description: str
    schema: dict
    handler: Callable[[dict], Awaitable[Any]]


_REGISTRY: dict[str, ToolDef] = {}


def tool(name: str, description: str, schema: dict):
    """Decorator que registra o handler em _REGISTRY."""
    def deco(fn):
        async def wrapper(args: dict):
            if inspect.iscoroutinefunction(fn):
                return await fn(args)
            return fn(args)
        _REGISTRY[name] = ToolDef(
            name=name, description=description, schema=schema, handler=wrapper,
        )
        return fn
    return deco


def iter_tool_defs() -> list[ToolDef]:
    return list(_REGISTRY.values())


async def call_tool(name: str, args: dict) -> Any:
    """Dispatch para o handler registrado. Captura MaestraError e genéricas."""
    td = _REGISTRY.get(name)
    if td is None:
        from maestra_ai.core.errors import UserError
        err = UserError(f"Tool '{name}' não existe.")
        return {"error": err.to_human_dict()}
    try:
        return await td.handler(args)
    except Exception as e:
        from maestra_ai.core.errors import MaestraError
        if isinstance(e, MaestraError):
            return {"error": e.to_human_dict()}
        return {
            "error": {
                "code": type(e).__name__,
                "title": "Erro inesperado",
                "what_happened": str(e),
            },
        }


# =========================================================================
# Playback (7)
# =========================================================================

@tool("now",
      "Mostra a faixa atual com progresso e dispositivo.",
      {"type": "object", "properties": {}, "additionalProperties": False})
def _now(args):
    ctrl = build_deps()["controller"]
    return ctrl.now()


@tool("play",
      "Toca playback. Sem args retoma. track_uri toca faixa específica. "
      "context_uri toca playlist/álbum.",
      {"type": "object", "properties": {
          "track_uri": {"type": "string"},
          "context_uri": {"type": "string"},
      }, "additionalProperties": False})
def _play(args):
    ctrl = build_deps()["controller"]
    uri = args.get("track_uri") or args.get("context_uri")
    return ctrl.play(uri=uri)


@tool("pause", "Pausa playback.",
      {"type": "object", "properties": {}, "additionalProperties": False})
def _pause(args):
    return build_deps()["controller"].pause()


@tool("skip", "Pula para próxima faixa.",
      {"type": "object", "properties": {}, "additionalProperties": False})
def _skip(args):
    return build_deps()["controller"].next_track()


@tool("queue", "Adiciona URI à fila do Spotify.",
      {"type": "object", "properties": {
          "track_uri": {"type": "string"},
      }, "required": ["track_uri"], "additionalProperties": False})
def _queue(args):
    return build_deps()["controller"].queue_add(args["track_uri"])


@tool("search", "Busca faixas no Spotify.",
      {"type": "object", "properties": {
          "query": {"type": "string"},
          "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
      }, "required": ["query"], "additionalProperties": False})
def _search(args):
    return build_deps()["controller"].search(
        args["query"], type="track", limit=args.get("limit", 10),
    )


@tool("devices", "Lista dispositivos de playback disponíveis.",
      {"type": "object", "properties": {}, "additionalProperties": False})
def _devices(args):
    return build_deps()["controller"].devices()


# =========================================================================
# Contexto (3) + Curadoria (1)
# =========================================================================

@tool("set_context",
      "Define o contexto musical ativo — descrição em linguagem natural. "
      "Usado ANTES de curate(). Exemplos: 'foco denso ambient noir', "
      "'indie folk melancólico para leitura'. Evite termos vagos.",
      {"type": "object", "properties": {
          "description": {"type": "string", "minLength": 3, "maxLength": 500},
      }, "required": ["description"], "additionalProperties": False})
def _set_context(args):
    return build_deps()["context_state"].set(args["description"])


@tool("get_context", "Retorna o contexto ativo.",
      {"type": "object", "properties": {}, "additionalProperties": False})
def _get_context(args):
    ctx = build_deps()["context_state"].show()
    return ctx if ctx is not None else {"context": None}


@tool("clear_context", "Limpa o contexto ativo.",
      {"type": "object", "properties": {}, "additionalProperties": False})
def _clear_context(args):
    return build_deps()["context_state"].clear()


@tool("curate",
      "Popula a playlist Maestra com faixas aderentes ao contexto ativo. "
      "max_tracks limita o batch. max_per_artist controla diversidade.",
      {"type": "object", "properties": {
          "max_tracks": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
          "max_per_artist": {"type": "integer", "minimum": 1, "maximum": 10, "default": 1},
      }, "additionalProperties": False})
def _curate(args):
    deps = build_deps()
    ctx = deps["context_state"].show()
    context_name = (ctx or {}).get("context", "default")
    tracks, queries = deps["curator"].curate(
        context_name,
        count=args.get("max_tracks", 10),
        max_per_artist=args.get("max_per_artist", 1),
    )
    return {
        "context": context_name,
        "tracks": tracks,
        "queries_used": queries,
    }


# =========================================================================
# Análise (3)
# =========================================================================

@tool("flow_review",
      "Analisa saúde do contexto: streak de rejeições, taxa negativa, "
      "termos comuns. Só diagnostica, não age.",
      {"type": "object", "properties": {
          "window": {"type": "integer", "minimum": 3, "maximum": 100, "default": 10},
          "context": {"type": "string"},
      }, "additionalProperties": False})
def _flow_review(args):
    deps = build_deps()
    ctx = args.get("context") or (deps["context_state"].show() or {}).get("context")
    return deps["flow_analyzer"].review(context=ctx, window=args.get("window", 10))


@tool("taste_review",
      "Resumo do perfil no contexto: top positivos, negativos, "
      "dominantes, candidatos de poda.",
      {"type": "object", "properties": {
          "top": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
          "context": {"type": "string"},
      }, "additionalProperties": False})
def _taste_review(args):
    from maestra_ai.core import taste as taste_mod
    from maestra_mcp.config import resolve_playlist_id

    deps = build_deps()
    ctx = args.get("context") or (deps["context_state"].show() or {}).get("context", "")
    playlist_id = resolve_playlist_id()
    tracks = deps["controller"].playlist_tracks(playlist_id) if playlist_id else []
    return taste_mod.review(deps["taste"], tracks, ctx, top=args.get("top", 10))


@tool("history_outside_playlist",
      "Lista faixas recentes ouvidas pelo usuário que NÃO estão na playlist.",
      {"type": "object", "properties": {
          "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 50},
      }, "additionalProperties": False})
def _history_outside(args):
    from maestra_mcp.config import resolve_playlist_id
    playlist_id = resolve_playlist_id()
    if not playlist_id:
        return {"outside": [], "note": "playlist_id não configurado"}
    return build_deps()["history_analyzer"].outside_playlist(
        playlist_id, recent_limit=args.get("limit", 50),
    )


# =========================================================================
# Manutenção (3)
# =========================================================================

@tool("playlist_prune",
      "Remove faixas da playlist com sinal negativo. DRY-RUN por default. "
      "Snapshot automático antes da remoção real.",
      {"type": "object", "properties": {
          "confirm": {"type": "boolean", "default": False},
          "context": {"type": "string"},
      }, "additionalProperties": False})
def _playlist_prune(args):
    from maestra_mcp.config import resolve_playlist_id
    deps = build_deps()
    ctx = args.get("context") or (deps["context_state"].show() or {}).get("context", "")
    return deps["curator"].prune(
        playlist_id=resolve_playlist_id(),
        context=ctx,
        confirm=args.get("confirm", False),
    )


@tool("history_import_outside",
      "Importa faixas ouvidas recentemente para dentro da playlist, "
      "filtrado por min_plays. DRY-RUN default.",
      {"type": "object", "properties": {
          "confirm": {"type": "boolean", "default": False},
          "count": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
          "min_plays": {"type": "integer", "minimum": 1, "maximum": 20, "default": 2},
          "context": {"type": "string"},
      }, "additionalProperties": False})
def _history_import(args):
    from maestra_mcp.config import resolve_playlist_id
    deps = build_deps()
    ctx = args.get("context") or (deps["context_state"].show() or {}).get("context", "")
    return deps["history_analyzer"].import_outside(
        playlist_id=resolve_playlist_id(),
        context=ctx,
        confirm=args.get("confirm", False),
        count=args.get("count", 10),
        min_plays=args.get("min_plays", 2),
        taste=deps["taste"],
    )


@tool("rollback",
      "Restaura snapshot anterior. Sem snapshot_id, restaura o mais recente. "
      "list=true retorna lista sem restaurar.",
      {"type": "object", "properties": {
          "snapshot_id": {"type": "string"},
          "list": {"type": "boolean", "default": False},
      }, "additionalProperties": False})
def _rollback(args):
    from maestra_ai.core import snapshot, rollback as rb

    if args.get("list"):
        return {"snapshots": snapshot.list_snapshots()}

    deps = build_deps()
    taste = deps["taste"]
    ctx = deps["context_state"]

    def current_state_fn():
        # Captura estado atual para snapshot-de-salvaguarda
        return {
            "taste": taste.data,
            "context": ctx.show(),
        }

    def apply_state_fn(state):
        # Aplica estado do snapshot-alvo aos módulos relevantes
        if "taste" in state and state["taste"] is not None:
            taste.restore(state["taste"])
        if "context" in state:
            ctx_val = state["context"]
            if ctx_val and isinstance(ctx_val, dict) and ctx_val.get("context"):
                ttl = ctx_val.get("ttl_minutes", 120)
                ctx.set(ctx_val["context"], ttl_minutes=ttl)
            else:
                ctx.clear()

    return rb.rollback_to(
        args.get("snapshot_id"),
        current_state_fn=current_state_fn,
        apply_state_fn=apply_state_fn,
    )


# =========================================================================
# Director (4)
# =========================================================================

@tool("director_start",
      "Inicia Director em background (loop que popula playlist em lotes).",
      {"type": "object", "properties": {
          "interval": {"type": "integer", "minimum": 60, "maximum": 3600, "default": 180},
          "target": {"type": "integer", "minimum": 10, "maximum": 500, "default": 100},
          "max_per_artist": {"type": "integer", "minimum": 1, "maximum": 10, "default": 1},
          "max_artist_share": {"type": "number", "minimum": 0.05, "maximum": 1.0, "default": 0.25},
          "import_outside": {"type": "string", "enum": ["off", "safe"], "default": "off"},
      }, "additionalProperties": False})
def _director_start(args):
    from maestra_ai.core import director as director_mod
    return director_mod.start(
        interval=args.get("interval", 180),
        target=args.get("target", 100),
        max_per_artist=args.get("max_per_artist", 1),
        max_artist_share=args.get("max_artist_share", 0.25),
        import_outside=args.get("import_outside", "off"),
    )


@tool("director_stop", "Para o Director.",
      {"type": "object", "properties": {}, "additionalProperties": False})
def _director_stop(args):
    from maestra_ai.core import director as director_mod
    return director_mod.stop()


@tool("director_status", "Status atual do Director.",
      {"type": "object", "properties": {}, "additionalProperties": False})
def _director_status(args):
    from maestra_ai.core import director as director_mod
    return director_mod.status()


@tool("director_once", "Roda uma iteração síncrona do Director (sem laço).",
      {"type": "object", "properties": {
          "count": {"type": "integer", "minimum": 1, "maximum": 20, "default": 2},
      }, "additionalProperties": False})
def _director_once(args):
    return build_deps()["director"].run_once(count=args.get("count", 2))


# =========================================================================
# Onboard + Doctor (2)
# =========================================================================

@tool("onboard",
      "Bootstrap inicial: importa histórico, cria playlist, popula taste, "
      "sugere contextos. Default dry_run=True — passe dry_run:false para "
      "efetivar a criação da playlist.",
      {"type": "object", "properties": {
          "playlist_name": {"type": "string", "default": "Maestra"},
          "seed_count": {"type": "integer", "minimum": 0, "maximum": 100, "default": 30},
          "dry_run": {"type": "boolean", "default": True},
      }, "additionalProperties": False})
def _onboard(args):
    from maestra_ai.core import onboard as onboard_mod
    deps = build_deps()
    return onboard_mod.run(
        deps["controller"].sp,
        deps["taste"],
        playlist_name=args.get("playlist_name", "Maestra"),
        seed_count=args.get("seed_count", 30),
        # Default seguro: dry_run=True quando omitido, alinhado a prune/import-outside
        dry_run=args.get("dry_run", True),
    )


@tool("doctor",
      "Executa os checks de diagnóstico (paridade com `maestra doctor`).",
      {"type": "object", "properties": {}, "additionalProperties": False})
def _doctor(args):
    from maestra_ai.core import doctor as doctor_mod
    return {"checks": doctor_mod.run_all()}
