"""Sonda de processo portável — MEDIUM-2.

Checa se o aplicativo Spotify está rodando. Retorna:
- True: processo encontrado
- False: processo não encontrado (ferramenta disponível e retornou vazio)
- None: não foi possível determinar (ferramenta ausente no sistema)

Caller decide como tratar None (tipicamente: prosseguir sem pré-check
e deixar a API do Spotify retornar o erro).
"""
from __future__ import annotations

import shutil
import subprocess


def is_spotify_running() -> bool | None:
    # Unix-like: pgrep
    pgrep = shutil.which("pgrep")
    if pgrep:
        try:
            result = subprocess.run(
                [pgrep, "-x", "spotify"],
                capture_output=True, timeout=2,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, OSError):
            return None

    # Windows: tasklist
    tasklist = shutil.which("tasklist")
    if tasklist:
        try:
            result = subprocess.run(
                [tasklist, "/FI", "IMAGENAME eq Spotify.exe", "/FO", "CSV", "/NH"],
                capture_output=True, timeout=2,
            )
            if result.returncode != 0:
                return None
            # tasklist retorna "INFO: No tasks..." no stdout se vazio
            out = result.stdout.decode("utf-8", errors="replace").strip()
            return bool(out) and "No tasks" not in out and "Spotify.exe" in out
        except (subprocess.TimeoutExpired, OSError):
            return None

    return None
