"""Wizard unificado `maestra init`.

Detecta estado (A/A2/B/C), apresenta menu contextual, executa o fluxo
escolhido. Delega I/O externo para `core.auth` e `core.onboard`.
"""
from __future__ import annotations

import json

from maestra_ai.core import storage
from maestra_ai.core.init_types import InitState


def _has_token() -> bool:
    """True se há refresh_token persistido (keyring ou fallback)."""
    from maestra_ai.core.token_store import default_token_store
    try:
        tok = default_token_store().load()
        return bool(tok)
    except Exception:
        return False


def _has_config() -> bool:
    """True se config.json tem client_id e client_secret não-vazios."""
    path = storage.config_dir() / "config.json"
    if not path.exists():
        return False
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(cfg.get("client_id")) and bool(cfg.get("client_secret"))


def _has_taste() -> bool:
    """True se taste_profile tem global_signal não-vazio."""
    path = storage.data_dir() / "taste_profile.json"
    if not path.exists():
        return False
    try:
        profile = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(profile.get("global_signal"))


def detect_state() -> InitState:
    """Retorna o estado atual do setup da Maestra.

    Estados inconsistentes (taste sem token, token sem config) voltam pra A
    — o chamador pode consultar o helper privado pra avisar o usuário.
    """
    has_config = _has_config()
    has_token = _has_token()
    has_taste = _has_taste()

    if has_config and has_token and has_taste:
        return "C"
    if has_config and has_token:
        return "B"
    if has_config and not has_token:
        return "A2"
    # Combinações inconsistentes caem em A
    return "A"
