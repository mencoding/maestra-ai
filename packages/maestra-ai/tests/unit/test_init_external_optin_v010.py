"""v0.10.4: opt-in estendido com 3 opções (MB-only / configurar todas / pular).

Keys são gravadas no keyring — não no dict retornado por _prompt_external_sources_optin.
"""
from __future__ import annotations


def test_optin_returns_structured_result(mocker):
    """_prompt_external_sources_optin retorna dict com cada source ativo/inativo."""
    sel = mocker.patch("maestra_ai.core.init.questionary.select")
    sel.return_value.ask.return_value = "Só MusicBrainz (não preciso mexer em mais nada agora)"
    from maestra_ai.core.init import _prompt_external_sources_optin
    result = _prompt_external_sources_optin()
    assert result["musicbrainz"]["enabled"] is True
    assert result["lastfm"]["enabled"] is False
    assert result["getsongbpm"]["enabled"] is False


def test_optin_configure_all_runs_lastfm_guide(mocker):
    """Quando guia retorna (True, key), keyring é chamado e api_key não entra no dict."""
    sel = mocker.patch("maestra_ai.core.init.questionary.select")
    sel.return_value.ask.return_value = "Configurar Last.fm e/ou GetSongBPM agora (guias passo-a-passo)"
    guide_lf = mocker.patch("maestra_ai.core.init.guide_lastfm", return_value=(True, "a" * 32))
    guide_gsb = mocker.patch("maestra_ai.core.init.guide_getsongbpm", return_value=(False, None))
    mock_set_key = mocker.patch("maestra_ai.core.init.set_source_key")

    from maestra_ai.core.init import _prompt_external_sources_optin
    result = _prompt_external_sources_optin()

    assert result["musicbrainz"]["enabled"] is True
    assert result["lastfm"]["enabled"] is True
    # v0.10.4: api_key não entra no dict — vai para keyring
    assert "api_key" not in result["lastfm"]
    assert result["getsongbpm"]["enabled"] is False
    guide_lf.assert_called_once()
    guide_gsb.assert_called_once()
    mock_set_key.assert_called_once_with("lastfm", "a" * 32)


def test_optin_skip_returns_all_disabled(mocker):
    sel = mocker.patch("maestra_ai.core.init.questionary.select")
    sel.return_value.ask.return_value = "Pular tudo, configurar depois com 'maestra config external'"
    from maestra_ai.core.init import _prompt_external_sources_optin
    result = _prompt_external_sources_optin()
    assert result["musicbrainz"]["enabled"] is False
    assert result["lastfm"]["enabled"] is False
    assert result["getsongbpm"]["enabled"] is False


def test_optin_configure_all_runs_both_guides(mocker):
    """Ambos os guias rodam e as keys são gravadas no keyring."""
    sel = mocker.patch("maestra_ai.core.init.questionary.select")
    sel.return_value.ask.return_value = "Configurar Last.fm e/ou GetSongBPM agora (guias passo-a-passo)"
    mocker.patch("maestra_ai.core.init.guide_lastfm", return_value=(True, "a" * 32))
    mocker.patch("maestra_ai.core.init.guide_getsongbpm", return_value=(True, "gsbkey123"))
    mock_set_key = mocker.patch("maestra_ai.core.init.set_source_key")

    from maestra_ai.core.init import _prompt_external_sources_optin
    result = _prompt_external_sources_optin()

    assert result["getsongbpm"]["enabled"] is True
    assert "api_key" not in result["getsongbpm"]
    # Dois set_source_key chamados
    calls = {call.args[0]: call.args[1] for call in mock_set_key.call_args_list}
    assert calls["lastfm"] == "a" * 32
    assert calls["getsongbpm"] == "gsbkey123"


def test_optin_keyring_failure_does_not_crash(mocker):
    """Falha no keyring emite warning mas não levanta exceção."""
    sel = mocker.patch("maestra_ai.core.init.questionary.select")
    sel.return_value.ask.return_value = "Configurar Last.fm e/ou GetSongBPM agora (guias passo-a-passo)"
    mocker.patch("maestra_ai.core.init.guide_lastfm", return_value=(True, "mykey"))
    mocker.patch("maestra_ai.core.init.guide_getsongbpm", return_value=(False, None))
    mocker.patch("maestra_ai.core.init.set_source_key", side_effect=RuntimeError("keyring down"))

    from maestra_ai.core.init import _prompt_external_sources_optin
    # Não deve levantar exceção
    result = _prompt_external_sources_optin()
    assert result["lastfm"]["enabled"] is True
