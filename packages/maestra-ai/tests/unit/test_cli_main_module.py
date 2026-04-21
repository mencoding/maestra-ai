"""Regressão: garante que `python -m maestra_ai.cli` é invocável.

O director (`core/director.py`) spawna `python -m maestra_ai.cli director run`
como subprocess. Sem __main__.py no pacote cli/, o subprocess morre com
"No module named maestra_ai.cli.__main__" e o daemon falha silenciosamente.

Issue #6.
"""
from __future__ import annotations

import subprocess
import sys


def test_cli_pode_ser_invocado_como_modulo():
    """`python -m maestra_ai.cli --help` deve retornar exit 0 e banner de ajuda."""
    result = subprocess.run(
        [sys.executable, "-m", "maestra_ai.cli", "--help"],
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 0, (
        f"python -m maestra_ai.cli --help falhou (exit {result.returncode}): "
        f"stderr={result.stderr.decode(errors='replace')!r}"
    )
    assert b"usage:" in result.stdout.lower() or b"maestra" in result.stdout.lower(), (
        f"stdout não contém banner de ajuda: {result.stdout[:200]!r}"
    )


def test_cli_modulo_propaga_exit_code_de_subcomando_invalido():
    """Subcomando inexistente deve retornar exit != 0, comprovando que main() é chamado."""
    result = subprocess.run(
        [sys.executable, "-m", "maestra_ai.cli", "--subcomando-que-nao-existe"],
        capture_output=True,
        timeout=10,
    )
    assert result.returncode != 0, (
        "argparse deveria rejeitar flag desconhecida com exit != 0"
    )
