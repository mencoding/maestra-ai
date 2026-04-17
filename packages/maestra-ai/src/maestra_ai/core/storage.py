"""Armazenamento local com XDG + env overrides + keyring (fallback chmod 600)."""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path

try:
    import keyring  # type: ignore[import-untyped]
except ImportError:
    keyring = None  # type: ignore[assignment]


_SERVICE = "maestra-ai"
_USER = "spotify-refresh-token"


def _env_or(env_key: str, xdg_key: str, xdg_default: str, suffix: str = "maestra") -> Path:
    """Resolve diretório por prioridade: env var > XDG > default."""
    override = os.environ.get(env_key)
    if override:
        return Path(override)
    xdg = os.environ.get(xdg_key)
    if xdg:
        return Path(xdg) / suffix
    return Path(os.path.expanduser(xdg_default)) / suffix


def config_dir() -> Path:
    return _env_or("MAESTRA_CONFIG_DIR", "XDG_CONFIG_HOME", "~/.config")


def data_dir() -> Path:
    return _env_or("MAESTRA_DATA_DIR", "XDG_DATA_HOME", "~/.local/share")


def state_dir() -> Path:
    return _env_or("MAESTRA_STATE_DIR", "XDG_STATE_HOME", "~/.local/state")


def snapshots_dir() -> Path:
    return data_dir() / "snapshots"


def ensure_dirs() -> None:
    for d in (config_dir(), data_dir(), state_dir(), snapshots_dir()):
        d.mkdir(parents=True, exist_ok=True)


def read_config() -> dict:
    p = config_dir() / "config.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def write_config(data: dict) -> None:
    ensure_dirs()
    p = config_dir() / "config.json"
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _keyring_backend_ok() -> bool:
    if keyring is None:
        return False
    try:
        backend = keyring.get_keyring()
        return backend is not None and "fail" not in type(backend).__name__.lower()
    except Exception:
        return False


def save_refresh_token(token: str) -> None:
    ensure_dirs()
    if _keyring_backend_ok():
        keyring.set_password(_SERVICE, _USER, token)
        _flag_keyring_used(True)
    else:
        _flag_keyring_used(False)
        path = config_dir() / "token.json"
        path.write_text(json.dumps({"refresh_token": token}), encoding="utf-8")
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 600


def load_refresh_token() -> str | None:
    if _keyring_backend_ok() and _flag_keyring_used_get():
        try:
            return keyring.get_password(_SERVICE, _USER)
        except Exception:
            pass
    path = config_dir() / "token.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("refresh_token")


def _flag_keyring_used(used: bool) -> None:
    flag = config_dir() / "token.keyring.flag"
    if used:
        flag.touch()
    elif flag.exists():
        flag.unlink()


def _flag_keyring_used_get() -> bool:
    return (config_dir() / "token.keyring.flag").exists()
