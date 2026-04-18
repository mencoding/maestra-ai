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
