"""Integration tests para maestra init (fluxo end-to-end)."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


def test_cli_init_help_nao_quebra():
    """`maestra init --help` imprime ajuda e sai com 0."""
    repo_root = Path(__file__).parents[3]
    result = subprocess.run(
        ["uv", "run", "maestra", "init", "--help"],
        capture_output=True, text=True, cwd=str(repo_root),
        timeout=60,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    out = result.stdout.lower()
    assert "init" in out
    # Help deve mencionar pelo menos uma das flags ou "wizard"/"configur"
    assert any(tok in out for tok in ["wizard", "configur", "--auto", "--json"])


@pytest.mark.integration
def test_init_auto_estado_B_produz_taste_profile(tmp_path):  # noqa: N802 — ecoa nome do state (B) para legibilidade
    """Com creds + token mockados, init --auto --json gera taste_profile.

    Skeleton — requer fixtures de rede (VCR/responses) pra simular Spotify API.
    """
    pytest.skip("Integration stub — requer fixtures VCR para Spotify API")
