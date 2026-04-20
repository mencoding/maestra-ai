"""Valida guias interativos de configuração das fontes externas."""
from __future__ import annotations

from maestra_ai.core.external.setup_guides import _validate_lastfm_key, guide_lastfm


def test_validate_lastfm_key_accepts_32_hex():
    assert _validate_lastfm_key("0123456789abcdef0123456789abcdef") is True


def test_validate_lastfm_key_rejects_short():
    assert _validate_lastfm_key("abc") is False


def test_validate_lastfm_key_rejects_whitespace():
    assert _validate_lastfm_key("0123456789abcdef 0123456789abcdef") is False


def test_validate_lastfm_key_rejects_empty():
    assert _validate_lastfm_key("") is False


def test_guide_lastfm_empty_input_returns_skip(mocker):
    mock_prompt = mocker.patch("maestra_ai.core.external.setup_guides.questionary.text")
    mock_prompt.return_value.ask.return_value = ""
    mocker.patch("maestra_ai.core.external.setup_guides.questionary.confirm")
    enabled, key = guide_lastfm()
    assert enabled is False
    assert key is None


def test_guide_lastfm_valid_key_returns_configured(mocker):
    mock_prompt = mocker.patch("maestra_ai.core.external.setup_guides.questionary.text")
    valid_key = "a" * 32
    mock_prompt.return_value.ask.return_value = valid_key
    enabled, key = guide_lastfm()
    assert enabled is True
    assert key == valid_key


def test_guide_lastfm_invalid_then_skip(mocker):
    mock_prompt = mocker.patch("maestra_ai.core.external.setup_guides.questionary.text")
    mock_prompt.return_value.ask.side_effect = ["xyz", ""]
    mock_confirm = mocker.patch("maestra_ai.core.external.setup_guides.questionary.confirm")
    mock_confirm.return_value.ask.return_value = True  # quer tentar de novo
    enabled, key = guide_lastfm()
    assert enabled is False
    assert key is None
