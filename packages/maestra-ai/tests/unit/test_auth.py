"""Testes do fluxo auth — setup grava config, login obtém token via paste-back."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from maestra_ai.core import auth, storage
from maestra_ai.core.errors import AuthError, ConfigError, NonInteractiveError


class TestScopes:
    """v0.5.2: SCOPES inclui user-read-email e user-read-private — sem
    eles, /v1/me retorna email/country/product como None, inviabilizando
    diagnósticos inteligentes no doctor."""

    def test_scopes_incluem_user_read_email(self):
        from maestra_ai.core.auth import SCOPES
        assert "user-read-email" in SCOPES

    def test_scopes_incluem_user_read_private(self):
        from maestra_ai.core.auth import SCOPES
        assert "user-read-private" in SCOPES


class TestAuthSetupCLINonTTY:
    """_handle_setup sem args e sem stdin-TTY → erro de categoria
    apropriada (NonInteractiveError), não 'Argumento inválido'."""

    def test_levanta_non_interactive_error_com_title_claro(self, monkeypatch):
        """Mensagem do painel deve ajudar, não falar em 'flag fora do range'."""
        from argparse import Namespace

        from maestra_ai.cli.auth import _handle_setup

        monkeypatch.setattr("sys.stdin.isatty", lambda: False)

        args = Namespace(
            client_id=None, client_secret=None, redirect_uri=None, json=False,
        )
        with pytest.raises(NonInteractiveError) as exc:
            _handle_setup(args)

        err = exc.value.to_human_dict()
        # Title não deve mais ser "Argumento inválido".
        assert err["title"] != "Argumento inválido"
        # Causes devem mencionar TTY/script/pipe, não "flag fora do range".
        joined_causes = " ".join(err["probable_causes"]).lower()
        assert "tty" in joined_causes or "interativ" in joined_causes \
               or "script" in joined_causes or "pipe" in joined_causes
        # Sugere o comando correto.
        actions_text = " ".join(a["command"] for a in err["suggested_actions"])
        assert "--client-id" in actions_text or "maestra auth setup" in actions_text


class TestAuthSetup:
    def test_setup_grava_credenciais_no_config(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
        auth.setup(
            client_id="cid_abc",
            client_secret="sec_xyz",
            redirect_uri="https://example.com/callback",
        )
        cfg = storage.read_config()
        assert cfg["client_id"] == "cid_abc"
        assert cfg["client_secret"] == "sec_xyz"
        assert cfg["redirect_uri"] == "https://example.com/callback"

    def test_setup_preserva_campos_existentes(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
        storage.write_config({"playlist_id": "pl_123", "other": "val"})
        auth.setup(client_id="a", client_secret="b", redirect_uri="https://x/cb")
        cfg = storage.read_config()
        assert cfg["playlist_id"] == "pl_123"
        assert cfg["other"] == "val"
        assert cfg["client_id"] == "a"


class TestNoopCacheHandler:
    def test_e_subclasse_de_spotipy_cache_handler(self):
        """v0.3.0/v0.3.1: _NoopCacheHandler não herdava CacheHandler,
        spotipy 2.26+ falhava com AssertionError em SpotifyOAuth.__init__.
        """
        from spotipy.cache_handler import CacheHandler

        from maestra_ai.core.auth import _NoopCacheHandler
        assert issubclass(_NoopCacheHandler, CacheHandler)

    def test_spotify_oauth_aceita_noop_handler(self):
        """Smoke: SpotifyOAuth real aceita o _NoopCacheHandler sem
        mockar nada. Teste fecha o gap de cobertura da v0.3.0."""
        from spotipy.oauth2 import SpotifyOAuth

        from maestra_ai.core.auth import SCOPES, _NoopCacheHandler
        # Não chama Spotify; só testa que __init__ não crasha no assert.
        oauth = SpotifyOAuth(
            client_id="cid",
            client_secret="sec",
            redirect_uri="https://example.com/cb",
            scope=SCOPES,
            cache_handler=_NoopCacheHandler(),
            open_browser=False,
        )
        assert oauth.cache_handler.get_cached_token() is None


class TestAuthLogin:
    def _write_config(self, tmp_path):
        storage.write_config({
            "client_id": "cid",
            "client_secret": "sec",
            "redirect_uri": "https://example.com/cb",
        })

    def test_login_sem_config_levanta_config_error(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
        with pytest.raises(ConfigError):
            auth.login(pasted_url_getter=lambda url: "dummy")

    def test_login_paste_back_extrai_code_e_persiste(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
        self._write_config(tmp_path)

        mock_oauth = MagicMock()
        mock_oauth.get_authorize_url.return_value = "https://accounts.spotify.com/authorize?state=S1"
        mock_oauth.parse_response_code.return_value = "CODE_ABC"
        mock_oauth.get_access_token.return_value = {
            "access_token": "at_123",
            "refresh_token": "rt_persisted",
            "scope": "user-read-playback-state",
        }

        mock_store = MagicMock()

        with patch("maestra_ai.core.auth.SpotifyOAuth", return_value=mock_oauth), \
             patch("maestra_ai.core.auth.default_token_store", return_value=mock_store):
            result = auth.login(
                pasted_url_getter=lambda url: "https://example.com/cb?code=CODE_ABC&state=S1",
                browser_opener=lambda url: None,  # noop
            )

        assert result["status"] == "ok"
        mock_oauth.parse_response_code.assert_called_once()
        mock_store.save.assert_called_once_with("rt_persisted")

    def test_login_token_sem_refresh_levanta_auth_error(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
        self._write_config(tmp_path)

        mock_oauth = MagicMock()
        mock_oauth.get_authorize_url.return_value = "https://x/auth"
        mock_oauth.parse_response_code.return_value = "CODE"
        mock_oauth.get_access_token.return_value = {
            "access_token": "at",
            "scope": "scope",
        }  # sem refresh_token

        with patch("maestra_ai.core.auth.SpotifyOAuth", return_value=mock_oauth), \
             patch("maestra_ai.core.auth.default_token_store"):
            with pytest.raises(AuthError):
                auth.login(
                    pasted_url_getter=lambda url: "https://x/cb?code=C",
                    browser_opener=lambda url: None,
                )

    def test_login_code_invalido_levanta_auth_error(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
        self._write_config(tmp_path)

        mock_oauth = MagicMock()
        mock_oauth.get_authorize_url.return_value = "https://x/auth"
        mock_oauth.parse_response_code.return_value = None  # spotipy retorna None em URL sem code

        with patch("maestra_ai.core.auth.SpotifyOAuth", return_value=mock_oauth):
            with pytest.raises(AuthError):
                auth.login(
                    pasted_url_getter=lambda url: "https://x/cb?erro=oops",
                    browser_opener=lambda url: None,
                )

    def test_login_aceita_code_puro_sem_url(self, monkeypatch, tmp_path):
        """Usuário pode colar só o code em vez da URL inteira."""
        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
        self._write_config(tmp_path)

        mock_oauth = MagicMock()
        mock_oauth.get_authorize_url.return_value = "https://x/auth"
        # spotipy parse_response_code retorna URL intacta se não encontrar padrão
        mock_oauth.parse_response_code.return_value = "CODE_PURO"
        mock_oauth.get_access_token.return_value = {
            "access_token": "at",
            "refresh_token": "rt",
            "scope": "s",
        }

        mock_store = MagicMock()
        with patch("maestra_ai.core.auth.SpotifyOAuth", return_value=mock_oauth), \
             patch("maestra_ai.core.auth.default_token_store", return_value=mock_store):
            result = auth.login(
                pasted_url_getter=lambda url: "CODE_PURO",
                browser_opener=lambda url: None,
            )
        assert result["status"] == "ok"

    def test_login_tenta_abrir_browser_mas_nao_falha_se_nao_conseguir(
        self, monkeypatch, tmp_path,
    ):
        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
        self._write_config(tmp_path)

        mock_oauth = MagicMock()
        mock_oauth.get_authorize_url.return_value = "https://x/auth"
        mock_oauth.parse_response_code.return_value = "CODE"
        mock_oauth.get_access_token.return_value = {
            "access_token": "at",
            "refresh_token": "rt",
            "scope": "s",
        }

        def failing_opener(url):
            raise RuntimeError("no display")

        with patch("maestra_ai.core.auth.SpotifyOAuth", return_value=mock_oauth), \
             patch("maestra_ai.core.auth.default_token_store"):
            result = auth.login(
                pasted_url_getter=lambda url: "CODE",
                browser_opener=failing_opener,
            )
        # Browser falhou mas o login foi em frente — URL impressa no stdout.
        assert result["status"] == "ok"
