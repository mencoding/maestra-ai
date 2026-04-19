"""Testes do SpotifyController — foco em DI e rate limit.

P1-4: construtor aceita `sp` (spotipy.Spotify pré-configurado) ou
`auth_manager` (SpotifyOAuth/outro) via DI, sem passar pelo OAuth
default. Pré-requisito para Fase 3 e para testes que não podem
depender de credenciais reais.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from maestra_ai.core.client import SpotifyController


class TestEnsureActiveDeviceError:
    """v0.5.5 #1: ensure_active_device levanta DeviceError (MaestraError),
    não RuntimeError. Contrato: probable_causes e suggested_actions
    padronizados."""

    def test_spotify_nao_rodando_levanta_device_error(self, monkeypatch):
        from maestra_ai.core.errors import DeviceError, MaestraError
        monkeypatch.setattr(
            "maestra_ai.core.process.is_spotify_running", lambda: False,
        )
        sp = MagicMock()
        controller = SpotifyController(sp=sp)
        with pytest.raises(DeviceError) as exc:
            controller.ensure_active_device()
        assert isinstance(exc.value, MaestraError)
        err = exc.value.to_human_dict()
        assert err["title"] == "Nenhum dispositivo Spotify ativo"
        assert err["probable_causes"]  # não vazia

    def test_sem_dispositivos_disponiveis_levanta_device_error(self, monkeypatch):
        from maestra_ai.core.errors import DeviceError
        monkeypatch.setattr(
            "maestra_ai.core.process.is_spotify_running", lambda: True,
        )
        sp = MagicMock()
        sp.devices.return_value = {"devices": []}
        controller = SpotifyController(sp=sp)
        with pytest.raises(DeviceError):
            controller.ensure_active_device()

    def test_transferencia_nao_completa_levanta_device_error(self, monkeypatch):
        from maestra_ai.core.errors import DeviceError
        monkeypatch.setattr(
            "maestra_ai.core.process.is_spotify_running", lambda: True,
        )
        monkeypatch.setattr("time.sleep", lambda *_: None)  # acelera o teste
        sp = MagicMock()
        sp.devices.return_value = {
            "devices": [{"id": "d1", "is_active": False}],
        }
        controller = SpotifyController(sp=sp)
        with pytest.raises(DeviceError):
            controller.ensure_active_device()


def test_di_com_sp_pronto_nao_instancia_oauth():
    """Com sp injetado, controller usa direto — não toca SpotifyOAuth."""
    sp = MagicMock()
    controller = SpotifyController(sp=sp)
    assert controller.sp is sp


def test_di_com_auth_manager_custom_passa_para_spotipy(monkeypatch):
    """Com auth_manager injetado, spotipy.Spotify recebe-o; não cria OAuth default."""
    captured = {}

    class FakeSpotify:
        def __init__(self, auth_manager=None):
            captured["auth_manager"] = auth_manager

    monkeypatch.setattr("maestra_ai.core.client.spotipy.Spotify", FakeSpotify)

    fake_auth = object()
    controller = SpotifyController(auth_manager=fake_auth)
    assert captured["auth_manager"] is fake_auth
    assert isinstance(controller.sp, FakeSpotify)


def test_di_token_store_injetado_popula_cache_handler(monkeypatch, tmp_path):
    """TokenStore injetado fornece refresh_token que vai pro cache_handler do OAuth."""
    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
    # Config mínimo para SpotifyOAuth não explodir
    from maestra_ai.core import storage
    storage.write_config({
        "client_id": "cid",
        "client_secret": "csec",
        "redirect_uri": "https://example.com/cb",
    })

    mock_store = MagicMock()
    mock_store.load.return_value = "rt_injected"

    captured = {}

    class FakeSpotify:
        def __init__(self, auth_manager=None):
            captured["auth_manager"] = auth_manager

    monkeypatch.setattr("maestra_ai.core.client.spotipy.Spotify", FakeSpotify)

    SpotifyController(token_store=mock_store)
    # O auth_manager recebido é um SpotifyOAuth com cache_handler que tem o refresh_token
    oauth = captured["auth_manager"]
    cached = oauth.cache_handler.get_cached_token()
    assert cached["refresh_token"] == "rt_injected"


def test_cache_handler_tem_expires_at_zero_para_forcar_refresh(monkeypatch, tmp_path):
    """P0: v0.3.0 populava só {'refresh_token': ...} — spotipy descarta e
    cai em fluxo OAuth interativo (EOFError em ambiente não-TTY).

    Cache handler precisa ter expires_at + scope para `validate_token()`
    do spotipy reconhecer como expired (e chamar refresh_access_token)
    em vez de solicitar auth interativa.
    """
    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
    from maestra_ai.core import storage
    storage.write_config({
        "client_id": "cid", "client_secret": "sec",
        "redirect_uri": "https://example.com/cb",
    })

    mock_store = MagicMock()
    mock_store.load.return_value = "rt_valid"

    captured = {}

    class FakeSpotify:
        def __init__(self, auth_manager=None):
            captured["auth_manager"] = auth_manager

    monkeypatch.setattr("maestra_ai.core.client.spotipy.Spotify", FakeSpotify)

    SpotifyController(token_store=mock_store)
    cached = captured["auth_manager"].cache_handler.get_cached_token()

    assert cached is not None
    assert cached["refresh_token"] == "rt_valid"
    # Crítico: expires_at=0 força spotipy a chamar refresh_access_token
    assert "expires_at" in cached
    assert cached["expires_at"] == 0
    # Scope deve casar com DEFAULT_SCOPES do controller para passar _is_scope_subset
    assert "scope" in cached
    assert all(s in cached["scope"] for s in SpotifyController.DEFAULT_SCOPES)


def test_spotify_oauth_error_vira_auth_error(monkeypatch):
    """SpotifyOauthError (refresh token invalido, client mismatch) deve
    virar AuthError com mensagem humana, nao traceback cru."""
    from spotipy.exceptions import SpotifyOauthError

    from maestra_ai.core.client import _call_spotify
    from maestra_ai.core.errors import AuthError

    def failing_call():
        raise SpotifyOauthError(
            "error: invalid_grant, error_description: Invalid refresh token",
        )

    # Patch bucket e breaker para nao interferir
    import maestra_ai.core.client as client_mod
    monkeypatch.setattr(client_mod, "_get_bucket", lambda: MagicMock(
        wait_and_acquire=lambda timeout=10.0: True,
    ))
    monkeypatch.setattr(client_mod, "_get_breaker", lambda: MagicMock(
        allow=lambda: True,
    ))

    with pytest.raises(AuthError):
        _call_spotify(failing_call)


def test_cache_handler_ausente_quando_sem_refresh_token(monkeypatch, tmp_path):
    """Se TokenStore não tem refresh_token, get_cached_token retorna None
    (spotipy fará fluxo interativo normal — caller deve rodar auth login).
    """
    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
    from maestra_ai.core import storage
    storage.write_config({
        "client_id": "cid", "client_secret": "sec",
        "redirect_uri": "https://example.com/cb",
    })

    mock_store = MagicMock()
    mock_store.load.return_value = None

    captured = {}

    class FakeSpotify:
        def __init__(self, auth_manager=None):
            captured["auth_manager"] = auth_manager

    monkeypatch.setattr("maestra_ai.core.client.spotipy.Spotify", FakeSpotify)

    SpotifyController(token_store=mock_store)
    assert captured["auth_manager"].cache_handler.get_cached_token() is None


def test_sem_dotenv_nao_lido_apenas_read_config(monkeypatch, tmp_path):
    """Remove dependência de .env legado — credenciais só via storage.read_config."""
    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
    # Existência de .env NÃO deve ser lida — só config.json
    (tmp_path / ".env").write_text("SPOTIFY_CLIENT_ID=never_read\n", encoding="utf-8")
    from maestra_ai.core import storage
    storage.write_config({
        "client_id": "from_config",
        "client_secret": "sec",
        "redirect_uri": "https://example.com/cb",
    })

    captured = {}

    class FakeSpotify:
        def __init__(self, auth_manager=None):
            captured["auth_manager"] = auth_manager

    monkeypatch.setattr("maestra_ai.core.client.spotipy.Spotify", FakeSpotify)

    SpotifyController()
    assert captured["auth_manager"].client_id == "from_config"


def test_client_now_tolera_track_sem_artists(monkeypatch):
    """CRITICAL-4: payload degradado onde track['artists'] é [] não deve crashar.
    Antes: IndexError em track['artists'][0]."""
    sp = MagicMock()
    sp.current_playback.return_value = {
        "is_playing": True,
        "item": {
            "name": "Faixa",
            "artists": [],  # vazio
            "album": {"name": "Album"},
            "uri": "spotify:track:x",
            "duration_ms": 1000,
        },
        "device": {"name": "dev"},
        "progress_ms": 500,
    }
    import maestra_ai.core.client as client_mod
    monkeypatch.setattr(client_mod, "_get_bucket", lambda: MagicMock(
        wait_and_acquire=lambda timeout=10.0: True,
    ))
    monkeypatch.setattr(client_mod, "_get_breaker", lambda: MagicMock(
        allow=lambda: True, record_success=lambda: None,
    ))
    controller = SpotifyController(sp=sp)
    result = controller.now()
    assert result is not None
    assert result["track"] == "Faixa"
    # Artista fallback não explode
    assert "artist" in result


def test_playlist_tracks_filtra_track_none(monkeypatch):
    """playlist_items pode ter items com track=None (faixa removida)."""
    sp = MagicMock()
    sp.playlist_items.return_value = {
        "items": [
            {"track": None},
            {"track": {
                "name": "OK", "artists": [{"name": "A"}],
                "uri": "spotify:track:ok",
            }},
        ],
        "next": None,
    }
    import maestra_ai.core.client as client_mod
    monkeypatch.setattr(client_mod, "_get_bucket", lambda: MagicMock(
        wait_and_acquire=lambda timeout=10.0: True,
    ))
    monkeypatch.setattr(client_mod, "_get_breaker", lambda: MagicMock(
        allow=lambda: True, record_success=lambda: None,
    ))
    controller = SpotifyController(sp=sp)
    tracks = controller.playlist_tracks("pl")
    assert len(tracks) == 1
    assert tracks[0]["track"] == "OK"
