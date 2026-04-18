"""HistoryAnalyzer — análise pontual do histórico Spotify."""
from collections import Counter


class HistoryAnalyzer:
    """Agrega histórico recente e top items sem alterar perfil de gosto."""

    def __init__(self, controller):
        self.controller = controller

    def analyze(self, recent_limit=50, top_limit=20):
        """Retorna análise pontual do histórico do usuário."""
        recent = self.controller.recently_played(limit=recent_limit)
        top_tracks = {
            range_name: self.controller.top_tracks(time_range=range_name, limit=top_limit)
            for range_name in ("short_term", "medium_term", "long_term")
        }
        top_artists = {
            range_name: self.controller.top_artists(time_range=range_name, limit=top_limit)
            for range_name in ("short_term", "medium_term", "long_term")
        }

        return {
            "recent": self._summarize_tracks(recent),
            "top_tracks": {
                range_name: self._summarize_tracks(tracks)
                for range_name, tracks in top_tracks.items()
            },
            "top_artists": {
                range_name: self._summarize_artists(artists)
                for range_name, artists in top_artists.items()
            },
            "suggestions": self._suggestions(recent, top_tracks, top_artists),
        }

    def outside_playlist(self, playlist_id, recent_limit=50):
        """Retorna faixas recentes que nao estao na playlist informada."""
        recent = self.controller.recently_played(limit=recent_limit)
        playlist_tracks = self.controller.playlist_tracks(playlist_id)
        playlist_uris = {track["uri"] for track in playlist_tracks}

        outside = []
        by_uri = {}
        for track in recent:
            uri = track["uri"]
            if uri in playlist_uris:
                continue
            if uri not in by_uri:
                item = {
                    **track,
                    "plays": 0,
                    "played_at_events": [],
                }
                by_uri[uri] = item
                outside.append(item)
            by_uri[uri]["plays"] += 1
            if track.get("played_at"):
                by_uri[uri]["played_at_events"].append(track["played_at"])

        return {
            "recent_count": len(recent),
            "playlist_count": len(playlist_tracks),
            "outside_count": len(outside),
            "outside_play_events": sum(track["plays"] for track in outside),
            "top_outside_artists": [
                {"artist": artist, "count": count}
                for artist, count in Counter(
                    track["artist"]
                    for track in outside
                    for _ in range(track["plays"])
                ).most_common(10)
            ],
            "top_outside_tracks": [
                {"track": track, "artist": artist, "count": count}
                for (track, artist), count in Counter(
                    (track["track"], track["artist"])
                    for track in outside
                    for _ in range(track["plays"])
                ).most_common(10)
            ],
            "tracks": outside,
            "candidates": self._outside_candidates(outside),
            "note": "Leitura apenas; nenhum feedback foi gravado.",
        }

    def _outside_candidates(self, tracks):
        """Ordena faixas fora da playlist para possível incorporação."""
        return sorted(
            tracks,
            key=lambda track: (
                track["plays"],
                max(track.get("played_at_events") or [""]),
            ),
            reverse=True,
        )

    def _summarize_tracks(self, tracks):
        artist_counts = Counter(t["artist"] for t in tracks)
        track_counts = Counter((t["track"], t["artist"]) for t in tracks)
        return {
            "count": len(tracks),
            "top_artists": [
                {"artist": artist, "count": count}
                for artist, count in artist_counts.most_common(10)
            ],
            "top_tracks": [
                {"track": track, "artist": artist, "count": count}
                for (track, artist), count in track_counts.most_common(10)
            ],
            "items": tracks,
        }

    def _summarize_artists(self, artists):
        genres = Counter(
            genre
            for artist in artists
            for genre in artist.get("genres", [])
        )
        return {
            "count": len(artists),
            "top_genres": [
                {"genre": genre, "count": count}
                for genre, count in genres.most_common(15)
            ],
            "items": artists,
        }

    def _suggestions(self, recent, top_tracks, top_artists):
        artist_counts = Counter(t["artist"] for t in recent)
        for tracks in top_tracks.values():
            artist_counts.update(t["artist"] for t in tracks)

        genre_counts = Counter()
        for artists in top_artists.values():
            for artist in artists:
                genre_counts.update(artist.get("genres", []))

        return {
            "preferred_artists_candidates": [
                artist for artist, _ in artist_counts.most_common(15)
            ],
            "genre_candidates": [
                genre for genre, _ in genre_counts.most_common(15)
            ],
            "context_query_candidates": self._context_query_candidates(genre_counts),
        }

    def import_outside(
        self,
        *,
        playlist_id,
        context,
        confirm=False,
        count=10,
        min_plays=2,
        recent_limit=50,
        taste=None,
    ):
        """Importa faixas ouvidas recentemente fora da playlist.

        Dry-run por default (confirm=False): retorna apenas candidatos,
        sem alterar playlist nem gosto. Com confirm=True: cria snapshot,
        adiciona à playlist e registra sinais contextuais positivos
        (se `taste` for fornecido).

        Filtros aplicados:
        - faixa não pode estar na playlist;
        - mínimo de reproduções recentes (min_plays);
        - se `taste` for fornecido, `context_score(uri, context)` deve
          ser não-negativo (ignora faixas com sinal contextual negativo).
        """
        from maestra_ai.core import snapshot

        analysis = self.outside_playlist(playlist_id, recent_limit=recent_limit)
        candidates = []
        for track in analysis.get("candidates", []):
            if track.get("plays", 0) < min_plays:
                continue
            if taste is not None and taste.context_score(track["uri"], context) < 0:
                continue
            candidates.append({
                "uri": track["uri"],
                "track": track.get("track", ""),
                "artist": track.get("artist", ""),
                "plays": track.get("plays", 0),
            })
            if len(candidates) >= count:
                break

        if not confirm:
            return {
                "dry_run": True,
                "context": context,
                "candidates": candidates,
                "total_candidates": len(candidates),
                "imported": 0,
            }

        # Snapshot automático antes da mutação
        playlist_tracks = self.controller.playlist_tracks(playlist_id)
        snap_id = snapshot.create(
            "import_outside",
            {"playlist_id": playlist_id, "context": context, "playlist_tracks": playlist_tracks},
        )

        uris = [c["uri"] for c in candidates]
        if uris:
            self.controller.playlist_add(playlist_id, uris)
            if taste is not None:
                for c in candidates:
                    event_id = f"outside-playlist-auto-safe:{context}:{c['uri']}"
                    taste.record_context_signal(
                        c["uri"],
                        "good",
                        context,
                        source="outside_playlist_auto_safe",
                        event_id=event_id,
                        weight=1,
                    )

        return {
            "dry_run": False,
            "context": context,
            "candidates": candidates,
            "imported": len(uris),
            "snapshot_id": snap_id,
            "uris_imported": uris,
        }

    def _context_query_candidates(self, genre_counts):
        genres = [genre for genre, _ in genre_counts.most_common(20)]
        return {
            "foco": [
                genre for genre in genres
                if any(token in genre for token in ("ambient", "instrumental", "soundtrack", "classical", "piano"))
            ][:8],
            "energia": [
                genre for genre in genres
                if any(token in genre for token in ("metal", "rock", "epic", "industrial", "electronic"))
            ][:8],
        }
