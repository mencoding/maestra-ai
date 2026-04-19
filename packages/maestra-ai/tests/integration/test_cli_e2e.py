"""Testes E2E do CLI maestra — subprocess real + filesystem isolado.

P1-7: até v0.2.4 o projeto tinha cobertura zero de E2E. Estes testes
invocam o binário instalado via `uv run maestra ...` em um tmp_path
isolado (MAESTRA_CONFIG_DIR / MAESTRA_DATA_DIR / MAESTRA_STATE_DIR)
e validam saída JSON + exit code + efeitos colaterais no filesystem.

Escopo mínimo pré-Fase 3 — só comandos que não dependem de credencial
Spotify real. Comandos que dependem (start, play, queue-add etc.)
ficam para Fase 3 com OAuth mockável.
"""
from __future__ import annotations

import json
import os
import subprocess

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    """Retorna env dict com XDG paths apontando para tmp_path."""
    env = os.environ.copy()
    env["MAESTRA_CONFIG_DIR"] = str(tmp_path / "config")
    env["MAESTRA_DATA_DIR"] = str(tmp_path / "data")
    env["MAESTRA_STATE_DIR"] = str(tmp_path / "state")
    # Desabilita keyring para rodar em CI sem DBus/secretstorage
    env["PYTHON_KEYRING_BACKEND"] = "keyring.backends.fail.Keyring"
    return env


def run_maestra(args, env, timeout=15):
    """Invoca `uv run maestra <args>` em subprocess, retorna CompletedProcess."""
    return subprocess.run(
        ["uv", "run", "maestra", *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


class TestDoctor:
    def test_doctor_roda_e_emite_tabela_humana(self, isolated_env):
        r = run_maestra(["doctor"], isolated_env)
        assert r.returncode == 0, f"stderr: {r.stderr}"
        assert "Python version" in r.stdout
        assert "Disk space" in r.stdout

    def test_doctor_avisa_config_ausente_em_ambiente_isolado(self, isolated_env):
        r = run_maestra(["doctor"], isolated_env)
        # config.json não existe em tmp isolado → doctor deve avisar
        assert r.returncode == 0
        assert "config.json" in r.stdout.lower() or "config" in r.stdout.lower()


class TestRollback:
    def test_rollback_list_sem_snapshots(self, isolated_env):
        r = run_maestra(["rollback", "--list"], isolated_env)
        assert r.returncode == 0, f"stderr: {r.stderr}"

    def test_rollback_list_json_estruturado(self, isolated_env):
        r = run_maestra(["--json", "rollback", "--list"], isolated_env)
        assert r.returncode == 0, f"stderr: {r.stderr}"
        payload = json.loads(r.stdout)
        # Lista vazia ou wrapper com snapshots
        assert isinstance(payload, (list, dict))

    def test_rollback_snapshot_id_invalido_rejeita_com_erro_humano(self, isolated_env):
        """P0-1 cobertura E2E: path traversal bloqueado."""
        r = run_maestra(
            ["--json", "rollback", "--snapshot", "../../../etc/passwd"],
            isolated_env,
        )
        assert r.returncode != 0
        combined = (r.stdout + r.stderr).lower()
        assert "inválido" in combined or "invalid" in combined or "traversal" in combined


class TestHelp:
    def test_help_onboarding_renderiza(self, isolated_env):
        r = run_maestra(["help", "onboarding"], isolated_env)
        assert r.returncode == 0, f"stderr: {r.stderr}"
        assert "Onboarding" in r.stdout

    def test_help_sem_arg_lista_topicos(self, isolated_env):
        r = run_maestra(["help"], isolated_env)
        assert r.returncode == 0
        assert "onboarding" in r.stdout


class TestAuth:
    def test_setup_com_args_grava_config(self, isolated_env, tmp_path):
        r = run_maestra(
            [
                "auth", "setup",
                "--client-id", "cid_e2e",
                "--client-secret", "sec_e2e",
                "--redirect-uri", "https://example.com/callback",
                "--json",
            ],
            isolated_env,
        )
        assert r.returncode == 0, f"stderr: {r.stderr}"
        payload = json.loads(r.stdout)
        assert payload["status"] == "ok"

        cfg_path = tmp_path / "config" / "config.json"
        assert cfg_path.exists()
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        assert cfg["client_id"] == "cid_e2e"
        assert cfg["redirect_uri"] == "https://example.com/callback"


# Nota: comandos `taste show`, `context set/show`, `status`, `play*`, `queue*`
# e `director run` não estão cobertos por E2E em v0.2.5 porque forçam
# _build_deps() → SpotifyController() → OAuth real. Fase 3 vai introduzir
# mock injetável e esses testes virão junto. Ver P1-4 (DI já pronto no
# constructor) + dívida arquitetural em cli/__init__.py::main
# (skip_deps só existe para rollback e auth hoje).


class TestQuickstart:
    """v0.5.6 #26: quickstart banner e grupos sem sub-subcomando."""

    def test_maestra_sem_args_mostra_quickstart(self, isolated_env):
        r = run_maestra([], isolated_env)
        assert r.returncode == 0
        # O banner quickstart cita comandos-chave de bootstrap.
        assert "onboarding" in r.stdout or "onboard" in r.stdout
        assert "doctor" in r.stdout

    def test_grupo_taste_sem_sub_mostra_help(self, isolated_env):
        """v0.5.2 + fix regressão v0.5.3.1: grupo sem sub-subcomando
        imprime help e retorna 0, não 2."""
        r = run_maestra(["taste"], isolated_env)
        assert r.returncode == 0
        assert "show" in r.stdout or "review" in r.stdout


class TestConfig:
    """v0.5.6 #26: fluxo config list redactando secrets."""

    def test_config_list_redacta_client_secret(self, isolated_env, tmp_path):
        # Grava credenciais primeiro via auth setup.
        run_maestra(
            [
                "auth", "setup",
                "--client-id", "cid_cfg_e2e",
                "--client-secret", "SUPER_SECRETO_XYZ",
                "--redirect-uri", "https://example.com/cb",
                "--json",
            ],
            isolated_env,
        )
        r = run_maestra(["config", "list"], isolated_env)
        assert r.returncode == 0, f"stderr: {r.stderr}"
        assert "SUPER_SECRETO_XYZ" not in r.stdout
        # client_id pode aparecer em clear (não é secret).
        assert "cid_cfg_e2e" in r.stdout


class TestHelpTopics:
    """v0.5.6 #26: help topics internos (onboarding, mcp) são acessíveis."""

    def test_help_onboarding_cita_pre_requisitos(self, isolated_env):
        r = run_maestra(["help", "onboarding"], isolated_env)
        assert r.returncode == 0
        assert "dashboard" in r.stdout.lower()
        assert "paste" in r.stdout.lower() or "redirect" in r.stdout.lower()

    def test_help_sem_topico_lista_disponiveis(self, isolated_env):
        r = run_maestra(["help"], isolated_env)
        assert r.returncode == 0
        assert "onboarding" in r.stdout
