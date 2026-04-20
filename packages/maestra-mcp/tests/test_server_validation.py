"""Testes de validação de args MCP contra inputSchema (I5 v0.6.1)."""
from __future__ import annotations

import pytest


@pytest.fixture
def register_test_tool(monkeypatch):
    """Registra uma tool de teste com schema estrito para validação."""
    from maestra_mcp import tools as tools_mod

    original_registry = dict(tools_mod._REGISTRY)

    schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 50},
        },
        "required": ["query"],
        "additionalProperties": False,
    }

    async def handler(args):
        return {"ok": True, "received": args}

    from maestra_mcp.tools import ToolDef
    tools_mod._REGISTRY["_test_tool"] = ToolDef(
        name="_test_tool",
        description="tool de teste",
        schema=schema,
        handler=handler,
    )
    yield
    tools_mod._REGISTRY.clear()
    tools_mod._REGISTRY.update(original_registry)


class TestValidacaoArgs:
    async def test_additional_properties_rejeita_campo_desconhecido(
        self, register_test_tool,
    ):
        from maestra_mcp.tools import call_tool
        result = await call_tool("_test_tool", {"query": "x", "extra": "y"})
        assert "error" in result
        assert result["error"]["code"] == "MCPInvalidArgsError"
        assert "extra" in result["error"]["agent_hint"] or "desconhecido" in result["error"]["agent_hint"]

    async def test_minimum_rejeita_valor_fora(self, register_test_tool):
        from maestra_mcp.tools import call_tool
        result = await call_tool("_test_tool", {"query": "x", "limit": 0})
        assert "error" in result
        assert result["error"]["code"] == "MCPInvalidArgsError"

    async def test_required_rejeita_ausencia(self, register_test_tool):
        from maestra_mcp.tools import call_tool
        result = await call_tool("_test_tool", {})
        assert "error" in result
        assert result["error"]["code"] == "MCPInvalidArgsError"
        assert "query" in result["error"]["agent_hint"]

    async def test_args_validos_passam(self, register_test_tool):
        from maestra_mcp.tools import call_tool
        result = await call_tool("_test_tool", {"query": "x", "limit": 10})
        assert result == {"ok": True, "received": {"query": "x", "limit": 10}}
