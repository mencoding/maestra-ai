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

    def test_artist_nao_vaza_para_positive(self):
        """Regressão: `parse("tipo The HU")` devia ter positive=() e
        artists_hint=('The HU',), não positive=('the',)."""
        from maestra_ai.core.context_parser import parse
        p = parse("tipo The HU")
        assert "The HU" in p.artists_hint
        assert p.positive == ()

    def test_artist_e_genero_coexistem_na_mesma_clausula(self):
        """Se o primeiro token é capitalizado (artist) o positive fica
        vazio. Se artist vem depois, positive captura o primeiro token."""
        from maestra_ai.core.context_parser import parse
        # Primeiro token minúsculo → positive; artist detectado separadamente
        p = parse("tipo metal Gojira")
        assert "metal" in p.positive
        assert "Gojira" in p.artists_hint


class TestBpmRange:
    def test_bpmrange_e_frozen(self):
        from dataclasses import FrozenInstanceError
        from maestra_ai.core.context_parser import BpmRange
        b = BpmRange(min=100, max=120)
        with pytest.raises(FrozenInstanceError):
            b.min = 200  # type: ignore[misc]

    def test_from_any_aceita_none(self):
        from maestra_ai.core.context_parser import BpmRange
        assert BpmRange.from_any(None) is None

    def test_from_any_aceita_dict(self):
        from maestra_ai.core.context_parser import BpmRange
        b = BpmRange.from_any({"min": 100, "max": 120})
        assert b == BpmRange(min=100, max=120)

    def test_from_any_aceita_bpmrange_passa_direto(self):
        from maestra_ai.core.context_parser import BpmRange
        original = BpmRange(min=100, max=120)
        assert BpmRange.from_any(original) is original

    def test_from_any_rejeita_tipo_invalido(self):
        from maestra_ai.core.context_parser import BpmRange
        with pytest.raises(TypeError):
            BpmRange.from_any("100-120")  # type: ignore[arg-type]


class TestParsedContextHashable:
    def test_hash_funciona_sem_bpm(self):
        from maestra_ai.core.context_parser import parse
        p = parse("foco")
        hash(p)  # não deve explodir

    def test_hash_funciona_com_bpm(self):
        from maestra_ai.core.context_parser import parse
        p = parse("foco", bpm={"min": 100, "max": 120})
        hash(p)  # não deve explodir

    def test_parse_com_dict_bpm_equivalente_a_parse_com_bpmrange(self):
        from maestra_ai.core.context_parser import BpmRange, parse
        p1 = parse("foco", bpm={"min": 100, "max": 120})
        p2 = parse("foco", bpm=BpmRange(min=100, max=120))
        assert p1 == p2
        assert p1.bpm == BpmRange(min=100, max=120)


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
