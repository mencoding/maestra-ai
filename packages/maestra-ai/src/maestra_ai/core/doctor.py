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


# Valores óbvios de placeholder que o usuário pode ter copiado direto
# do --help ou de algum exemplo. "example.com/example.org" só é placeholder
# quando aparece no redirect_uri — no client_id/secret seria bizarro e
# cairia no check de comprimento mínimo de qualquer forma.
_PLACEHOLDER_TOKENS = (
    "your_client_id", "your_client_secret", "your-client-id", "your-client-secret",
    "seu_client_id", "seu_client_secret",
    "<client_id>", "<client_secret>", "<redirect_uri>",
    "xxx", "xxxx", "todo", "tbd", "changeme",
)


def _is_placeholder(value: str) -> bool:
    """True se `value` parece placeholder copiado de doc/exemplo."""
    if not value:
        return True
    v = value.strip().lower()
    return any(tok in v for tok in _PLACEHOLDER_TOKENS)


def _redirect_uri_is_placeholder(value: str) -> bool:
    """Redirect placeholder = tokens textuais óbvios ou localhost.

    example.com/example.org NÃO são tratados como placeholder: o fluxo é
    paste-back, o domínio nem precisa existir. Registrar example.com no
    dashboard é uso legítimo (e econômico). Já http://localhost é
    rejeitado pelo próprio Spotify em apps criados após 2025 — aí sim
    vale warning.
    """
    if _is_placeholder(value):
        return True
    v = value.strip().lower()
    return (
        v.startswith("http://localhost")
        or v.startswith("http://127.0.0.1")
    )


def check_config() -> dict:
    cfg = storage.read_config()
    path_hint = str(storage.config_dir() / "config.json")
    if not cfg:
        return {
            "name": "Config",
            "status": "warning",
            "message": "config.json ausente. Rode `maestra auth setup`.",
            "details": {"path": path_hint},
        }

    missing: list[str] = []
    placeholders: list[str] = []
    for field in ("client_id", "client_secret", "redirect_uri"):
        val = cfg.get(field)
        if not val:
            missing.append(field)
            continue
        if field == "redirect_uri":
            if _redirect_uri_is_placeholder(val):
                placeholders.append(field)
        elif _is_placeholder(val):
            placeholders.append(field)

    if missing:
        return {
            "name": "Config",
            "status": "warning",
            "message": f"Config incompleto — faltam: {', '.join(missing)}. "
                       f"Rode `maestra auth setup`.",
            "details": {"missing": missing, "path": path_hint},
        }
    if placeholders:
        return {
            "name": "Config",
            "status": "warning",
            "message": f"Campos com placeholder: {', '.join(placeholders)}. "
                       f"Rode `maestra auth setup` com valores reais.",
            "details": {"placeholders": placeholders, "path": path_hint},
        }
    return {
        "name": "Config",
        "status": "ok",
        "message": "OK",
        "details": {"keys": list(cfg.keys())},
    }


def check_keyring() -> dict:
    from maestra_ai.core.token_store import _keyring_backend_ok
    ok = _keyring_backend_ok()
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
