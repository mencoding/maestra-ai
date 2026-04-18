"""Registry de tools MCP (stub mínimo para Task 7 — expandido em Tasks 8-10)."""
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
# Stub — tool `doctor` para validar o list_tools em Task 7.
# Será sobrescrita/expandida em Task 10 com os demais handlers.
# =========================================================================

@tool("doctor",
      "Executa os checks de diagnóstico (paridade com `maestra doctor`).",
      {"type": "object", "properties": {}, "additionalProperties": False})
def _doctor(args):
    from maestra_ai.core import doctor as doctor_mod
    return {"checks": doctor_mod.run_all()}
