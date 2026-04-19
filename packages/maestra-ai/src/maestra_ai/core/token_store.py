"""Backends pluggable para persistência do refresh_token Spotify.

Keyring é preferencial (Secret Service/DBus em Linux, macOS Keychain,
Windows Credential Manager). File é fallback com chmod 600 em
`config_dir()/token.json`, usando `atomic_write_json` (v0.2.5) para
evitar corrupção concorrente.

Interface via Protocol permite futuros backends (MCP server em Fase 4+
pode precisar de stores em containers sem DBus, ou em cofre externo).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

try:
    import keyring  # type: ignore[import-untyped]
except ImportError:
    keyring = None  # type: ignore[assignment]

from maestra_ai.core.storage import atomic_write_json, config_dir

_SERVICE = "maestra-ai"
_USER = "spotify-refresh-token"


class TokenStore(Protocol):
    """Contrato mínimo para backends de refresh_token."""

    def save(self, refresh_token: str) -> None: ...
    def load(self) -> str | None: ...
    def delete(self) -> None: ...


def _keyring_backend_ok() -> bool:
    """True se keyring tem backend real (não null, não fail).

    `fail.Keyring` e `null.Keyring` vivem em módulos com "fail"/"null" no
    path — checamos `__module__` em vez de `__name__` porque a classe
    sempre se chama "Keyring".
    """
    if keyring is None:
        return False
    try:
        backend = keyring.get_keyring()
        if backend is None:
            return False
        module = type(backend).__module__.lower()
        return "fail" not in module and "null" not in module
    except Exception:
        return False


class KeyringTokenStore:
    """Backend via python-keyring (Secret Service em Linux).

    Todos os métodos são defensivos contra `NoKeyringError` e similares:
    se o backend explodir em runtime (mudança de ambiente, keyring
    corrompido), load/delete retornam silenciosamente. save re-levanta
    pois falha real não pode ser ignorada.
    """

    def save(self, refresh_token: str) -> None:
        keyring.set_password(_SERVICE, _USER, refresh_token)

    def load(self) -> str | None:
        try:
            return keyring.get_password(_SERVICE, _USER)
        except Exception:
            return None

    def delete(self) -> None:
        try:
            keyring.delete_password(_SERVICE, _USER)
        except Exception:
            # PasswordDeleteError se entrada inexistente, ou
            # NoKeyringError se backend sumiu — idempotente.
            pass


class FileTokenStore:
    """Fallback em `config_dir()/token.json` com chmod 600.

    Usa `atomic_write_json` (v0.2.5) para fechar janela de corrupção
    concorrente. Leitura tolera JSON malformado e retorna None (reuso
    do fix P0-N1 em v0.2.4).
    """

    def _path(self) -> Path:
        return config_dir() / "token.json"

    def save(self, refresh_token: str) -> None:
        path = self._path()
        # v0.4.4 CRITICAL-3: chmod acontece no .tmp antes do rename (sem
        # janela world-readable). mode=0o600 = S_IRUSR | S_IWUSR.
        atomic_write_json(path, {"refresh_token": refresh_token}, mode=0o600)

    def load(self) -> str | None:
        path = self._path()
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        if not isinstance(data, dict):
            return None
        return data.get("refresh_token")

    def delete(self) -> None:
        path = self._path()
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def default_token_store() -> TokenStore:
    """KeyringTokenStore se o backend estiver ok; senão FileTokenStore."""
    if _keyring_backend_ok():
        return KeyringTokenStore()
    return FileTokenStore()
