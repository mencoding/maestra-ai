"""Testes de deps.build_deps — instancia cores uma vez por processo."""
from __future__ import annotations

from unittest.mock import patch


def test_build_deps_retorna_dict_com_chaves_esperadas(monkeypatch, tmp_path):
    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
    from maestra_ai.core import storage
    storage.write_config({
        "client_id": "cid", "client_secret": "sec",
        "redirect_uri": "https://example.com/cb",
    })

    from maestra_mcp.deps import build_deps, _reset
    _reset()  # limpa cache entre testes

    with patch("maestra_ai.core.client.spotipy.Spotify"):
        deps = build_deps()

    assert "controller" in deps
    assert "taste" in deps
    assert "context_state" in deps
    assert "curator" in deps
    assert "history_analyzer" in deps
    assert "flow_analyzer" in deps


def test_build_deps_cacheia_entre_chamadas(monkeypatch, tmp_path):
    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
    from maestra_ai.core import storage
    storage.write_config({
        "client_id": "c", "client_secret": "s",
        "redirect_uri": "https://example.com/cb",
    })

    from maestra_mcp.deps import build_deps, _reset
    _reset()
    with patch("maestra_ai.core.client.spotipy.Spotify"):
        a = build_deps()
        b = build_deps()
    assert a is b
