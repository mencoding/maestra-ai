"""Testes do subcomando `maestra onboard` — modo interativo + non-interactive.

v0.4.5 parte 2: CLI aceita --playlist-id para apontar playlist existente
e modo interativo (TTY) com escolha entre criar nova ou apontar.
"""
from __future__ import annotations

import argparse

import pytest

from maestra_ai.cli import onboard as cli_onboard

_ID = "ABCDEFGHIJKLMNOPQRSTUV"  # 22 chars base62


def _ns(**kwargs):
    ns = argparse.Namespace(
        human=False,
        json=False,
        playlist_name="Maestra",
        seed_playlist=0,
        dry_run=True,
        yes=True,
        non_interactive=False,
        playlist_id=None,
    )
    for k, v in kwargs.items():
        setattr(ns, k, v)
    return ns


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("MAESTRA_STATE_DIR", str(tmp_path / "state"))
    yield


class _FakeController:
    def __init__(self):
        self.sp = object()


def _fake_run_capture(captured: dict):
    def _fake(sp, taste, **kwargs):
        captured.update(kwargs)
        return {
            "status": "ok",
            "playlist_id": kwargs.get("existing_playlist_id") or "pl_new",
            "playlist_name": kwargs.get("playlist_name") or "PL",
            "top_long_count": 0, "top_medium_count": 0, "top_short_count": 0,
            "saved_tracks_fetched": 0, "recent_count": 0,
            "unique_tracks_scored": 0, "seeded": 0,
            "context_suggestions": ["a", "b", "c", "d", "e"],
        }
    return _fake


def test_onboard_cli_non_interactive_com_name(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "maestra_ai.core.onboard.run", _fake_run_capture(captured)
    )
    args = _ns(playlist_name="TesteNome", non_interactive=True, yes=True)
    rc = cli_onboard._handle(args, _FakeController(), taste=None)
    assert rc == 0
    assert captured.get("playlist_name") == "TesteNome"
    assert captured.get("existing_playlist_id") is None


def test_onboard_cli_non_interactive_com_playlist_id_normaliza(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "maestra_ai.core.onboard.run", _fake_run_capture(captured)
    )
    args = _ns(
        playlist_id=f"spotify:playlist:{_ID}",
        non_interactive=True, yes=True,
    )
    rc = cli_onboard._handle(args, _FakeController(), taste=None)
    assert rc == 0
    assert captured.get("existing_playlist_id") == _ID


def test_onboard_cli_non_interactive_sem_flags_erra(monkeypatch, capsys):
    # --non-interactive sem --name (default "Maestra" ainda existe, mas o
    # usuário precisa confirmar uma das duas flags explicitamente).
    # Regra: se non_interactive e não há --playlist-id e playlist_name é
    # o default placeholder => erra. Usamos playlist_name=None para sinalizar
    # ausência explícita.
    args = _ns(
        playlist_name=None,
        playlist_id=None,
        non_interactive=True,
        yes=True,
    )
    rc = cli_onboard._handle(args, _FakeController(), taste=None)
    assert rc != 0


def test_onboard_cli_interativo_escolha_1_cria(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "maestra_ai.core.onboard.run", _fake_run_capture(captured)
    )
    # Força TTY
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)

    inputs = iter(["1", "Nome Teste"])
    monkeypatch.setattr("builtins.input", lambda *a, **kw: next(inputs))

    args = _ns(
        playlist_name=None, playlist_id=None,
        non_interactive=False, yes=True,
    )
    rc = cli_onboard._handle(args, _FakeController(), taste=None)
    assert rc == 0
    assert captured.get("playlist_name") == "Nome Teste"
    assert captured.get("existing_playlist_id") is None


def test_onboard_cli_interativo_escolha_2_por_numero(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "maestra_ai.core.onboard.run", _fake_run_capture(captured)
    )
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)

    class _Ctrl:
        def __init__(self):
            self.sp = self
        def current_user_playlists(self, limit=20):
            return {"items": [
                {"id": "pl_a", "name": "A", "tracks": {"total": 10}},
                {"id": "pl_b", "name": "B", "tracks": {"total": 20}},
                {"id": "pl_c", "name": "C", "tracks": {"total": 30}},
            ]}

    inputs = iter(["2", "2"])
    monkeypatch.setattr("builtins.input", lambda *a, **kw: next(inputs))

    args = _ns(
        playlist_name=None, playlist_id=None,
        non_interactive=False, yes=True,
    )
    rc = cli_onboard._handle(args, _Ctrl(), taste=None)
    assert rc == 0
    assert captured.get("existing_playlist_id") == "pl_b"


def test_onboard_cli_interativo_escolha_2_paste_url(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "maestra_ai.core.onboard.run", _fake_run_capture(captured)
    )
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)

    class _Ctrl:
        def __init__(self):
            self.sp = self
        def current_user_playlists(self, limit=20):
            return {"items": [
                {"id": "pl_a", "name": "A", "tracks": {"total": 10}},
            ]}

    url = f"https://open.spotify.com/playlist/{_ID}?si=xyz"
    inputs = iter(["2", url])
    monkeypatch.setattr("builtins.input", lambda *a, **kw: next(inputs))

    args = _ns(
        playlist_name=None, playlist_id=None,
        non_interactive=False, yes=True,
    )
    rc = cli_onboard._handle(args, _Ctrl(), taste=None)
    assert rc == 0
    assert captured.get("existing_playlist_id") == _ID


def test_onboard_cli_interativo_input_invalido_3x_aborta(monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)

    class _Ctrl:
        def __init__(self):
            self.sp = self
        def current_user_playlists(self, limit=20):
            return {"items": [
                {"id": "pl_a", "name": "A", "tracks": {"total": 10}},
            ]}

    # "2" para apontar, depois 3 inputs inválidos
    inputs = iter(["2", "xxx", "yyy", "zzz"])
    monkeypatch.setattr("builtins.input", lambda *a, **kw: next(inputs))

    args = _ns(
        playlist_name=None, playlist_id=None,
        non_interactive=False, yes=True,
    )
    rc = cli_onboard._handle(args, _Ctrl(), taste=None)
    assert rc != 0
