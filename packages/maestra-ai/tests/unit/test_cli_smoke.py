"""Smoke tests do agregador CLI: parser aceita subcomandos conhecidos."""
from __future__ import annotations

import pytest

from maestra_ai.cli import main as cli_main


def _run(argv: list[str], monkeypatch) -> None:
    monkeypatch.setattr("sys.argv", ["maestra", *argv])
    cli_main()


def test_auth_setup_grava_config(monkeypatch, tmp_path, capsys):
    """`auth setup --client-id --client-secret --redirect-uri` grava config."""
    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
    _run(
        [
            "auth", "setup",
            "--client-id", "cid_smoke",
            "--client-secret", "sec_smoke",
            "--redirect-uri", "https://example.com/cb",
        ],
        monkeypatch,
    )
    from maestra_ai.core import storage
    cfg = storage.read_config()
    assert cfg["client_id"] == "cid_smoke"
    assert cfg["redirect_uri"] == "https://example.com/cb"


def test_auth_login_sem_config_levanta(monkeypatch, tmp_path, capsys):
    """`auth login` sem config.json → exit code 2 (MaestraError handled)."""
    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
    rc = cli_main(["auth", "login"])
    assert rc == 2


def test_onboard_parser_aceita_flags():
    """Parser de onboard aceita --playlist-name, --seed-playlist, --dry-run, --yes, --json."""
    from maestra_ai.cli import _build_parser
    args = _build_parser().parse_args(
        ["onboard", "--playlist-name", "MinhaLista", "--seed-playlist", "50",
         "--dry-run", "--yes", "--json"],
    )
    assert args.playlist_name == "MinhaLista"
    assert args.seed_playlist == 50
    assert args.dry_run is True
    assert args.yes is True
    assert args.json is True


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
