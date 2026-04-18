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


@pytest.mark.asyncio
async def test_flow_review_chama_flow_analyzer(monkeypatch):
    from maestra_mcp.tools import call_tool
    mock_flow = MagicMock()
    mock_flow.review.return_value = {"status": "ok"}
    mock_ctx = MagicMock()
    mock_ctx.show.return_value = {"context": "foco"}
    with patch("maestra_mcp.tools.build_deps",
               return_value={"flow_analyzer": mock_flow, "context_state": mock_ctx}):
        await call_tool("flow_review", {"window": 5, "context": "foco"})
    mock_flow.review.assert_called_once()


@pytest.mark.asyncio
async def test_taste_review_chama_taste_review_func(monkeypatch):
    from maestra_mcp.tools import call_tool
    mock_ctrl = MagicMock()
    mock_ctrl.playlist_tracks.return_value = []
    mock_taste = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.show.return_value = {"context": "foco"}
    with patch("maestra_mcp.tools.build_deps",
               return_value={"controller": mock_ctrl, "taste": mock_taste, "context_state": mock_ctx}), \
         patch("maestra_mcp.config.resolve_playlist_id", return_value="pl_1"), \
         patch("maestra_ai.core.taste.review", return_value={"context": "foco", "top_positive": []}) as m:
        result = await call_tool("taste_review", {"top": 5})
    m.assert_called_once()
    assert result["context"] == "foco"


@pytest.mark.asyncio
async def test_playlist_prune_dry_run():
    from maestra_mcp.tools import call_tool
    mock_curator = MagicMock()
    mock_curator.prune.return_value = {"dry_run": True, "candidates": []}
    mock_ctx = MagicMock()
    mock_ctx.show.return_value = {"context": "foco"}
    with patch("maestra_mcp.tools.build_deps",
               return_value={"curator": mock_curator, "context_state": mock_ctx}), \
         patch("maestra_mcp.config.resolve_playlist_id", return_value="pl_1"):
        result = await call_tool("playlist_prune", {})
    assert result["dry_run"] is True


@pytest.mark.asyncio
async def test_rollback_list():
    from maestra_mcp.tools import call_tool
    with patch("maestra_ai.core.snapshot.list_snapshots",
               return_value=[{"id": "snap_1", "label": "prune"}]):
        result = await call_tool("rollback", {"list": True})
    assert "snapshots" in result
    assert len(result["snapshots"]) == 1
