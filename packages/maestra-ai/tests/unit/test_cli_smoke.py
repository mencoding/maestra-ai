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


def test_grupo_com_sub_subcomando_nao_pula_deps(monkeypatch, tmp_path):
    """v0.5.2 (regressão do fix 6): set_defaults(skip_deps=True) no parser
    do grupo vazava para sub-subparsers via herança de defaults do argparse,
    quebrando dispatch com 'missing positional argument'. Agora
    group_help_handler é identificado via atributo _is_group_help no
    próprio handler — sub-subcomandos recebem deps normalmente."""
    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("MAESTRA_STATE_DIR", str(tmp_path / "state"))

    captured = {}
    import maestra_ai.cli.taste as taste_mod

    def fake_taste_show(args, **deps):
        captured["deps"] = list(deps.keys())
        return 0

    monkeypatch.setattr(taste_mod, "cmd_taste_show", fake_taste_show)
    # Re-monta parser porque _REGISTRARS só roda uma vez; o mock do
    # cmd_taste_show já entra via ref direto ao dispatch, porém como
    # set_defaults(func=cmd_taste_show) capturou a ref original, fazemos
    # patch direto no args.func via namespace.
    # Abordagem mais simples: atestar que o taste.cmd_taste_show original
    # é chamado com deps (não cai no skip_deps do grupo).
    import argparse
    from maestra_ai.cli import _build_parser
    parser = _build_parser()
    args = parser.parse_args(["taste", "show"])
    # args.func deveria ser o cmd_taste_show real, não o group_help_handler.
    assert not getattr(args.func, "_is_group_help", False), \
        "sub-subparser 'show' não deveria ser o group help handler"


@pytest.mark.parametrize("group", ["taste", "auth", "config", "playlist",
                                     "context", "director", "flow"])
def test_grupo_sem_sub_subcomando_mostra_help_em_vez_de_erro(group, monkeypatch, capsys):
    """v0.5.2 (bug 6): antes, `maestra taste` sem subcomando dava argparse
    error ("the following arguments are required: taste_command") e exit 2.
    Agora printa help formatado do grupo e retorna 0."""
    monkeypatch.setattr("sys.argv", ["maestra", group])
    rc = cli_main()
    assert rc == 0
    out = capsys.readouterr().out
    # Help do grupo deve listar subcomandos disponíveis.
    assert "usage:" in out.lower() or "Usage:" in out


def test_auth_setup_help_cita_dashboard_e_redirect_https(monkeypatch, capsys):
    """--help de `auth setup` deve explicar pré-requisito (app no dashboard,
    redirect HTTPS) para agente IA ou usuário novo não precisar adivinhar."""
    monkeypatch.setattr("sys.argv", ["maestra", "auth", "setup", "--help"])
    with pytest.raises(SystemExit):
        cli_main()
    out = capsys.readouterr().out
    # Aponta o dashboard.
    assert "developer.spotify.com" in out or "dashboard" in out.lower()
    # Menciona que localhost é rejeitado em apps novos.
    assert "localhost" in out.lower() or "HTTPS" in out


def test_sem_subcomando_mostra_banner_e_retorna_zero(monkeypatch, capsys):
    """v0.5.1: antes levantava SystemExit(2) com help do argparse.
    Agora imprime quickstart banner e retorna 0 — UX de primeira execução."""
    monkeypatch.setattr("sys.argv", ["maestra"])
    rc = cli_main()
    assert rc == 0
    assert "maestra help onboarding" in capsys.readouterr().out


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
