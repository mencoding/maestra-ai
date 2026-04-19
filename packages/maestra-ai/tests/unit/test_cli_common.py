"""Testes de helpers em cli/_common.py — resolve_playlist_id (Fix BLOCKER-1)."""
from __future__ import annotations

import pytest

from maestra_ai.cli._common import resolve_playlist_id, safe_call
from maestra_ai.core import storage
from maestra_ai.core.errors import ConfigError


class TestImportSemSideEffect:
    """v0.5.6 #13: `import maestra_ai.cli._common` NÃO deve criar
    diretório no disco. O side-effect antigo (`os.makedirs(BASE_DIR)`
    no topo) dificultava testes que monkeypatch MAESTRA_DATA_DIR."""

    def test_import_nao_cria_dir_no_path_do_env(self, tmp_path, monkeypatch):
        import importlib
        import sys

        custom_dir = tmp_path / "maestra-data-test"
        monkeypatch.setenv("MAESTRA_DATA_DIR", str(custom_dir))
        # Força reimport do módulo e do storage.
        for m in ("maestra_ai.cli._common", "maestra_ai.core.storage"):
            sys.modules.pop(m, None)
        importlib.import_module("maestra_ai.cli._common")
        # O import NÃO deve ter criado custom_dir.
        assert not custom_dir.exists(), \
            f"import criou diretório {custom_dir} — side-effect proibido"


class TestSafeCallRedact:
    """v0.5.5 #2: safe_call redacta str(e) antes de retornar no dict
    de erro. Antes, tokens em mensagens de SpotifyException vazavam
    via cmd_status (que usa safe_call para compor o status agregado).
    """

    def test_bearer_token_em_excecao_e_redactado(self):
        def _raise():
            raise RuntimeError(
                "Authorization: Bearer BQAkZ9xK_abc123def456ghi789 falhou",
            )
        result = safe_call(_raise, "TEST_ERROR")
        assert "BQAkZ9xK" not in result["error"]
        assert "REDACTED" in result["error"]
        assert result["code"] == "TEST_ERROR"

    def test_client_secret_na_excecao_e_redactado(self):
        def _raise():
            raise ValueError("client_secret=xpto123 inválido")
        result = safe_call(_raise, "CFG_ERR")
        assert "xpto123" not in result["error"]

    def test_sucesso_retorna_valor_sem_modificar(self):
        result = safe_call(lambda: {"ok": True}, "X")
        assert result == {"ok": True}


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
