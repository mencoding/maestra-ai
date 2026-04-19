"""Testes de helpers em cli/_common.py — resolve_playlist_id (Fix BLOCKER-1)."""
from __future__ import annotations

import pytest

from maestra_ai.cli._common import resolve_playlist_id
from maestra_ai.core import storage
from maestra_ai.core.errors import ConfigError


def test_resolve_playlist_id_levanta_config_error_sem_config(monkeypatch, tmp_path):
    """Sem playlist_id no config, deve levantar ConfigError com mensagem útil."""
    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
    # Config vazio
    storage.write_config({})
    with pytest.raises(ConfigError) as exc_info:
        resolve_playlist_id()
    assert "playlist_id" in str(exc_info.value).lower()


def test_resolve_playlist_id_retorna_valor_do_config(monkeypatch, tmp_path):
    """Com playlist_id no config, retorna o valor armazenado."""
    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
    storage.write_config({"playlist_id": "pl_test_123"})
    assert resolve_playlist_id() == "pl_test_123"
