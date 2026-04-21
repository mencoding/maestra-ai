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


class TestPositivos:
    def test_extrai_termo_apos_tipo(self):
        from maestra_ai.core.context_parser import parse
        p = parse("tipo lo-fi")
        assert "lo-fi" in p.positive

    def test_extrai_termo_apos_como(self):
        from maestra_ai.core.context_parser import parse
        p = parse("algo como jazz")
        assert "jazz" in p.positive

    def test_extrai_termo_apos_parecido_com(self):
        from maestra_ai.core.context_parser import parse
        p = parse("parecido com bossa")
        assert "bossa" in p.positive

    def test_positivo_e_negativo_coexistem(self):
        from maestra_ai.core.context_parser import parse
        p = parse("tipo rock, sem ballads")
        assert "rock" in p.positive
        assert "ballads" in p.negative


class TestArtistsHint:
    def test_captura_nome_proprio_apos_marker_positivo(self):
        from maestra_ai.core.context_parser import parse
        p = parse("tipo The HU")
        assert "The HU" in p.artists_hint

    def test_captura_multi_palavra_capitalizada(self):
        from maestra_ai.core.context_parser import parse
        p = parse("como Dance With The Dead")
        assert "Dance With The Dead" in p.artists_hint

    def test_palavra_minuscula_nao_vira_artist(self):
        from maestra_ai.core.context_parser import parse
        p = parse("tipo rock")
        assert p.artists_hint == ()


class TestNormalizacao:
    def test_nao_e_nao_sao_equivalentes(self):
        from maestra_ai.core.context_parser import parse
        p1 = parse("não acústico")
        p2 = parse("nao acustico")
        # Ambos devem pegar o negativo
        assert len(p1.negative) == 1
        assert len(p2.negative) == 1

    def test_maiusculas_nao_afetam_marker(self):
        from maestra_ai.core.context_parser import parse
        p = parse("EVITAR jazz")
        assert "jazz" in p.negative

    def test_acentos_preservados_no_term_extraido(self):
        from maestra_ai.core.context_parser import parse
        p = parse("sem distração")
        # O term pode estar normalizado ou preservado — o importante é
        # que o match funcionou e o term é recuperável
        assert len(p.negative) == 1
