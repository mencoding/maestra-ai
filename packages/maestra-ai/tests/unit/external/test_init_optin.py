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


def test_state_c_offers_migration_when_external_flag_absent(monkeypatch, tmp_path):
    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path / "config" / "maestra"))
    (tmp_path / "config" / "maestra").mkdir(parents=True)
    import json
    (tmp_path / "config" / "maestra" / "config.json").write_text(json.dumps({
        "client_id": "x", "client_secret": "y", "redirect_uri": "z",
    }))
    from maestra_ai.core.init import _state_c_should_offer_external
    assert _state_c_should_offer_external() is True


def test_state_c_does_not_offer_when_already_decided(tmp_path, monkeypatch):
    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path / "config" / "maestra"))
    (tmp_path / "config" / "maestra").mkdir(parents=True)
    import json
    (tmp_path / "config" / "maestra" / "config.json").write_text(json.dumps({
        "client_id": "x", "client_secret": "y", "redirect_uri": "z",
        "external_sources_enabled": False,
    }))
    from maestra_ai.core.init import _state_c_should_offer_external
    assert _state_c_should_offer_external() is False
