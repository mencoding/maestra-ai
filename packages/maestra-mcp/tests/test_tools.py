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
async def test_history_import_outside_defaults_alinhados_com_cli():
    # CLI expõe count=5, min_plays=1, recent_limit=50 — MCP deve espelhar.
    from maestra_mcp.tools import call_tool

    mock_history = MagicMock()
    mock_history.import_outside.return_value = {"dry_run": True, "candidates": []}
    mock_taste = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.show.return_value = {"context": "foco"}

    with patch("maestra_mcp.tools.build_deps",
               return_value={
                   "history_analyzer": mock_history,
                   "taste": mock_taste,
                   "context_state": mock_ctx,
               }), \
         patch("maestra_mcp.config.resolve_playlist_id", return_value="pl_1"):
        await call_tool("history_import_outside", {})

    kwargs = mock_history.import_outside.call_args.kwargs
    assert kwargs.get("count") == 5, f"count default esperado 5, veio {kwargs.get('count')}"
    assert kwargs.get("min_plays") == 1, \
        f"min_plays default esperado 1, veio {kwargs.get('min_plays')}"
    assert kwargs.get("recent_limit") == 50, \
        f"recent_limit default esperado 50, veio {kwargs.get('recent_limit')}"
    # Default do signal deve ser "good" — alinhado ao core e CLI
    assert kwargs.get("signal") == "good", \
        f"signal default esperado 'good', veio {kwargs.get('signal')!r}"


@pytest.mark.asyncio
async def test_history_import_outside_propaga_signal():
    """MCP deve repassar `signal` explícito ao core.import_outside."""
    from maestra_mcp.tools import call_tool

    mock_history = MagicMock()
    mock_history.import_outside.return_value = {"dry_run": True, "candidates": []}
    mock_taste = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.show.return_value = {"context": "foco"}

    with patch("maestra_mcp.tools.build_deps",
               return_value={
                   "history_analyzer": mock_history,
                   "taste": mock_taste,
                   "context_state": mock_ctx,
               }), \
         patch("maestra_mcp.config.resolve_playlist_id", return_value="pl_1"):
        await call_tool("history_import_outside", {"signal": "bad"})

    kwargs = mock_history.import_outside.call_args.kwargs
    assert kwargs.get("signal") == "bad"


@pytest.mark.asyncio
async def test_history_import_outside_rejeita_signal_invalido():
    """Signal inválido: jsonschema rejeita no boundary MCP (MCPInvalidArgsError).

    Antes de v0.6.1 o erro vinha do core (ValueError). Agora a validação de
    schema captura o enum inválido antes de invocar o handler.
    """
    from maestra_mcp.tools import call_tool

    mock_history = MagicMock()
    mock_taste = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.show.return_value = {"context": "foco"}

    with patch("maestra_mcp.tools.build_deps",
               return_value={
                   "history_analyzer": mock_history,
                   "taste": mock_taste,
                   "context_state": mock_ctx,
               }), \
         patch("maestra_mcp.config.resolve_playlist_id", return_value="pl_1"):
        result = await call_tool("history_import_outside", {"signal": "invalido"})

    assert "error" in result
    assert result["error"]["code"] == "MCPInvalidArgsError"


@pytest.mark.asyncio
async def test_rollback_executa_com_snapshot_id():
    # Verifica que o handler monta current_state_fn e apply_state_fn
    # e chama rollback_to com o snapshot_id informado.
    from maestra_mcp.tools import call_tool

    mock_taste = MagicMock()
    mock_taste.data = {"tracks": {}}
    mock_ctx = MagicMock()
    mock_ctx.show.return_value = {"context": "foco"}

    with patch("maestra_mcp.tools.build_deps",
               return_value={"taste": mock_taste, "context_state": mock_ctx}), \
         patch("maestra_ai.core.rollback.rollback_to",
               return_value={"restored": "abc", "status": "ok"}) as m:
        result = await call_tool("rollback", {"snapshot_id": "abc"})

    assert m.called, "rollback_to deveria ter sido chamado"
    kwargs = m.call_args.kwargs
    positional = m.call_args.args
    # snapshot_id pode chegar como primeiro posicional ou via kwarg snap_id
    assert (positional and positional[0] == "abc") or kwargs.get("snap_id") == "abc"
    assert "current_state_fn" in kwargs
    assert "apply_state_fn" in kwargs
    assert callable(kwargs["current_state_fn"])
    assert callable(kwargs["apply_state_fn"])
    assert result["status"] == "ok"


@pytest.mark.asyncio
async def test_rollback_list():
    from maestra_mcp.tools import call_tool
    with patch("maestra_ai.core.snapshot.list_snapshots",
               return_value=[{"id": "snap_1", "label": "prune"}]):
        result = await call_tool("rollback", {"list": True})
    assert "snapshots" in result
    assert len(result["snapshots"]) == 1


@pytest.mark.asyncio
async def test_director_start_delega_para_core():
    from maestra_mcp.tools import call_tool
    with patch("maestra_ai.core.director.start",
               return_value={"status": "started", "pid": 111}) as m:
        result = await call_tool("director_start", {"interval": 180, "target": 100})
    m.assert_called_once()
    assert result["pid"] == 111


@pytest.mark.asyncio
async def test_director_stop_delega():
    from maestra_mcp.tools import call_tool
    with patch("maestra_ai.core.director.stop",
               return_value={"status": "stopped"}):
        result = await call_tool("director_stop", {})
    assert result["status"] == "stopped"


@pytest.mark.asyncio
async def test_director_status_delega():
    from maestra_mcp.tools import call_tool
    with patch("maestra_ai.core.director.status",
               return_value={"status": "running", "pid": 222}):
        result = await call_tool("director_status", {})
    assert result["pid"] == 222


