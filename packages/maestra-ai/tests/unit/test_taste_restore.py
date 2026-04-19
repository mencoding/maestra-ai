"""HIGH-2: taste.restore valida schema antes de sobrescrever.
v0.5.5 #5: restore/save limpam .tmp órfão em falha de os.replace.
"""
from __future__ import annotations

import pytest

from maestra_ai.core.errors import StorageError, ValidationError
from maestra_ai.core.taste import TasteProfile


class TestAtomicWriteCleanup:
    """v0.5.5 #5: se os.replace falha durante save/restore, o .tmp não
    pode ficar órfão e a exceção deve ser traduzida para StorageError."""

    def test_save_limpa_tmp_quando_os_replace_falha(self, tmp_path, monkeypatch):
        import os
        tp = TasteProfile(path=str(tmp_path / "taste.json"))

        def _fake_replace(src, dst):
            raise OSError(28, "No space left on device")

        monkeypatch.setattr(os, "replace", _fake_replace)
        with pytest.raises(StorageError) as exc:
            tp.save()
        assert "persistir perfil" in exc.value.what_happened_msg
        # .tmp não pode estar órfão
        tmp = f"{tp.path}.tmp"
        assert not os.path.exists(tmp), \
            f".tmp órfão em {tmp} após falha de save"

    def test_restore_limpa_tmp_quando_os_replace_falha(self, tmp_path, monkeypatch):
        import os
        tp = TasteProfile(path=str(tmp_path / "taste.json"))

        def _fake_replace(src, dst):
            raise OSError(13, "Permission denied")

        monkeypatch.setattr(os, "replace", _fake_replace)
        payload = {"tracks": {"spotify:track:y": {"weight": 2}}}
        with pytest.raises(StorageError):
            tp.restore(payload)
        tmp = f"{tp.path}.tmp"
        assert not os.path.exists(tmp)


def test_restore_aceita_payload_valido(tmp_path):
    tp = TasteProfile(path=str(tmp_path / "taste.json"))
    payload = {
        "global": {"positive_count": 5},
        "tracks": {
            "spotify:track:abc": {
                "name": "Foo",
                "artist": "Bar",
                "weight": 3,
            }
        },
        "success_rates": {},
        "context_tokens": {},
    }
    tp.restore(payload)
    assert tp.data["tracks"]["spotify:track:abc"]["weight"] == 3


def test_restore_rejeita_tipo_errado(tmp_path):
    tp = TasteProfile(path=str(tmp_path / "taste.json"))
    with pytest.raises(ValidationError):
        tp.restore("não é um dict")


def test_restore_rejeita_tracks_nao_dict(tmp_path):
    tp = TasteProfile(path=str(tmp_path / "taste.json"))
    with pytest.raises(ValidationError):
        tp.restore({"tracks": [1, 2, 3]})


def test_restore_rejeita_track_sem_estrutura_esperada(tmp_path):
    tp = TasteProfile(path=str(tmp_path / "taste.json"))
    with pytest.raises(ValidationError):
        tp.restore({"tracks": {"spotify:track:abc": "should be dict"}})


def test_restore_rejeita_weight_nao_numerico(tmp_path):
    tp = TasteProfile(path=str(tmp_path / "taste.json"))
    with pytest.raises(ValidationError):
        tp.restore({
            "tracks": {
                "spotify:track:abc": {"weight": "three"}
            }
        })


def test_restore_nao_corrompe_perfil_em_falha(tmp_path):
    """Se validação falhar, perfil em memória E em disco devem permanecer intactos."""
    path = tmp_path / "taste.json"
    tp = TasteProfile(path=str(path))
    tp.record_global_positive("spotify:track:original", name="Original", weight=5)
    original_data = dict(tp.data)

    with pytest.raises(ValidationError):
        tp.restore("payload inválido")

    # Memória preservada
    assert tp.data == original_data
    # Disco não foi tocado com lixo
    if path.exists():
        import json
        on_disk = json.loads(path.read_text())
        assert "spotify:track:original" in on_disk.get("tracks", {})
