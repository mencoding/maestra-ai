"""v0.10: opt-in estendido com 3 opções (MB-only / configurar todas / pular)."""
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
    sel = mocker.patch("maestra_ai.core.init.questionary.select")
    sel.return_value.ask.return_value = "Configurar Last.fm e/ou GetSongBPM agora (guias passo-a-passo)"
    guide_lf = mocker.patch("maestra_ai.core.init.guide_lastfm", return_value=(True, "a" * 32))
    guide_gsb = mocker.patch("maestra_ai.core.init.guide_getsongbpm", return_value=(False, None))
    from maestra_ai.core.init import _prompt_external_sources_optin
    result = _prompt_external_sources_optin()
    assert result["musicbrainz"]["enabled"] is True
    assert result["lastfm"]["enabled"] is True
    assert result["lastfm"]["api_key"] == "a" * 32
    assert result["getsongbpm"]["enabled"] is False
    guide_lf.assert_called_once()
    guide_gsb.assert_called_once()


def test_optin_skip_returns_all_disabled(mocker):
    sel = mocker.patch("maestra_ai.core.init.questionary.select")
    sel.return_value.ask.return_value = "Pular tudo, configurar depois com 'maestra config external'"
    from maestra_ai.core.init import _prompt_external_sources_optin
    result = _prompt_external_sources_optin()
    assert result["musicbrainz"]["enabled"] is False
    assert result["lastfm"]["enabled"] is False
