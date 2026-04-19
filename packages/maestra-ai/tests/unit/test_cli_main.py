"""Testes do dispatch principal do CLI — saida JSON e tratamento de erros."""
from __future__ import annotations

import json

from maestra_ai.cli import main


class TestQuickstartBanner:
    """Rodar `maestra` sem subcomando → banner de quickstart + exit 0.

    Antes, argparse levantava 'required' e imprimia help completo de
    28 subcomandos, deixando usuário novo perdido."""

    def test_sem_args_imprime_banner_e_retorna_zero(self, capsys, monkeypatch, tmp_path):
        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path / "cfg"))
        monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
        monkeypatch.setenv("MAESTRA_STATE_DIR", str(tmp_path / "state"))

        rc = main([])

        assert rc == 0
        out = capsys.readouterr().out
        # Banner deve apontar caminhos concretos — não dump de 28 subcomandos.
        assert "maestra help onboarding" in out
        assert "maestra doctor" in out

    def test_sem_args_banner_nao_eh_argparse_help(self, capsys, monkeypatch, tmp_path):
        """Argparse help tem 'Positional Arguments' ou 'usage:'; banner não."""
        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path / "cfg"))
        monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
        monkeypatch.setenv("MAESTRA_STATE_DIR", str(tmp_path / "state"))

        main([])
        out = capsys.readouterr().out
        # Precisa ser compacto, não o wall-of-text do argparse help.
        assert len(out) < 2000


def test_json_error_redacts_secrets_in_where(monkeypatch, capsys, tmp_path):
    """P0-2: secrets em MaestraError.where nao devem vazar via --json."""
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("MAESTRA_STATE_DIR", str(tmp_path / "state"))

    from maestra_ai.core.errors import AuthError

    secret_value = "super_secret_token_12345"

    def fake_build_deps(args):
        raise AuthError(
            "Falha na autenticacao",
            where={"client_secret": secret_value, "endpoint": "/api/token"},
        )

    import maestra_ai.cli as cli_mod
    monkeypatch.setattr(cli_mod, "_build_deps", fake_build_deps)

    result = main(["--json", "status"])
    assert result == 2

    captured = capsys.readouterr()
    assert secret_value not in captured.out
    assert "REDACTED" in captured.out

    parsed = json.loads(captured.out)
    assert parsed["error"]["where"]["client_secret"] == "REDACTED"
    assert parsed["error"]["where"]["endpoint"] == "/api/token"
