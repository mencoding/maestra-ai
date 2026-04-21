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
