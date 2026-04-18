"""SpotifyController — wrapper da API Spotify via spotipy."""
import os
import subprocess
import time
import spotipy
from spotipy.cache_handler import CacheHandler
from spotipy.exceptions import SpotifyOauthError
from spotipy.oauth2 import SpotifyOAuth

from maestra_ai.core.errors import AuthError, RateLimitError, SpotifyAPIError
from maestra_ai.core.ratelimit import PersistentCircuitBreaker, PersistentTokenBucket
from maestra_ai.core.storage import read_config, state_dir


def _ratelimit_db_path() -> str:
    return str(state_dir() / "ratelimit.db")


# Singletons compartilhados entre daemon (director run) e CLI manual via SQLite.
# Preguiçosos para respeitar MAESTRA_STATE_DIR setado em testes via monkeypatch.
_bucket: PersistentTokenBucket | None = None
_breaker: PersistentCircuitBreaker | None = None


def _get_bucket() -> PersistentTokenBucket:
    global _bucket
    if _bucket is None:
        _bucket = PersistentTokenBucket(
            capacity=60, refill_per_sec=1.0, db_path=_ratelimit_db_path()
        )
    return _bucket


def _get_breaker() -> PersistentCircuitBreaker:
    global _breaker
    if _breaker is None:
        _breaker = PersistentCircuitBreaker(
            max_failures=3, window_sec=60, cooldown_sec=300, db_path=_ratelimit_db_path()
        )
    return _breaker


def _call_spotify(fn, *args, **kwargs):
    """Chama função do spotipy com rate limit + circuit breaker."""
    bucket = _get_bucket()
    breaker = _get_breaker()
    if not breaker.allow():
        raise RateLimitError("Circuit breaker aberto; tente em ~5min.")
    if not bucket.wait_and_acquire(timeout=10.0):
        raise RateLimitError("Rate bucket esgotado (timeout local).")
    try:
        result = fn(*args, **kwargs)
        breaker.record_success()
        return result
    except SpotifyOauthError as e:
        # Refresh token inválido, client_id mismatch, credenciais revogadas:
        # orientar usuário a re-autenticar em vez de propagar traceback cru.
        raise AuthError(
            f"Falha de OAuth: {e}. Rode `maestra auth login` para re-autenticar.",
        ) from e
    except Exception as e:
        status = getattr(e, "http_status", None)
        if status == 429:
            retry_after = int(getattr(e, "headers", {}).get("Retry-After", "1"))
            breaker.record_failure()
            raise RateLimitError(str(e), retry_after=retry_after) from e
        if status in (500, 502, 503, 504):
            breaker.record_failure()
            raise SpotifyAPIError(str(e), status=status) from e
        if status == 401:
            raise AuthError(str(e)) from e
        raise


SPOTIFY_SEARCH_PAGE_LIMIT = 10


class _InMemoryCacheHandler(CacheHandler):
    """CacheHandler que injeta o refresh_token no spotipy sem I/O.

    spotipy usa CacheHandler para ler/escrever token_info (access_token,
    refresh_token, expires_at, scope). Escrever em disco conflita com a
    persistência via TokenStore — aqui apenas mantemos em memória.

    O dict precisa incluir `expires_at` (=0 força refresh imediato) e
    `scope` (casa com DEFAULT_SCOPES para passar `validate_token` do
    spotipy). Sem esses campos, spotipy descarta o cache e cai em fluxo
    OAuth interativo — que falha em ambiente não-TTY (EOFError).
    """

    def __init__(self, refresh_token: str | None = None, scope: str = ""):
        if refresh_token:
            self._token_info: dict | None = {
                "refresh_token": refresh_token,
                "access_token": "",
                "expires_at": 0,  # força spotipy a chamar refresh_access_token
                "scope": scope,
            }
        else:
            self._token_info = None

    def get_cached_token(self):
        return self._token_info

    def save_token_to_cache(self, token_info):
        self._token_info = token_info


