"""Testes do TokenStore — backend pluggable para refresh_token Spotify.

Task 1 da v0.3.0. Substitui as chamadas diretas a keyring em
storage.save/load_refresh_token por Protocol abstrato com
KeyringTokenStore (preferencial) e FileTokenStore (fallback).
"""
from __future__ import annotations

import json
import stat
from unittest.mock import MagicMock, patch

import pytest

from maestra_ai.core import storage
from maestra_ai.core.token_store import (
    FileTokenStore,
    KeyringTokenStore,
    default_token_store,
)


class TestKeyringTokenStore:
    def test_save_load_delete_roundtrip(self):
        mock_kr = MagicMock()
        mock_kr.get_password.return_value = "rt_abc"
        with patch("maestra_ai.core.token_store.keyring", mock_kr):
            store = KeyringTokenStore()
            store.save("rt_abc")
            assert store.load() == "rt_abc"
            store.delete()
            mock_kr.set_password.assert_called_once()
            mock_kr.delete_password.assert_called_once()

    def test_load_retorna_none_se_keyring_sem_entrada(self):
        mock_kr = MagicMock()
        mock_kr.get_password.return_value = None
        with patch("maestra_ai.core.token_store.keyring", mock_kr):
            store = KeyringTokenStore()
            assert store.load() is None


class TestFileTokenStore:
    def test_save_cria_arquivo_chmod_600(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
        store = FileTokenStore()
        store.save("rt_file_abc")

        token_file = tmp_path / "token.json"
        assert token_file.exists()
        assert oct(token_file.stat().st_mode)[-3:] == "600"
        data = json.loads(token_file.read_text(encoding="utf-8"))
        assert data["refresh_token"] == "rt_file_abc"

    def test_load_retorna_token(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
        store = FileTokenStore()
        store.save("rt_xyz")
        assert store.load() == "rt_xyz"

    def test_load_arquivo_ausente_retorna_none(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
        store = FileTokenStore()
        assert store.load() is None

    def test_load_arquivo_corrompido_retorna_none(self, tmp_path, monkeypatch):
        """Reusa a tolerância a corrupção do P0-N1 (v0.2.4)."""
        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
        (tmp_path / "token.json").write_text("{not json", encoding="utf-8")
        store = FileTokenStore()
        assert store.load() is None

    def test_load_nao_dict_retorna_none(self, tmp_path, monkeypatch):
        """JSON válido mas não-dict (ex: lista) tratado como ausente."""
        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
        (tmp_path / "token.json").write_text("[1, 2, 3]", encoding="utf-8")
        store = FileTokenStore()
        assert store.load() is None

    def test_delete_remove_arquivo(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
        store = FileTokenStore()
        store.save("rt_xyz")
        store.delete()
        assert not (tmp_path / "token.json").exists()

    def test_delete_idempotente(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
        store = FileTokenStore()
        store.delete()  # não levanta mesmo sem arquivo


class TestDefaultTokenStore:
    def test_prefere_keyring_quando_disponivel(self, monkeypatch):
        with patch("maestra_ai.core.token_store._keyring_backend_ok", return_value=True):
            store = default_token_store()
            assert isinstance(store, KeyringTokenStore)

    def test_fallback_para_file_quando_keyring_falha(self, monkeypatch):
        with patch("maestra_ai.core.token_store._keyring_backend_ok", return_value=False):
            store = default_token_store()
            assert isinstance(store, FileTokenStore)


class TestStorageShim:
    """storage.save/load_refresh_token delegam para default_token_store."""

    def test_save_refresh_token_delega(self, monkeypatch):
        mock_store = MagicMock()
        with patch(
            "maestra_ai.core.token_store.default_token_store",
            return_value=mock_store,
        ):
            storage.save_refresh_token("rt_delegated")
        mock_store.save.assert_called_once_with("rt_delegated")

    def test_load_refresh_token_delega(self, monkeypatch):
        mock_store = MagicMock()
        mock_store.load.return_value = "rt_from_delegate"
        with patch(
            "maestra_ai.core.token_store.default_token_store",
            return_value=mock_store,
        ):
            assert storage.load_refresh_token() == "rt_from_delegate"
