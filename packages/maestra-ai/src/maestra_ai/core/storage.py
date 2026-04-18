"""Armazenamento local com XDG + env overrides + keyring (fallback chmod 600)."""
from __future__ import annotations

import fcntl
import json
import os
import stat
from pathlib import Path
from typing import Any

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


def update_json_under_lock(
    path: str | os.PathLike,
    mutator,
    *,
    default: Any = None,
    indent: int = 2,
) -> Any:
    """Read-modify-write atômico sob lock exclusivo.

    Adquire `fcntl.LOCK_EX`, relê o arquivo (ou usa `default` se não existir
    ou estiver corrompido), aplica `mutator(data)` → novo dict, escreve em
    tmp e faz `os.replace`. Elimina janela de lost-update entre processos
    concorrentes (daemon + CLI manual).

    Retorna o valor escrito (útil para o caller inspecionar o resultado
    do merge sem reler o arquivo).
    """
    path = os.fspath(path)
    parent = os.path.dirname(path) or "."
    os.makedirs(parent, exist_ok=True)
    if default is None:
        default = {}
    lock_path = f"{path}.lock"
    tmp_path = f"{path}.tmp"
    with open(lock_path, "w", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    current = json.load(f)
            except (json.JSONDecodeError, OSError):
                current = default
        else:
            current = default
        updated = mutator(current)
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(updated, f, indent=indent, ensure_ascii=False)
        os.replace(tmp_path, path)
    return updated


def atomic_write_json(path: str | os.PathLike, data: Any, *, indent: int = 2) -> None:
    """Escreve `data` como JSON em `path` com lock exclusivo + rename atômico.

    Fecha P0-5: serializa writes concorrentes entre daemon (director run) e
    CLI manual. Usa `fcntl.LOCK_EX` em `<path>.lock` durante toda a operação,
    escreve em `<path>.tmp` e faz `os.replace` (POSIX atomic rename). Leitores
    concorrentes sempre veem o conteúdo antigo ou o novo — nunca um parcial.
    """
    path = os.fspath(path)
    parent = os.path.dirname(path) or "."
    os.makedirs(parent, exist_ok=True)
    lock_path = f"{path}.lock"
    tmp_path = f"{path}.tmp"
    with open(lock_path, "w", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent, ensure_ascii=False)
        os.replace(tmp_path, path)


def read_config() -> dict:
    p = config_dir() / "config.json"
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        from maestra_ai.core.errors import ConfigError
        raise ConfigError(
            "config.json malformado ou inacessível.",
            where={"path": str(p)},
        ) from e
    if not isinstance(data, dict):
        from maestra_ai.core.errors import ConfigError
        raise ConfigError(
            "config.json não é um objeto JSON.",
            where={"path": str(p), "got_type": type(data).__name__},
        )
    return data


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
    """Shim: delega para default_token_store().save().

    Mantido por retrocompat. Nova code path usa token_store direto.
    """
    ensure_dirs()
    from maestra_ai.core.token_store import default_token_store
    default_token_store().save(token)


def load_refresh_token() -> str | None:
    """Shim: delega para default_token_store().load()."""
    from maestra_ai.core.token_store import default_token_store
    return default_token_store().load()


def _flag_keyring_used(used: bool) -> None:
    flag = config_dir() / "token.keyring.flag"
    if used:
        flag.touch()
    elif flag.exists():
        flag.unlink()


def _flag_keyring_used_get() -> bool:
    return (config_dir() / "token.keyring.flag").exists()
