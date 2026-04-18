"""MCP stdio server para Maestra AI."""
from __future__ import annotations

import asyncio
import json
import logging
import sys

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

from maestra_mcp.tools import call_tool, iter_tool_defs


logger = logging.getLogger("maestra-mcp")


def _disabled_tools() -> set[str]:
    from maestra_ai.core import storage
    cfg = storage.read_config()
    raw = (cfg.get("mcp") or {}).get("disabled_tools", [])
    if not isinstance(raw, list):
        logger.warning("mcp.disabled_tools deve ser lista; ignorando.")
        return set()
    return set(raw)


def _build_list_tools_handler():
    async def _list_tools() -> list[types.Tool]:
        disabled = _disabled_tools()
        return [
            types.Tool(
                name=t.name,
                description=t.description,
                inputSchema=t.schema,
            )
            for t in iter_tool_defs()
            if t.name not in disabled
        ]
    return _list_tools


def _build_call_tool_handler():
    async def _call_tool(name: str, args: dict) -> list[types.TextContent]:
        from maestra_ai.core import audit
        from maestra_ai.core.errors import UserError

        disabled = _disabled_tools()
        if name in disabled:
            err = UserError(f"Tool desabilitada via config: {name}")
            return [types.TextContent(
                type="text",
                text=json.dumps({"error": err.to_human_dict()}, ensure_ascii=False),
            )]

        # Fix H4: envolve a chamada para garantir auditoria mesmo quando
        # o handler (ou tools.call_tool) propaga exceção não-tratada. Antes,
        # qualquer erro fora do try/except do registry pulava o audit.log
        # e o cliente MCP recebia erro opaco sem trilha forense.
        try:
            result = await call_tool(name, args or {})
        except Exception as e:
            result = {
                "error": {
                    "code": "InternalError",
                    "title": "Erro não tratado em tool",
                    "what_happened": str(e),
                },
            }

        try:
            log_result = result if isinstance(result, dict) else {"raw": str(result)}
            audit.log(name, args or {}, log_result)
        except Exception as e:
            logger.warning("audit log failed: %s", e)

        return [types.TextContent(
            type="text",
            text=json.dumps(result, ensure_ascii=False),
        )]
    return _call_tool


def create_server() -> Server:
    """Cria instância do Server com handlers registrados."""
    server = Server("maestra")
    server.list_tools()(_build_list_tools_handler())
    server.call_tool()(_build_call_tool_handler())
    return server


async def _run() -> int:
    server = create_server()
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())
    return 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    try:
        return asyncio.run(_run())
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
