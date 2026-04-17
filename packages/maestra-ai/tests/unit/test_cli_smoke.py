"""Smoke tests do agregador CLI: parser aceita subcomandos conhecidos."""
from __future__ import annotations

import pytest

from maestra_ai.cli import main as cli_main


def _run(argv: list[str], monkeypatch) -> None:
    monkeypatch.setattr("sys.argv", ["maestra", *argv])
    cli_main()


def test_auth_setup_stub(monkeypatch, capsys):
    _run(["auth", "setup"], monkeypatch)
    out = capsys.readouterr().out
    assert "stub" in out and "Plano 3" in out


def test_auth_login_stub(monkeypatch, capsys):
    _run(["auth", "login"], monkeypatch)
    out = capsys.readouterr().out
    assert "stub" in out


def test_onboard_stub(monkeypatch, capsys):
    _run(["onboard"], monkeypatch)
    out = capsys.readouterr().out
    assert "stub" in out


def test_help_sem_subcomando_falha(monkeypatch):
    monkeypatch.setattr("sys.argv", ["maestra"])
    with pytest.raises(SystemExit):
        cli_main()


@pytest.mark.parametrize("sub", [
    "status", "start", "now", "devices", "play", "pause", "next",
    "search", "queue", "queue-add", "queue-context", "play-context",
    "playlist", "taste", "context", "playback", "feedback", "flow",
    "history", "curate", "director", "auth", "onboard",
])
def test_subcomando_aparece_no_help(sub, monkeypatch, capsys):
    """Cada subcomando deve estar no --help raiz."""
    monkeypatch.setattr("sys.argv", ["maestra", "--help"])
    with pytest.raises(SystemExit):
        cli_main()
    out = capsys.readouterr().out
    assert sub in out, f"{sub} não está no help raiz"
