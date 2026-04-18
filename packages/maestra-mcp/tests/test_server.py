"""Testes do server MCP — create_server + disabled_tools."""
from __future__ import annotations

import pytest


def test_create_server_returns_mcp_server():
    from maestra_mcp.server import create_server
    s = create_server()
    assert s is not None
    assert hasattr(s, "run")


@pytest.mark.asyncio
async def test_disabled_tool_nao_aparece_em_list(monkeypatch, tmp_path):
    """Tools listadas em config.mcp.disabled_tools não aparecem no list_tools."""
    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
    from maestra_ai.core import storage
    storage.write_config({
        "client_id": "c", "client_secret": "s",
        "redirect_uri": "https://x/cb",
        "mcp": {"disabled_tools": ["now"]},
    })

    from maestra_mcp.server import _build_list_tools_handler
    handler = _build_list_tools_handler()
    tools = await handler()
    names = {t.name for t in tools}
    assert "now" not in names
    assert "doctor" in names  # outras tools continuam