class SpotifyController:
    """Encapsula a API do Spotify. Métodos retornam dicts, sem I/O."""

    DEFAULT_SCOPES = (
        "user-read-playback-state",
        "user-modify-playback-state",
        "playlist-modify-private",
        "playlist-read-private",
        "user-top-read",
        "user-read-recently-played",
        "user-library-read",
    )

    def __init__(self, sp=None, auth_manager=None, token_store=None):
        """Instancia o controller.

        DI via `sp` (spotipy.Spotify pré-pronto), `auth_manager` (SpotifyOAuth
        custom) ou `token_store` (backend de refresh_token). Quando todos são
        None, lê credenciais via `storage.read_config()` e refresh_token via
        `default_token_store()`, injetando no spotipy por
        `_InMemoryCacheHandler` (sem escrever cache em disco).
        """
        if sp is not None:
            self.sp = sp
            return
        if auth_manager is None:
            cfg = read_config()
            from maestra_ai.core.token_store import default_token_store
            store = token_store or default_token_store()
            refresh_token = store.load()
            scope = " ".join(self.DEFAULT_SCOPES)
            auth_manager = SpotifyOAuth(
                client_id=cfg.get("client_id"),
                client_secret=cfg.get("client_secret"),
                redirect_uri=cfg.get("redirect_uri"),
                scope=scope,
                open_browser=False,
                cache_handler=_InMemoryCacheHandler(refresh_token, scope=scope),
            )
        self.sp = spotipy.Spotify(auth_manager=auth_manager)

    def ensure_active_device(self):
        """Garante que há um dispositivo ativo. Retorna o device_id ou levanta erro.

        Sequência:
        1. Verifica se o processo do Spotify está rodando
        2. Busca dispositivos disponíveis
        3. Se nenhum está ativo, faz transfer_playback pro primeiro
        4. Aguarda o dispositivo ficar pronto
        """
        # 1. Processo rodando?
        result = subprocess.run(["pgrep", "-x", "spotify"], capture_output=True)
        if result.returncode != 0:
            raise RuntimeError("Processo do Spotify não encontrado. Abra o Spotify primeiro.")

        # 2. Dispositivos disponíveis?
        devs = _call_spotify(self.sp.devices).get("devices", [])
        if not devs:
            raise RuntimeError("Spotify aberto mas nenhum dispositivo visível na API. Aguarde alguns segundos e tente novamente.")

        # 3. Já tem algum ativo?
        active = [d for d in devs if d["is_active"]]
        if active:
            return active[0]["id"]

        # 4. Ativa o primeiro dispositivo disponível
        device_id = devs[0]["id"]
        _call_spotify(self.sp.transfer_playback, device_id, force_play=False)

        # 5. Aguarda o dispositivo aceitar comandos (até 5s)
        for _ in range(5):
            time.sleep(1)
            devs = _call_spotify(self.sp.devices).get("devices", [])
            active = [d for d in devs if d["is_active"]]
            if active:
                return active[0]["id"]

        raise RuntimeError("Dispositivo transferido mas não ficou ativo a tempo.")

    def now(self):
        """Retorna info da faixa atual ou None se nada toca."""
        pb = _call_spotify(self.sp.current_playback)
        if not pb or not pb.get("item"):
            return None
        track = pb["item"]
        return {
            "track": track["name"],
            "artist": track["artists"][0]["name"],
            "album": track["album"]["name"],
            "uri": track["uri"],
            "is_playing": pb["is_playing"],
            "device": pb["device"]["name"],
            "progress_ms": pb.get("progress_ms"),
            "duration_ms": track.get("duration_ms"),
        }

    def devices(self):
        """Retorna lista de dispositivos disponíveis."""
        result = _call_spotify(self.sp.devices)
        return [
            {
                "name": d["name"],
                "id": d["id"],
                "type": d["type"],
                "active": d["is_active"],
            }
            for d in result["devices"]
        ]

    def play(self, uri=None):
        """Toca URI (track, album, playlist) ou resume playback atual."""
        if uri is None:
            _call_spotify(self.sp.start_playback)
        elif uri.startswith("spotify:track:"):
            _call_spotify(self.sp.start_playback, uris=[uri])
        else:
            _call_spotify(self.sp.start_playback, context_uri=uri)

    def pause(self):
        """Pausa o playback atual."""
        _call_spotify(self.sp.pause_playback)

    def next_track(self):
        """Pula pra próxima faixa."""
        _call_spotify(self.sp.next_track)

    def queue_list(self):
        """Retorna faixa atual e fila."""
        raw = _call_spotify(self.sp.queue)
        current = raw.get("currently_playing")
        return {
            "current": self._track_summary(current) if current else None,
            "queue": [self._track_summary(t) for t in raw.get("queue", [])],
        }

    def queue_add(self, uri):
        """Adiciona uma faixa à fila."""
        _call_spotify(self.sp.add_to_queue, uri)

    def search(self, query, type="track", limit=10, offset=0):
        """Busca no Spotify. Retorna lista de resultados formatados."""
        items = []
        remaining = limit
        current_offset = offset

        while remaining > 0:
            page_limit = min(remaining, SPOTIFY_SEARCH_PAGE_LIMIT)
            raw = _call_spotify(self.sp.search, q=query, type=type, limit=page_limit, offset=current_offset)
            page_items = self._search_items(raw, type)
            if not page_items:
                break
            items.extend(page_items)
            remaining -= len(page_items)
            current_offset += len(page_items)
            if len(page_items) < page_limit:
                break

        if type == "track":
            return [
                {
                    "track": t["name"],
                    "artist": t["artists"][0]["name"],
                    "album": t["album"]["name"],
                    "uri": t["uri"],
                }
                for t in items
            ]
        elif type == "artist":
            return [
                {
                    "name": a["name"],
                    "uri": a["uri"],
                    "genres": a.get("genres", []),
                }
                for a in items
            ]
        elif type == "album":
            return [
                {
                    "name": a["name"],
                    "artist": a["artists"][0]["name"],
                    "uri": a["uri"],
                }
                for a in items
            ]
        return []

    @staticmethod
    def _search_items(raw, type):
        """Extrai lista de itens do payload de busca."""
        if type == "track":
            return raw.get("tracks", {}).get("items", [])
        if type == "artist":
            return raw.get("artists", {}).get("items", [])
        if type == "album":
            return raw.get("albums", {}).get("items", [])
        return []

    def recently_played(self, limit=50):
        """Retorna faixas tocadas recentemente."""
        raw = _call_spotify(self.sp.current_user_recently_played, limit=limit)
        results = []
        for item in raw.get("items", []):
            track = item.get("track")
            if track and track.get("name"):
                summary = self._track_summary(track)
                summary["played_at"] = item.get("played_at")
                results.append(summary)
        return results

    def top_tracks(self, time_range="medium_term", limit=20):
        """Retorna top faixas do usuário."""
        raw = _call_spotify(self.sp.current_user_top_tracks, time_range=time_range, limit=limit)
        return [
            {
                "track": t["name"],
                "artist": t["artists"][0]["name"],
                "album": t["album"]["name"],
                "uri": t["uri"],
            }
            for t in raw.get("items", [])
        ]

    def top_artists(self, time_range="medium_term", limit=20):
        """Retorna top artistas do usuário."""
        raw = _call_spotify(self.sp.current_user_top_artists, time_range=time_range, limit=limit)
        return [
            {
                "name": a["name"],
                "uri": a["uri"],
                "genres": a.get("genres", []),
            }
            for a in raw.get("items", [])
        ]

    def playlist_tracks(self, playlist_id):
        """Retorna todas as faixas de uma playlist (com paginação)."""
        results = []
        offset = 0
        limit = 50
        while True:
            raw = _call_spotify(self.sp.playlist_items, playlist_id, offset=offset, limit=limit)
            for item in raw["items"]:
                # A API retorna o track em "track" ou "item" dependendo da versão
                track_data = item.get("track") or item.get("item")
                if track_data and track_data.get("name"):
                    results.append(self._track_summary(track_data))
            if raw.get("next") is None:
                break
            offset += limit
        return results

    def playlist_add(self, playlist_id, uris):
        """Adiciona faixas a uma playlist."""
        _call_spotify(self.sp.playlist_add_items, playlist_id, uris)

    def playlist_remove(self, playlist_id, uris):
        """Remove faixas de uma playlist."""
        _call_spotify(self.sp.playlist_remove_all_occurrences_of_items, playlist_id, uris)

    @staticmethod
    def _track_summary(track):
        """Extrai resumo de uma faixa."""
        return {
            "track": track["name"],
            "artist": track["artists"][0]["name"],
            "uri": track["uri"],
        }
