"""SpotifyController — wrapper da API Spotify via spotipy."""
import os
import subprocess
import time
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv


# Diretório base do workspace (onde ficam .env e .cache)
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPOTIFY_SEARCH_PAGE_LIMIT = 10


class SpotifyController:
    """Encapsula a API do Spotify. Métodos retornam dicts, sem I/O."""

    def __init__(self):
        load_dotenv(os.path.join(_BASE_DIR, ".env"))
        scopes = [
            "user-read-playback-state",
            "user-modify-playback-state",
            "playlist-modify-private",
            "playlist-read-private",
            "user-top-read",
            "user-read-recently-played",
            "user-library-read",
        ]
        self.sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
            scope=" ".join(scopes),
            open_browser=False,
            cache_path=os.path.join(_BASE_DIR, ".cache"),
        ))

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
        devs = self.sp.devices().get("devices", [])
        if not devs:
            raise RuntimeError("Spotify aberto mas nenhum dispositivo visível na API. Aguarde alguns segundos e tente novamente.")

        # 3. Já tem algum ativo?
        active = [d for d in devs if d["is_active"]]
        if active:
            return active[0]["id"]

        # 4. Ativa o primeiro dispositivo disponível
        device_id = devs[0]["id"]
        self.sp.transfer_playback(device_id, force_play=False)

        # 5. Aguarda o dispositivo aceitar comandos (até 5s)
        for _ in range(5):
            time.sleep(1)
            devs = self.sp.devices().get("devices", [])
            active = [d for d in devs if d["is_active"]]
            if active:
                return active[0]["id"]

        raise RuntimeError("Dispositivo transferido mas não ficou ativo a tempo.")

    def now(self):
        """Retorna info da faixa atual ou None se nada toca."""
        pb = self.sp.current_playback()
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
        result = self.sp.devices()
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
            self.sp.start_playback()
        elif uri.startswith("spotify:track:"):
            self.sp.start_playback(uris=[uri])
        else:
            self.sp.start_playback(context_uri=uri)

    def pause(self):
        """Pausa o playback atual."""
        self.sp.pause_playback()

    def next_track(self):
        """Pula pra próxima faixa."""
        self.sp.next_track()

    def queue_list(self):
        """Retorna faixa atual e fila."""
        raw = self.sp.queue()
        current = raw.get("currently_playing")
        return {
            "current": self._track_summary(current) if current else None,
            "queue": [self._track_summary(t) for t in raw.get("queue", [])],
        }

    def queue_add(self, uri):
        """Adiciona uma faixa à fila."""
        self.sp.add_to_queue(uri)

    def search(self, query, type="track", limit=10, offset=0):
        """Busca no Spotify. Retorna lista de resultados formatados."""
        items = []
        remaining = limit
        current_offset = offset

        while remaining > 0:
            page_limit = min(remaining, SPOTIFY_SEARCH_PAGE_LIMIT)
            raw = self.sp.search(q=query, type=type, limit=page_limit, offset=current_offset)
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
        raw = self.sp.current_user_recently_played(limit=limit)
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
        raw = self.sp.current_user_top_tracks(time_range=time_range, limit=limit)
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
        raw = self.sp.current_user_top_artists(time_range=time_range, limit=limit)
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
            raw = self.sp.playlist_items(playlist_id, offset=offset, limit=limit)
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
        self.sp.playlist_add_items(playlist_id, uris)

    def playlist_remove(self, playlist_id, uris):
        """Remove faixas de uma playlist."""
        self.sp.playlist_remove_all_occurrences_of_items(playlist_id, uris)

    @staticmethod
    def _track_summary(track):
        """Extrai resumo de uma faixa."""
        return {
            "track": track["name"],
            "artist": track["artists"][0]["name"],
            "uri": track["uri"],
        }
