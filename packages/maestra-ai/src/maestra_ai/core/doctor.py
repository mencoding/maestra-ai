"""Diagnóstico self-service: cada check retorna {name, status, message, details}."""
from __future__ import annotations

import shutil
import sys

from maestra_ai.core import storage


def check_python() -> dict:
    v = sys.version_info
    ok = v >= (3, 11)
    return {
        "name": "Python version",
        "status": "ok" if ok else "error",
        "message": f"{v.major}.{v.minor}.{v.micro}",
        "details": {"required": ">=3.11"},
    }


def check_config() -> dict:
    cfg = storage.read_config()
    if not cfg:
        return {
            "name": "Config",
            "status": "warning",
            "message": "config.json ausente. Rode `maestra auth setup`.",
            "details": {"path": str(storage.config_dir() / "config.json")},
        }
    has_client = bool(cfg.get("client_id"))
    return {
        "name": "Config",
        "status": "ok" if has_client else "warning",
        "message": "OK" if has_client else "client_id não configurado",
        "details": {"keys": list(cfg.keys())},
    }


def check_keyring() -> dict:
    ok = storage._keyring_backend_ok()
    return {
        "name": "Keyring",
        "status": "ok" if ok else "warning",
        "message": "Disponível" if ok else "Indisponível; fallback para arquivo chmod 600",
        "details": {},
    }


def check_token() -> dict:
    token = storage.load_refresh_token()
    return {
        "name": "Spotify token",
        "status": "ok" if token else "warning",
        "message": "Presente" if token else "Ausente; rode `maestra auth login`",
        "details": {"length": len(token) if token else 0},
    }


def check_disk() -> dict:
    storage.ensure_dirs()
    stat = shutil.disk_usage(str(storage.data_dir()))
    gb_free = stat.free / (1024**3)
    status = "ok" if gb_free > 1 else ("warning" if gb_free > 0.1 else "error")
    return {
        "name": "Disk space",
        "status": status,
        "message": f"{gb_free:.2f} GB livre em {storage.data_dir()}",
        "details": {"available": stat.free, "total": stat.total},
    }


def check_director() -> dict:
    # v0.4.4 CRITICAL-1: usa o mesmo path autoritativo do director daemon
    # (core.director._pid_file = data_dir()/director.pid). Antes usávamos
    # state_dir() e reportávamos "parado" para daemons vivos.
    from maestra_ai.core.director import _pid_file as _director_pid_file
    pidfile = _director_pid_file()
    if not pidfile.exists():
        return {
            "name": "Director",
            "status": "ok",
            "message": "Parado (normal se você não iniciou).",
            "details": {},
        }
    pid = pidfile.read_text().strip()
    return {
        "name": "Director",
        "status": "ok",
        "message": f"Rodando (PID {pid})",
        "details": {"pid": pid},
    }


def run_all() -> list[dict]:
    return [
        check_python(),
        check_config(),
        check_keyring(),
        check_token(),
        check_disk(),
        check_director(),
    ]
