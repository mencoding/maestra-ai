"""Testes do prompt opt-in de fontes externas no init."""
from unittest.mock import patch

from maestra_ai.core.init import _prompt_external_sources_optin


def test_prompt_returns_true_for_option_3():
    with patch("rich.prompt.Prompt.ask", return_value="3"):
        choice = _prompt_external_sources_optin()
    assert choice is True


def test_prompt_returns_false_for_option_2():
    with patch("rich.prompt.Prompt.ask", return_value="2"):
        choice = _prompt_external_sources_optin()
    assert choice is False


def test_prompt_option_1_reprompts(capsys):
    """v0.9: opção 1 (Last.fm/BPM) ainda não disponível. Deve re-promptar."""
    with patch("rich.prompt.Prompt.ask", side_effect=["1", "2"]):
        choice = _prompt_external_sources_optin()
    assert choice is False
