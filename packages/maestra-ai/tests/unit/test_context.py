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

    assert result["context"]["text"] == "foco profundo"
    assert result["ttl_minutes"] == 90
    assert state.show()["context"]["text"] == "foco profundo"


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


def test_show_retorna_none_para_json_corrompido(tmp_path):
    path = tmp_path / "context.json"
    path.write_text("not valid json")
    ctx = ContextState(str(path))
    assert ctx.show() is None


def test_show_retorna_none_para_json_sem_set_at(tmp_path):
    path = tmp_path / "context.json"
    path.write_text('{"context": "foco", "ttl_minutes": 120}')
    ctx = ContextState(str(path))
    assert ctx.show() is None


def test_show_limpa_state_com_iso_malformado(tmp_path):
    """HIGH-1: set_at malformado (ValueError em fromisoformat) deve
    limpar o state e retornar None em vez de crashar."""
    path = tmp_path / "ctx.json"
    path.write_text('{"context": "foco", "set_at": "nao-é-iso", "ttl_minutes": 60}')
    state = ContextState(str(path))
    assert state.show() is None
    # Arquivo limpo após detecção do erro
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

    assert state.show()["context"]["text"] == "foco"


class TestParsed:
    def test_parsed_retorna_none_quando_sem_contexto(self, tmp_path):
        state = ContextState(str(tmp_path / "ctx.json"))
        assert state.parsed() is None

    def test_parsed_retorna_parsed_context_apos_set(self, tmp_path):
        from maestra_ai.core.context_parser import ParsedContext
        state = ContextState(str(tmp_path / "ctx.json"))
        state.set("metal tribal evitar ambient")
        p = state.parsed()
        assert isinstance(p, ParsedContext)
        assert "ambient" in p.negative

    def test_parsed_memoiza_entre_chamadas(self, tmp_path):
        state = ContextState(str(tmp_path / "ctx.json"))
        state.set("foco")
        p1 = state.parsed()
        p2 = state.parsed()
        assert p1 is p2  # identidade preservada por memoização

    def test_parsed_invalida_apos_novo_set(self, tmp_path):
        state = ContextState(str(tmp_path / "ctx.json"))
        state.set("foco")
        p1 = state.parsed()
        state.set("energia")
        p2 = state.parsed()
        assert p1 is not p2
        assert p2.text == "energia"

    def test_parsed_repass_bpm_do_context(self, tmp_path):
        from maestra_ai.core.context_parser import BpmRange
        state = ContextState(str(tmp_path / "ctx.json"))
        state.set("foco", bpm={"min": 60, "max": 90})
        p = state.parsed()
        assert p.bpm == BpmRange(min=60, max=90)
