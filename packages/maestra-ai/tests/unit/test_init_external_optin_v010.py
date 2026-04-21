"""v0.11.0: opt-in reformulado com 3 opções (default MB+RB / com LF / pular).

Keys são gravadas no keyring — não no dict retornado por _prompt_external_sources_optin.
Reccobeats não precisa de key — é ativado sem interação.
"""
from __future__ import annotations


def test_optin_default_returns_mb_and_reccobeats_enabled(mocker):
    """Opção padrão ativa MusicBrainz + Reccobeats, sem Last.fm."""
    sel = mocker.patch("maestra_ai.core.init.questionary.select")
    sel.return_value.ask.return_value = "Padrão (MusicBrainz + Reccobeats) — grátis, sem chave, recomendado"
    from maestra_ai.core.init import _prompt_external_sources_optin
    result = _prompt_external_sources_optin()
    assert result["musicbrainz"]["enabled"] is True
    assert result["reccobeats"]["enabled"] is True
    assert result["lastfm"]["enabled"] is False
    assert "getsongbpm" not in result


def test_optin_with_lastfm_runs_guide(mocker):
    """Opção 'com LF' roda guide_lastfm; key é gravada no keyring."""
    sel = mocker.patch("maestra_ai.core.init.questionary.select")
    sel.return_value.ask.return_value = "Padrão + Last.fm (tags folksonômicas ricas, ~2 min para API key)"
    guide_lf = mocker.patch("maestra_ai.core.init.guide_lastfm", return_value=(True, "a" * 32))
    mock_set_key = mocker.patch("maestra_ai.core.init.set_source_key")

    from maestra_ai.core.init import _prompt_external_sources_optin
    result = _prompt_external_sources_optin()

    assert result["musicbrainz"]["enabled"] is True
    assert result["reccobeats"]["enabled"] is True
    assert result["lastfm"]["enabled"] is True
    assert "api_key" not in result["lastfm"]
    assert "getsongbpm" not in result
    guide_lf.assert_called_once()
    mock_set_key.assert_called_once_with("lastfm", "a" * 32)


def test_optin_skip_returns_all_disabled(mocker):
    sel = mocker.patch("maestra_ai.core.init.questionary.select")
    sel.return_value.ask.return_value = "Pular tudo, configurar depois com 'maestra config external'"
    from maestra_ai.core.init import _prompt_external_sources_optin
    result = _prompt_external_sources_optin()
    assert result["musicbrainz"]["enabled"] is False
    assert result["reccobeats"]["enabled"] is False
    assert result["lastfm"]["enabled"] is False
    assert "getsongbpm" not in result


def test_optin_with_lastfm_skipped_guide(mocker):
    """Guia Last.fm pulado: lastfm.enabled=False, mas MB + Reccobeats ativos."""
    sel = mocker.patch("maestra_ai.core.init.questionary.select")
    sel.return_value.ask.return_value = "Padrão + Last.fm (tags folksonômicas ricas, ~2 min para API key)"
    mocker.patch("maestra_ai.core.init.guide_lastfm", return_value=(False, None))
    mocker.patch("maestra_ai.core.init.set_source_key")

    from maestra_ai.core.init import _prompt_external_sources_optin
    result = _prompt_external_sources_optin()

    assert result["musicbrainz"]["enabled"] is True
    assert result["reccobeats"]["enabled"] is True
    assert result["lastfm"]["enabled"] is False


def test_optin_keyring_failure_does_not_crash(mocker):
    """Falha no keyring emite warning mas não levanta exceção."""
    sel = mocker.patch("maestra_ai.core.init.questionary.select")
    sel.return_value.ask.return_value = "Padrão + Last.fm (tags folksonômicas ricas, ~2 min para API key)"
    mocker.patch("maestra_ai.core.init.guide_lastfm", return_value=(True, "mykey"))
    mocker.patch("maestra_ai.core.init.set_source_key", side_effect=RuntimeError("keyring down"))

    from maestra_ai.core.init import _prompt_external_sources_optin
    # Não deve levantar exceção
    result = _prompt_external_sources_optin()
    assert result["lastfm"]["enabled"] is True
    assert result["reccobeats"]["enabled"] is True
