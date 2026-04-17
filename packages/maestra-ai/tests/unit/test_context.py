"""Testes do ContextState — contexto musical ativo."""
import json
from datetime import datetime, timedelta

from maestra_ai.core.context import ContextState


def test_show_retorna_none_se_arquivo_nao_existe(tmp_path):
    state = ContextState(str(tmp_path / "current_context.json"))

    assert state.show() is None


def test_set_e_show_preserva_contexto(tmp_path):
    state = ContextState(str(tmp_path / "current_context.json"))

    result = state.set("foco profundo", ttl_minutes=90)

    assert result["context"] == "foco profundo"
    assert result["ttl_minutes"] == 90
    assert state.show()["context"] == "foco profundo"


def test_clear_remove_contexto(tmp_path):
    path = tmp_path / "current_context.json"
    state = ContextState(str(path))
    state.set("energia")

    result = state.clear()

    assert result == {"status": "cleared"}
    assert state.show() is None
    assert not path.exists()


def test_show_retorna_none_para_contexto_expirado(tmp_path):
    path = tmp_path / "current_context.json"
    expired = {
        "context": "foco",
        "set_at": (datetime.now() - timedelta(minutes=120)).isoformat(timespec="seconds"),
        "ttl_minutes": 60,
    }
    path.write_text(json.dumps(expired), encoding="utf-8")
    state = ContextState(str(path))

    assert state.show() is None
    assert not path.exists()


def test_show_ignora_ttl_nulo(tmp_path):
    path = tmp_path / "current_context.json"
    data = {
        "context": "foco",
        "set_at": (datetime.now() - timedelta(days=1)).isoformat(timespec="seconds"),
        "ttl_minutes": None,
    }
    path.write_text(json.dumps(data), encoding="utf-8")
    state = ContextState(str(path))

    assert state.show()["context"] == "foco"
