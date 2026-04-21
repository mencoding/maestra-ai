"""Testes do parser de contexto (issue #8, v0.13)."""
from __future__ import annotations

import dataclasses

import pytest


def test_parse_retorna_parsed_context_com_text_vazio_quando_input_vazio():
    from maestra_ai.core.context_parser import ParsedContext, parse
    p = parse("")
    assert isinstance(p, ParsedContext)
    assert p.text == ""
    assert p.positive == ()
    assert p.negative == ()
    assert p.artists_hint == ()
    assert p.bpm is None


def test_parsed_context_e_frozen():
    from maestra_ai.core.context_parser import ParsedContext
    p = ParsedContext(text="x")
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.text = "mudou"  # type: ignore[misc]


class TestNegativos:
    def test_extrai_um_negativo_apos_evitar(self):
        from maestra_ai.core.context_parser import parse
        p = parse("metal evitar ambient")
        assert "ambient" in p.negative

    def test_extrai_um_negativo_apos_sem(self):
        from maestra_ai.core.context_parser import parse
        p = parse("rock sem ballads")
        assert "ballads" in p.negative

    def test_extrai_um_negativo_apos_nao(self):
        from maestra_ai.core.context_parser import parse
        p = parse("música não acústica")
        assert "acústica" in p.negative

    def test_extrai_multiplos_negativos_em_virgula(self):
        from maestra_ai.core.context_parser import parse
        p = parse("foco sem distração, evitar vocal")
        assert "distração" in p.negative
        assert "vocal" in p.negative

    def test_nenhuma_negacao_retorna_tupla_vazia(self):
        from maestra_ai.core.context_parser import parse
        p = parse("metal tribal denso")
        assert p.negative == ()
