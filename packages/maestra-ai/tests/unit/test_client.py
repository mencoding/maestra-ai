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
