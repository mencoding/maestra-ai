"""Testes do server MCP — create_server + disabled_tools."""
from __future__ import annotations

import json
import os
import subprocess
import sys

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


def test_disabled_tools_cacheia_por_mtime(monkeypatch, tmp_path):
    """Fix M3: _disabled_tools deve cachear o resultado e só reler
    config.json quando mtime mudar. Reduz I/O por chamada MCP."""
    import os
    import time
    from unittest.mock import patch as _patch

    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
    from maestra_ai.core import storage
    storage.write_config({
        "client_id": "c", "client_secret": "s",
        "redirect_uri": "https://x/cb",
        "mcp": {"disabled_tools": ["now"]},
    })

    from maestra_mcp import server as server_mod
    # Limpa cache entre testes
    server_mod._DISABLED_CACHE["mtime"] = None
    server_mod._DISABLED_CACHE["value"] = set()

    with _patch("maestra_ai.core.storage.read_config",
                wraps=storage.read_config) as m:
        # 3 chamadas seguidas sem mudar o arquivo — só 1 read_config
        a = server_mod._disabled_tools()
        b = server_mod._disabled_tools()
        c = server_mod._disabled_tools()
        assert a == b == c == {"now"}
        assert m.call_count == 1, \
            f"read_config deveria ter sido chamado 1x, veio {m.call_count}"

        # Altera mtime — cache deve invalidar e reler
        path = storage.config_dir() / "config.json"
        future = time.time() + 10
        os.utime(path, (future, future))
        d = server_mod._disabled_tools()
        assert d == {"now"}
        assert m.call_count == 2, \
            f"após mudar mtime, read_config deveria rodar de novo (veio {m.call_count})"


@pytest.mark.asyncio
async def test_server_audita_excecao_nao_tratada(monkeypatch, tmp_path):
    """Fix H4: se tools.call_tool levanta exceção não-tratada, o server
    deve ainda assim registrar audit.log com o erro resumido no
    result_summary, em vez de pular a trilha."""
    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("MAESTRA_STATE_DIR", str(tmp_path / "state"))
    from maestra_ai.core import storage
    storage.write_config({
        "client_id": "c", "client_secret": "s",
        "redirect_uri": "https://x/cb",
    })

    from unittest.mock import patch

    from maestra_mcp.server import _build_call_tool_handler

    calls = []

    def fake_log(tool, args, result):
        calls.append({"tool": tool, "args": args, "result": result})

    async def exploding_call_tool(name, args):
        raise RuntimeError("kaboom")

    handler = _build_call_tool_handler()
    with patch("maestra_mcp.server.call_tool", side_effect=exploding_call_tool), \
         patch("maestra_ai.core.audit.log", side_effect=fake_log):
        out = await handler("now", {"x": 1})

    # Resposta TextContent com error dict serializado
    assert len(out) == 1
    payload = json.loads(out[0].text)
    assert "error" in payload
    assert payload["error"]["code"] == "InternalError"
    assert "kaboom" in payload["error"]["what_happened"]

    # Auditoria registrou o evento com erro no result_summary
    assert len(calls) == 1, "audit.log deveria ter sido chamado mesmo com exceção"
    assert calls[0]["tool"] == "now"
    # result passa pelo summarizer, mas a chave 'error' deve estar presente
    assert "error" in calls[0]["result"]


def test_server_subprocess_responde_initialize_e_list_tools(tmp_path, monkeypatch):
    """Integration: inicia maestra-mcp como subprocess e fala JSON-RPC stdio."""
    env = os.environ.copy()
    env["MAESTRA_CONFIG_DIR"] = str(tmp_path / "config")
    env["MAESTRA_DATA_DIR"] = str(tmp_path / "data")
    env["MAESTRA_STATE_DIR"] = str(tmp_path / "state")
    env["PYTHON_KEYRING_BACKEND"] = "keyring.backends.fail.Keyring"

    # Config mínimo para build_deps não falhar
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "config.json").write_text(
        json.dumps({
            "client_id": "cid", "client_secret": "sec",
            "redirect_uri": "https://x/cb",
        }),
        encoding="utf-8",
    )

    proc = subprocess.Popen(
        [sys.executable, "-m", "maestra_mcp.server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        text=True,
    )
    try:
        # Initialize
        init = {
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0.0"},
            },
        }
        proc.stdin.write(json.dumps(init) + "\n")
        proc.stdin.flush()
        line = proc.stdout.readline()
        resp = json.loads(line)
        assert resp.get("id") == 1
        assert "result" in resp
        assert "serverInfo" in resp["result"]
        assert resp["result"]["serverInfo"]["name"] == "maestra"

        # initialized notification
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        proc.stdin.flush()

        # tools/list
        list_req = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
        proc.stdin.write(json.dumps(list_req) + "\n")
        proc.stdin.flush()
        line = proc.stdout.readline()
        resp = json.loads(line)
        tools = resp.get("result", {}).get("tools", [])
        names = {t["name"] for t in tools}
        assert "now" in names
        assert "doctor" in names
        assert len(names) == 23
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
