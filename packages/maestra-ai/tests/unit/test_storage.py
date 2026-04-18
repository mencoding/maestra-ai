"""Testes de storage — XDG, env override, keyring fallback."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from maestra_ai.core import storage
from maestra_ai.core.errors import ConfigError


def test_config_dir_xdg_default(monkeypatch, tmp_path):
    monkeypatch.delenv("MAESTRA_CONFIG_DIR", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    p = storage.config_dir()
    assert p == tmp_path / "maestra"


def test_config_dir_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path / "custom"))
    p = storage.config_dir()
    assert p == tmp_path / "custom"


def test_data_dir_xdg_default(monkeypatch, tmp_path):
    monkeypatch.delenv("MAESTRA_DATA_DIR", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    p = storage.data_dir()
    assert p == tmp_path / "maestra"


def test_data_dir_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "dados"))
    p = storage.data_dir()
    assert p == tmp_path / "dados"


def test_ensure_dirs_creates(monkeypatch, tmp_path):
    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("MAESTRA_STATE_DIR", str(tmp_path / "state"))
    storage.ensure_dirs()
    assert (tmp_path / "cfg").is_dir()
    assert (tmp_path / "data").is_dir()
    assert (tmp_path / "state").is_dir()


def test_config_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
    storage.write_config({"client_id": "abc", "playlist_id": "xyz"})
    c = storage.read_config()
    assert c["client_id"] == "abc"


def test_read_config_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
    c = storage.read_config()
    assert c == {}


def test_keyring_save_and_load(monkeypatch):
    mock_keyring = MagicMock()
    mock_keyring.get_password.return_value = "refresh_token_xyz"
    with patch.object(storage, "_keyring_backend_ok", return_value=True), \
         patch.object(storage, "keyring", mock_keyring, create=True):
        storage.save_refresh_token("tok_123")
        mock_keyring.set_password.assert_called_once()
        result = storage.load_refresh_token()
        assert result == "refresh_token_xyz"


def test_load_refresh_token_corrupt_returns_none(monkeypatch, tmp_path):
    """P0-N1: token.json corrompido deve retornar None, não crashar."""
    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
    with patch.object(storage, "_keyring_backend_ok", return_value=False):
        token_file = tmp_path / "token.json"
        token_file.write_text("{invalid json", encoding="utf-8")
        assert storage.load_refresh_token() is None


def test_load_refresh_token_non_dict_returns_none(monkeypatch, tmp_path):
    """P0-N1: token.json com JSON válido mas não-dict deve retornar None."""
    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
    with patch.object(storage, "_keyring_backend_ok", return_value=False):
        token_file = tmp_path / "token.json"
        token_file.write_text("[1, 2, 3]", encoding="utf-8")
        assert storage.load_refresh_token() is None


def test_read_config_corrupt_raises_config_error(monkeypatch, tmp_path):
    """P0-N1.b: config.json malformado deve levantar ConfigError, não JSONDecodeError."""
    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
    (tmp_path / "config.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ConfigError):
        storage.read_config()


def test_read_config_non_dict_raises_config_error(monkeypatch, tmp_path):
    """P0-N1.b: config.json com lista/primitivo deve levantar ConfigError."""
    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
    (tmp_path / "config.json").write_text('["not", "a", "dict"]', encoding="utf-8")
    with pytest.raises(ConfigError):
        storage.read_config()


def test_keyring_fallback_to_file(monkeypatch, tmp_path):
    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
    with patch.object(storage, "_keyring_backend_ok", return_value=False):
        storage.save_refresh_token("tok_fallback")
        token_file = tmp_path / "token.json"
        assert token_file.exists()
        mode = oct(token_file.stat().st_mode)[-3:]
        assert mode == "600"
        loaded = storage.load_refresh_token()
        assert loaded == "tok_fallback"
