"""MEDIUM-2: is_spotify_running portável (pgrep Linux/mac, tasklist Windows, fallback)."""
from __future__ import annotations

from unittest.mock import patch


def test_is_spotify_running_pgrep_encontra():
    """Em sistemas com pgrep e processo rodando, retorna True."""
    import subprocess

    from maestra_ai.core import process

    fake = subprocess.CompletedProcess(args=[], returncode=0, stdout=b"1234\n")
    with patch("maestra_ai.core.process.shutil.which", return_value="/usr/bin/pgrep"):
        with patch("maestra_ai.core.process.subprocess.run", return_value=fake):
            assert process.is_spotify_running() is True


def test_is_spotify_running_pgrep_nao_encontra():
    import subprocess

    from maestra_ai.core import process

    fake = subprocess.CompletedProcess(args=[], returncode=1, stdout=b"")
    with patch("maestra_ai.core.process.shutil.which", return_value="/usr/bin/pgrep"):
        with patch("maestra_ai.core.process.subprocess.run", return_value=fake):
            assert process.is_spotify_running() is False


def test_is_spotify_running_sem_pgrep_nem_tasklist_retorna_none():
    """Sem ferramentas disponíveis: retorna None (desconhecido, não False)."""
    from maestra_ai.core import process

    with patch("maestra_ai.core.process.shutil.which", return_value=None):
        assert process.is_spotify_running() is None


def test_is_spotify_running_tasklist_windows():
    import subprocess

    from maestra_ai.core import process

    def which_side(cmd):
        return r"C:\Windows\System32\tasklist.exe" if cmd == "tasklist" else None

    fake = subprocess.CompletedProcess(
        args=[], returncode=0,
        stdout=b'"Spotify.exe","1234","Console","1","100,000 K"\r\n',
    )
    with patch("maestra_ai.core.process.shutil.which", side_effect=which_side):
        with patch("maestra_ai.core.process.subprocess.run", return_value=fake):
            assert process.is_spotify_running() is True
