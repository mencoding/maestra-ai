"""Testes de storage — XDG, env override, keyring fallback."""
from __future__ import annotations

import json

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


def test_atomic_write_json_cria_arquivo(tmp_path):
    """P0-5: helper atomic_write_json persiste dict em JSON."""
    path = tmp_path / "state.json"
    storage.atomic_write_json(str(path), {"k": "v", "n": 42})
    assert json.loads(path.read_text(encoding="utf-8")) == {"k": "v", "n": 42}


def test_atomic_write_json_sobrescreve_preserva_atomicidade(tmp_path):
    """P0-5: rewrite sobrescreve e não deixa .tmp residual."""
    path = tmp_path / "state.json"
    storage.atomic_write_json(str(path), {"gen": 1})
    storage.atomic_write_json(str(path), {"gen": 2})
    assert json.loads(path.read_text(encoding="utf-8")) == {"gen": 2}
    assert not (tmp_path / "state.json.tmp").exists()


def test_atomic_write_json_serializa_writes_concorrentes(tmp_path):
    """P0-5: writes paralelos via fcntl.LOCK_EX produzem um dos valores, não corrompem."""
    import threading
    path = tmp_path / "state.json"

    def writer(n):
        for _ in range(20):
            storage.atomic_write_json(str(path), {"writer": n})

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Arquivo final é JSON válido (não corrompido por write parcial)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["writer"] in {0, 1, 2, 3}


def test_update_json_under_lock_preserva_chaves_concorrentes(tmp_path):
    """P0-5: read-modify-write atômico não perde atualização de outra chave."""
    import threading
    path = tmp_path / "state.json"
    storage.atomic_write_json(str(path), {})

    def writer(key):
        for _ in range(15):
            storage.update_json_under_lock(
                str(path),
                lambda d, k=key: {**d, k: d.get(k, 0) + 1},
            )

    threads = [threading.Thread(target=writer, args=(f"k{i}",)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    data = json.loads(path.read_text(encoding="utf-8"))
    # Cada thread incrementou 15 vezes sua chave — sem lost update, todas batem 15
    assert data == {"k0": 15, "k1": 15, "k2": 15, "k3": 15}


def test_update_json_under_lock_arquivo_inexistente_comeca_vazio(tmp_path):
    path = tmp_path / "new.json"
    storage.update_json_under_lock(str(path), lambda d: {**d, "first": True})
    assert json.loads(path.read_text(encoding="utf-8")) == {"first": True}


# Testes de keyring/file via storage.save/load_refresh_token migraram para
# test_token_store.py quando essas funções viraram shim na v0.3.0.


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


# test_keyring_fallback_to_file removido — coberto por
# test_token_store.TestDefaultTokenStore + TestFileTokenStore


class TestAppendJsonlLocked:
    def test_serializa_entry_com_acento(self, tmp_path):
        from maestra_ai.core.storage import append_jsonl_locked
        path = tmp_path / "log.jsonl"
        append_jsonl_locked(path, {"user": "João", "city": "São Paulo"})
        lines = path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed == {"user": "João", "city": "São Paulo"}

    def test_concorrencia_nao_intercala_bytes(self, tmp_path):
        import threading

        from maestra_ai.core.storage import append_jsonl_locked
        path = tmp_path / "log.jsonl"

        def writer(tid: int):
            for i in range(50):
                append_jsonl_locked(path, {"thread": tid, "i": i, "pad": "x" * 500})

        threads = [threading.Thread(target=writer, args=(t,)) for t in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        lines = path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 100
        # Todas as linhas devem ser JSON válido — prova ausência de intercalação.
        for line in lines:
            parsed = json.loads(line)
            assert set(parsed.keys()) == {"thread", "i", "pad"}
