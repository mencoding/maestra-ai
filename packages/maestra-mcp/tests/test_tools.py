"""Testes do registry + handlers individuais (mock do core)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_tool_registry_nao_vazio():
    from maestra_mcp.tools import iter_tool_defs
    assert len(iter_tool_defs()) >= 11  # playback(7) + contexto(3) + curate(1)


@pytest.mark.asyncio
async def test_unknown_tool_retorna_erro_user():
    from maestra_mcp.tools import call_tool
    result = await call_tool("does_not_exist", {})
    assert "error" in result
    assert result["error"]["code"] == "UserError"


@pytest.mark.asyncio
async def test_now_chama_controller_now():
    from maestra_mcp.tools import call_tool
    mock_ctrl = MagicMock()
    mock_ctrl.now.return_value = {"track": "T", "artist": "A"}
    with patch("maestra_mcp.tools.build_deps", return_value={"controller": mock_ctrl}):
        result = await call_tool("now", {})
    assert result["track"] == "T"


@pytest.mark.asyncio
async def test_set_context_chama_context_state_set():
    from maestra_mcp.tools import call_tool
    mock_ctx = MagicMock()
    mock_ctx.set.return_value = {"context": "foco", "set_at": "t"}
    with patch("maestra_mcp.tools.build_deps", return_value={"context_state": mock_ctx}):
        result = await call_tool("set_context", {"description": "foco denso"})
    mock_ctx.set.assert_called_once_with("foco denso")
    assert result["context"] == "foco"


@pytest.mark.asyncio
async def test_curate_passa_args_para_curator():
    from maestra_mcp.tools import call_tool
    mock_curator = MagicMock()
    mock_curator.curate.return_value = ([], [])
    mock_ctx = MagicMock()
    mock_ctx.show.return_value = {"context": "foco"}
    with patch("maestra_mcp.tools.build_deps",
               return_value={"curator": mock_curator, "context_state": mock_ctx}):
        await call_tool("curate", {"max_tracks": 5, "max_per_artist": 2})
    assert mock_curator.curate.called
    kwargs = mock_curator.curate.call_args.kwargs
    assert kwargs.get("count") == 5 or mock_curator.curate.call_args.args[1] == 5


@pytest.mark.asyncio
async def test_maestra_error_vira_error_dict():
    from maestra_mcp.tools import call_tool
    from maestra_ai.core.errors import AuthError
    mock_ctrl = MagicMock()
    mock_ctrl.now.side_effect = AuthError("token revogado")
    with patch("maestra_mcp.tools.build_deps", return_value={"controller": mock_ctrl}):
        result = await call_tool("now", {})
    assert "error" in result
    assert result["error"]["code"] == "AuthError"
    assert "agent_hint" in result["error"]
