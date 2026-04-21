"""Testes do prompt opt-in de fontes externas no init (v0.11)."""
import json

from maestra_ai.core.init import _prompt_external_sources_optin


def test_prompt_returns_dict_for_default_mb_and_reccobeats(mocker):
    sel = mocker.patch("maestra_ai.core.init.questionary.select")
    sel.return_value.ask.return_value = "Padrão (MusicBrainz + Reccobeats) — grátis, sem chave, recomendado"
    result = _prompt_external_sources_optin()
    assert result["musicbrainz"]["enabled"] is True
    assert result["reccobeats"]["enabled"] is True
    assert result["lastfm"]["enabled"] is False
    assert "getsongbpm" not in result


def test_prompt_returns_all_disabled_for_skip(mocker):
    sel = mocker.patch("maestra_ai.core.init.questionary.select")
    sel.return_value.ask.return_value = "Pular tudo, configurar depois com 'maestra config external'"
    result = _prompt_external_sources_optin()
    assert result["musicbrainz"]["enabled"] is False
    assert result["reccobeats"]["enabled"] is False
    assert result["lastfm"]["enabled"] is False
    assert "getsongbpm" not in result


def test_prompt_returns_all_disabled_for_none(mocker):
    """None retornado pelo questionary (Ctrl-C) = pular."""
    sel = mocker.patch("maestra_ai.core.init.questionary.select")
    sel.return_value.ask.return_value = None
    result = _prompt_external_sources_optin()
    assert result["musicbrainz"]["enabled"] is False
    assert result["reccobeats"]["enabled"] is False
    assert result["lastfm"]["enabled"] is False
    assert "getsongbpm" not in result


def test_state_c_offers_migration_when_external_flag_absent(monkeypatch, tmp_path):
    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path / "config" / "maestra"))
    (tmp_path / "config" / "maestra").mkdir(parents=True)
    (tmp_path / "config" / "maestra" / "config.json").write_text(json.dumps({
        "client_id": "x", "client_secret": "y", "redirect_uri": "z",
    }))
    from maestra_ai.core.init import _state_c_should_offer_external
    assert _state_c_should_offer_external() is True


def test_state_c_does_not_offer_when_already_decided(tmp_path, monkeypatch):
    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path / "config" / "maestra"))
    (tmp_path / "config" / "maestra").mkdir(parents=True)
    (tmp_path / "config" / "maestra" / "config.json").write_text(json.dumps({
        "client_id": "x", "client_secret": "y", "redirect_uri": "z",
        "external_sources_enabled": False,
    }))
    from maestra_ai.core.init import _state_c_should_offer_external
    assert _state_c_should_offer_external() is False
