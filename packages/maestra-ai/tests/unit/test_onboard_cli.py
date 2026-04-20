"""Testes da deprecação do subcomando `maestra onboard` (v0.8 → remoção em v0.9).

Valida que `cmd_onboard` imprime o aviso de depreciação em stderr e delega
para `_run_onboard_real` sem alterar o comportamento funcional.
"""
from __future__ import annotations

import argparse


def test_onboard_imprime_deprecation_warning_stderr(capsys, monkeypatch):
    from maestra_ai.cli import onboard as onboard_cli

    # Stub: substitui o handler real para isolar o wrapper de depreciação.
    monkeypatch.setattr(onboard_cli, "_run_onboard_real", lambda args, **_: 0)

    args = argparse.Namespace(
        playlist_name="Maestra",
        playlist_id=None,
        seed_playlist=30,
        dry_run=True,
        yes=True,
        non_interactive=True,
        total_cap=5000,
        no_expand=True,
        expand_playlists=None,
        json=False,
        name=None,
    )
    rc = onboard_cli.cmd_onboard(args)
    err = capsys.readouterr().err
    # Aceita "depreciado" (PT-BR) ou "deprecated" (EN) e exige a menção
    # ao novo comando `maestra init` para guiar o usuário.
    assert "depreciado" in err.lower() or "deprecated" in err.lower()
    assert "maestra init" in err
    assert rc == 0
