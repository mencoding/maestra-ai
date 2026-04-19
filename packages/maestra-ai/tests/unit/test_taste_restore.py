"""HIGH-2: taste.restore valida schema antes de sobrescrever."""
from __future__ import annotations

import pytest

from maestra_ai.core.errors import ValidationError
from maestra_ai.core.taste import TasteProfile


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