@pytest.mark.asyncio
async def test_director_once_chama_run_once():
    from maestra_mcp.tools import call_tool
    mock_director = MagicMock()
    mock_director.run_once.return_value = {"added": 2}
    with patch("maestra_mcp.tools.build_deps", return_value={"director": mock_director}):
        await call_tool("director_once", {"count": 3})
    mock_director.run_once.assert_called_once()


@pytest.mark.asyncio
async def test_onboard_default_e_dry_run():
    # Garante que chamar onboard sem argumentos é seguro: dry_run=True.
    from maestra_mcp.tools import call_tool
    mock_ctrl = MagicMock()
    mock_taste = MagicMock()
    mock_ctrl.sp = MagicMock()
    with patch("maestra_mcp.tools.build_deps",
               return_value={"controller": mock_ctrl, "taste": mock_taste}), \
         patch("maestra_ai.core.onboard.run",
               return_value={"status": "ok", "dry_run": True}) as m:
        await call_tool("onboard", {})
    kwargs = m.call_args.kwargs
    assert kwargs.get("dry_run") is True, \
        "onboard default deve ser dry_run=True para evitar mutação sem consentimento"


@pytest.mark.asyncio
async def test_onboard_chama_core_onboard_run():
    from maestra_mcp.tools import call_tool
    mock_ctrl = MagicMock()
    mock_taste = MagicMock()
    mock_ctrl.sp = MagicMock()
    with patch("maestra_mcp.tools.build_deps",
               return_value={"controller": mock_ctrl, "taste": mock_taste}), \
         patch("maestra_ai.core.onboard.run",
               return_value={"status": "ok"}) as m:
        result = await call_tool("onboard", {"playlist_name": "X", "seed_count": 0})
    m.assert_called_once()
    assert result["status"] == "ok"


@pytest.mark.asyncio
async def test_doctor_chama_run_all():
    from maestra_mcp.tools import call_tool
    with patch("maestra_ai.core.doctor.run_all",
               return_value=[{"check": "python", "status": "ok"}]) as m:
        result = await call_tool("doctor", {})
    m.assert_called_once()
    assert "checks" in result


@pytest.mark.asyncio
async def test_playlist_prune_expoe_top():
    """Fix H3: schema de playlist_prune deve aceitar e propagar `top`."""
    from maestra_mcp.tools import call_tool
    mock_curator = MagicMock()
    mock_curator.prune.return_value = {"dry_run": True, "candidates": []}
    mock_ctx = MagicMock()
    mock_ctx.show.return_value = {"context": "foco"}
    with patch("maestra_mcp.tools.build_deps",
               return_value={"curator": mock_curator, "context_state": mock_ctx}), \
         patch("maestra_mcp.config.resolve_playlist_id", return_value="pl_1"):
        await call_tool("playlist_prune", {"top": 5})
    kwargs = mock_curator.prune.call_args.kwargs
    assert kwargs.get("top") == 5, f"top deveria ser 5, veio {kwargs.get('top')}"


@pytest.mark.asyncio
async def test_history_outside_playlist_retorna_shape_consistente_sem_playlist_id():
    """Fix M4: sem playlist_id, retornar shape canônico com zeros em vez
    de dict divergente `{outside, note}`."""
    from maestra_mcp.tools import call_tool
    with patch("maestra_mcp.config.resolve_playlist_id", return_value=None):
        result = await call_tool("history_outside_playlist", {})
    expected = {
        "recent_count", "playlist_count", "outside_count",
        "outside_play_events", "top_outside_artists", "top_outside_tracks",
        "tracks", "candidates", "note",
    }
    assert expected.issubset(result.keys()), \
        f"faltam chaves canônicas: {expected - set(result.keys())}"
    assert result["outside_count"] == 0
    assert result["tracks"] == []
    assert result["candidates"] == []


@pytest.mark.asyncio
async def test_total_23_tools():
    from maestra_mcp.tools import iter_tool_defs
    assert len(iter_tool_defs()) == 23


# ---------------------------------------------------------------------------
# clear_context — N5 v0.6.2
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_clear_context_registrado_no_registry():
    """clear_context deve constar em iter_tool_defs."""
    from maestra_mcp.tools import iter_tool_defs
    names = [t.name for t in iter_tool_defs()]
    assert "clear_context" in names, f"clear_context ausente do registry; tools: {names}"


@pytest.mark.asyncio
async def test_clear_context_chama_context_state_clear():
    """Round-trip: call_tool('clear_context', {}) deve delegar a context_state.clear()."""
    from maestra_mcp.tools import call_tool
    mock_ctx = MagicMock()
    mock_ctx.clear.return_value = {"status": "cleared", "cleared_context": "workout"}
    with patch("maestra_mcp.tools.build_deps", return_value={"context_state": mock_ctx}):
        result = await call_tool("clear_context", {})
    mock_ctx.clear.assert_called_once()
    assert result.get("status") == "cleared"
    assert result.get("cleared_context") == "workout"


@pytest.mark.asyncio
async def test_clear_context_retorna_resultado_do_handler():
    """Shape de retorno: o dict devolvido por context_state.clear() é propagado sem alteração."""
    from maestra_mcp.tools import call_tool
    mock_ctx = MagicMock()
    mock_ctx.clear.return_value = {"status": "cleared", "cleared_context": None}
    with patch("maestra_mcp.tools.build_deps", return_value={"context_state": mock_ctx}):
        result = await call_tool("clear_context", {})
    assert "status" in result
    assert result["cleared_context"] is None
