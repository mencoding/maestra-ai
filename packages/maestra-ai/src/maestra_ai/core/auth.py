"""Fluxo OAuth Spotify — setup de credenciais e login via paste-back.

Política Spotify (>2025) rejeita redirect URIs `localhost`/`127.0.0.1` em
apps novos. Em vez de spinner + servidor HTTP local, usamos fluxo
paste-back: abrimos o navegador (best-effort), imprimimos a URL sempre,
e o usuário cola de volta a URL de redirect. O `code` é extraído e
trocado por `refresh_token`, persistido via `TokenStore`.
"""
from __future__ import annotations

import webbrowser
from collections.abc import Callable

from spotipy.cache_handler import CacheHandler
from spotipy.oauth2 import SpotifyOAuth

from maestra_ai.core import storage
from maestra_ai.core.errors import AuthError, ConfigError
from maestra_ai.core.token_store import default_token_store

SCOPES = " ".join([
    "user-read-playback-state",
    "user-modify-playback-state",
    "user-read-recently-played",
    "user-top-read",
    "user-library-read",
    "playlist-modify-public",
    "playlist-modify-private",
    "playlist-read-private",
])


class _NoopCacheHandler(CacheHandler):
    """Impede spotipy de ler/escrever cache em disco durante login.

    Persistência é feita via TokenStore depois do get_access_token.
    Precisa herdar CacheHandler: spotipy 2.26+ faz `issubclass` no
    `SpotifyOAuth.__init__` e crasha com AssertionError caso contrário.
    """

    def get_cached_token(self):
        return None

    def save_token_to_cache(self, token_info):
        pass


def setup(
    *,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
) -> dict:
    """Grava credenciais no config.json. Preserva campos existentes."""
    cfg = storage.read_config()
    cfg.update({
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
    })
    storage.write_config(cfg)
    return {
        "status": "ok",
        "config_path": str(storage.config_dir() / "config.json"),
    }


def login(
    *,
    pasted_url_getter: Callable[[str], str],
    browser_opener: Callable[[str], None] | None = None,
) -> dict:
    """Executa fluxo OAuth paste-back.

    Args:
        pasted_url_getter: callable que recebe a URL de autorização e
            retorna a URL de redirect colada pelo usuário (ou só o code).
            Injetado para facilitar testes e CLI wrapping.
        browser_opener: callable que tenta abrir URL no navegador default.
            Default: `webbrowser.open`. Falha silenciosa se não conseguir.

    Retorna dict com status, scopes, access_token_len.
    Levanta ConfigError se credenciais ausentes, AuthError se flow quebra.
    """
    cfg = storage.read_config()
    if not cfg.get("client_id") or not cfg.get("client_secret"):
        raise ConfigError(
            "client_id/client_secret não configurados. Rode `maestra auth setup`.",
        )
    if not cfg.get("redirect_uri"):
        raise ConfigError(
            "redirect_uri não configurado. Rode `maestra auth setup --redirect-uri <url>`.",
        )

    oauth = SpotifyOAuth(
        client_id=cfg["client_id"],
        client_secret=cfg["client_secret"],
        redirect_uri=cfg["redirect_uri"],
        scope=SCOPES,
        cache_handler=_NoopCacheHandler(),
        open_browser=False,
    )
    auth_url = oauth.get_authorize_url()

    opener = browser_opener or webbrowser.open
    try:
        opener(auth_url)
    except Exception:
        # Ambiente headless, sem display, etc. — seguimos mostrando a URL.
        pass

    pasted = pasted_url_getter(auth_url).strip()

    # parse_response_code aceita URL completa ou o code puro (retorna igual).
    code = oauth.parse_response_code(pasted)
    if not code or code == pasted and "http" in pasted:
        # Condição: ainda é URL mas sem code detectável.
        raise AuthError(
            "Code não reconhecido na URL colada. Rode `maestra auth login` de novo.",
        )

    try:
        token_info = oauth.get_access_token(code, as_dict=True, check_cache=False)
    except Exception as e:
        raise AuthError(f"Falha ao trocar code por token: {e}") from e

    refresh = token_info.get("refresh_token")
    if not refresh:
        raise AuthError(
            "OAuth completou sem refresh_token. Verifique o app Spotify.",
        )

    default_token_store().save(refresh)

    return {
        "status": "ok",
        "scopes": token_info.get("scope", ""),
        "access_token_len": len(token_info.get("access_token", "")),
    }
