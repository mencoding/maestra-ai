"""Testes do HistoryAnalyzer."""
from unittest.mock import MagicMock

from maestra_ai.core.history import HistoryAnalyzer


def test_analyze_agrega_historico_e_sugestoes():
    controller = MagicMock()
    controller.recently_played.return_value = [
        {"track": "Wolf Totem", "artist": "The HU", "uri": "spotify:track:a"},
        {"track": "Yuve Yuve Yu", "artist": "The HU", "uri": "spotify:track:b"},
        {"track": "EMV Charon", "artist": "Guillaume David", "uri": "spotify:track:c"},
    ]
    controller.top_tracks.side_effect = [
        [{"track": "Track S", "artist": "The HU", "uri": "spotify:track:s"}],
        [{"track": "Track M", "artist": "Max Richter", "uri": "spotify:track:m"}],
        [{"track": "Track L", "artist": "Guillaume David", "uri": "spotify:track:l"}],
    ]
    controller.top_artists.side_effect = [
        [{"name": "The HU", "uri": "spotify:artist:a", "genres": ["mongolian metal"]}],
        [{"name": "Max Richter", "uri": "spotify:artist:b", "genres": ["classical", "soundtrack"]}],
        [{"name": "Guillaume David", "uri": "spotify:artist:c", "genres": ["soundtrack"]}],
    ]

    result = HistoryAnalyzer(controller).analyze(recent_limit=10, top_limit=5)

    assert result["recent"]["top_artists"][0]["artist"] == "The HU"
    assert "The HU" in result["suggestions"]["preferred_artists_candidates"]
    assert "soundtrack" in result["suggestions"]["genre_candidates"]
    assert "soundtrack" in result["suggestions"]["context_query_candidates"]["foco"]
    controller.recently_played.assert_called_once_with(limit=10)
    assert controller.top_tracks.call_count == 3
    assert controller.top_artists.call_count == 3


def test_outside_playlist_lista_recentes_fora_da_playlist_sem_duplicar():
    controller = MagicMock()
    controller.recently_played.return_value = [
        {
            "track": "Fora",
            "artist": "Artista A",
            "uri": "spotify:track:outside",
            "played_at": "2026-04-16T10:00:00Z",
        },
        {
            "track": "Dentro",
            "artist": "Artista B",
            "uri": "spotify:track:inside",
            "played_at": "2026-04-16T09:55:00Z",
        },
        {
            "track": "Fora",
            "artist": "Artista A",
            "uri": "spotify:track:outside",
            "played_at": "2026-04-16T09:50:00Z",
        },
    ]
    controller.playlist_tracks.return_value = [
        {"track": "Dentro", "artist": "Artista B", "uri": "spotify:track:inside"}
    ]

    result = HistoryAnalyzer(controller).outside_playlist("playlist123", recent_limit=20)

    assert result["recent_count"] == 3
    assert result["playlist_count"] == 1
    assert result["outside_count"] == 1
    assert result["outside_play_events"] == 2
    assert result["top_outside_artists"] == [{"artist": "Artista A", "count": 2}]
    assert result["top_outside_tracks"] == [
        {"track": "Fora", "artist": "Artista A", "count": 2}
    ]
    assert result["tracks"][0]["uri"] == "spotify:track:outside"
    assert result["tracks"][0]["plays"] == 2
    assert result["tracks"][0]["played_at_events"] == [
        "2026-04-16T10:00:00Z",
        "2026-04-16T09:50:00Z",
    ]
    assert result["candidates"][0]["uri"] == "spotify:track:outside"
    controller.recently_played.assert_called_once_with(limit=20)
    controller.playlist_tracks.assert_called_once_with("playlist123")


def test_outside_playlist_candidatos_priorizam_repeticao_e_recencia():
    controller = MagicMock()
    controller.recently_played.return_value = [
        {
            "track": "Recente",
            "artist": "Artista B",
            "uri": "spotify:track:recent",
            "played_at": "2026-04-16T10:10:00Z",
        },
        {
            "track": "Repetida",
            "artist": "Artista A",
            "uri": "spotify:track:repeat",
            "played_at": "2026-04-16T10:00:00Z",
        },
        {
            "track": "Repetida",
            "artist": "Artista A",
            "uri": "spotify:track:repeat",
            "played_at": "2026-04-16T09:50:00Z",
        },
    ]
    controller.playlist_tracks.return_value = []

    result = HistoryAnalyzer(controller).outside_playlist("playlist123", recent_limit=20)

    assert [track["uri"] for track in result["candidates"]] == [
        "spotify:track:repeat",
        "spotify:track:recent",
    ]
