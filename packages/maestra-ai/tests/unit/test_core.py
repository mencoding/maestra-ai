"""Testes do SpotifyController com mocks do spotipy."""
from unittest.mock import patch

import pytest

from maestra_ai.core.client import SpotifyController


@pytest.fixture
def controller():
    """Cria controller com spotipy mockado."""
    with patch("maestra_ai.core.client.SpotifyOAuth"):
        with patch("maestra_ai.core.client.spotipy.Spotify") as mock_sp:
            instance = mock_sp.return_value
            ctrl = SpotifyController()
            ctrl.sp = instance
            yield ctrl


class TestNow:
    def test_retorna_info_da_faixa_atual(self, controller):
        controller.sp.current_playback.return_value = {
            "is_playing": True,
            "item": {
                "name": "EMV Charon",
                "uri": "spotify:track:abc123",
                "artists": [{"name": "Guillaume David", "id": "art1"}],
                "album": {"name": "IXION OST"},
                "duration_ms": 170964,
            },
            "progress_ms": 50000,
            "device": {"name": "Predator", "id": "dev1", "type": "Computer"},
        }

        result = controller.now()

        assert result["track"] == "EMV Charon"
        assert result["artist"] == "Guillaume David"
        assert result["album"] == "IXION OST"
        assert result["uri"] == "spotify:track:abc123"
        assert result["is_playing"] is True
        assert result["device"] == "Predator"
        assert result["progress_ms"] == 50000
        assert result["duration_ms"] == 170964

    def test_retorna_none_quando_nada_toca(self, controller):
        controller.sp.current_playback.return_value = None
        assert controller.now() is None

    def test_retorna_none_quando_sem_item(self, controller):
        controller.sp.current_playback.return_value = {"item": None}
        assert controller.now() is None


class TestDevices:
    def test_retorna_lista_de_dispositivos(self, controller):
        controller.sp.devices.return_value = {
            "devices": [
                {"name": "Predator", "id": "dev1", "type": "Computer", "is_active": True},
                {"name": "Phone", "id": "dev2", "type": "Smartphone", "is_active": False},
            ]
        }

        result = controller.devices()

        assert len(result) == 2
        assert result[0]["name"] == "Predator"
        assert result[0]["active"] is True
        assert result[1]["name"] == "Phone"

    def test_retorna_lista_vazia_sem_dispositivos(self, controller):
        controller.sp.devices.return_value = {"devices": []}
        assert controller.devices() == []


class TestPlaybackControl:
    def test_play_sem_uri_resume(self, controller):
        controller.sp.start_playback.return_value = None
        controller.play()
        controller.sp.start_playback.assert_called_once_with()

    def test_play_com_uri_track(self, controller):
        controller.sp.start_playback.return_value = None
        controller.play(uri="spotify:track:abc123")
        controller.sp.start_playback.assert_called_once_with(uris=["spotify:track:abc123"])

    def test_play_com_context_uri(self, controller):
        controller.sp.start_playback.return_value = None
        controller.play(uri="spotify:playlist:xyz789")
        controller.sp.start_playback.assert_called_once_with(context_uri="spotify:playlist:xyz789")

    def test_pause(self, controller):
        controller.sp.pause_playback.return_value = None
        controller.pause()
        controller.sp.pause_playback.assert_called_once()

    def test_next_track(self, controller):
        controller.sp.next_track.return_value = None
        controller.next_track()
        controller.sp.next_track.assert_called_once()


class TestQueue:
    def test_queue_list(self, controller):
        controller.sp.queue.return_value = {
            "currently_playing": {
                "name": "EMV Charon",
                "artists": [{"name": "Guillaume David"}],
                "uri": "spotify:track:abc",
            },
            "queue": [
                {
                    "name": "Wolf Totem",
                    "artists": [{"name": "The HU"}],
                    "uri": "spotify:track:def",
                },
            ],
        }

        result = controller.queue_list()

        assert result["current"]["track"] == "EMV Charon"
        assert len(result["queue"]) == 1
        assert result["queue"][0]["track"] == "Wolf Totem"

    def test_queue_add(self, controller):
        controller.sp.add_to_queue.return_value = None
        controller.queue_add("spotify:track:abc123")
        controller.sp.add_to_queue.assert_called_once_with("spotify:track:abc123")


class TestSearch:
    def test_search_tracks(self, controller):
        controller.sp.search.return_value = {
            "tracks": {
                "items": [
                    {
                        "name": "Wolf Totem",
                        "artists": [{"name": "The HU"}],
                        "uri": "spotify:track:abc",
                        "album": {"name": "The Gereg"},
                    },
                ]
            }
        }

        result = controller.search("The HU Wolf Totem")

        assert len(result) == 1
        assert result[0]["track"] == "Wolf Totem"
        assert result[0]["artist"] == "The HU"
        assert result[0]["uri"] == "spotify:track:abc"

    def test_search_pagina_quando_limit_maior_que_limite_por_chamada(self, controller):
        page1 = {
            "tracks": {
                "items": [
                    {
                        "name": f"Track {i}",
                        "artists": [{"name": "Artist"}],
                        "uri": f"spotify:track:{i}",
                        "album": {"name": "Album"},
                    }
                    for i in range(10)
                ]
            }
        }
        page2 = {
            "tracks": {
                "items": [
                    {
                        "name": f"Track {i}",
                        "artists": [{"name": "Artist"}],
                        "uri": f"spotify:track:{i}",
                        "album": {"name": "Album"},
                    }
                    for i in range(10, 15)
                ]
            }
        }
        controller.sp.search.side_effect = [page1, page2]

        result = controller.search("focus", limit=15)

        assert len(result) == 15
        assert controller.sp.search.call_args_list[0].kwargs == {
            "q": "focus",
            "type": "track",
            "limit": 10,
            "offset": 0,
        }
        assert controller.sp.search.call_args_list[1].kwargs == {
            "q": "focus",
            "type": "track",
            "limit": 5,
            "offset": 10,
        }

    def test_search_com_tipo_artist(self, controller):
        controller.sp.search.return_value = {
            "artists": {
                "items": [
                    {"name": "The HU", "uri": "spotify:artist:xyz", "genres": ["mongolian metal"]},
                ]
            }
        }

        result = controller.search("The HU", type="artist")

        assert len(result) == 1
        assert result[0]["name"] == "The HU"


class TestPlaylist:
    def test_playlist_tracks_com_track_key(self, controller):
        controller.sp.playlist_items.return_value = {
            "items": [
                {
                    "track": {
                        "name": "EMV Charon",
                        "artists": [{"name": "Guillaume David"}],
                        "uri": "spotify:track:abc",
                    }
                },
            ]
        }

        result = controller.playlist_tracks("playlist123")

        assert len(result) == 1
        assert result[0]["track"] == "EMV Charon"

    def test_playlist_tracks_com_item_key(self, controller):
        controller.sp.playlist_items.return_value = {
            "items": [
                {
                    "item": {
                        "name": "Wolf Totem",
                        "artists": [{"name": "The HU"}],
                        "uri": "spotify:track:def",
                    }
                },
            ]
        }

        result = controller.playlist_tracks("playlist123")

        assert len(result) == 1
        assert result[0]["track"] == "Wolf Totem"

    def test_playlist_tracks_pagina_automaticamente(self, controller):
        page1 = {
            "items": [
                {"track": {"name": "Track 1", "artists": [{"name": "A1"}], "uri": "spotify:track:1"}},
            ],
            "next": "https://api.spotify.com/v1/playlists/x/tracks?offset=50",
        }
        page2 = {
            "items": [
                {"track": {"name": "Track 2", "artists": [{"name": "A2"}], "uri": "spotify:track:2"}},
            ],
            "next": None,
        }
        controller.sp.playlist_items.side_effect = [page1, page2]

        result = controller.playlist_tracks("playlist123")

        assert len(result) == 2
        assert result[0]["track"] == "Track 1"
        assert result[1]["track"] == "Track 2"
        assert controller.sp.playlist_items.call_count == 2

    def test_playlist_add(self, controller):
        controller.sp.playlist_add_items.return_value = None
        uris = ["spotify:track:a", "spotify:track:b"]
        controller.playlist_add("playlist123", uris)
        controller.sp.playlist_add_items.assert_called_once_with("playlist123", uris)

    def test_playlist_remove(self, controller):
        controller.sp.playlist_remove_all_occurrences_of_items.return_value = None
        uris = ["spotify:track:a"]
        controller.playlist_remove("playlist123", uris)
        controller.sp.playlist_remove_all_occurrences_of_items.assert_called_once_with("playlist123", uris)


class TestHistory:
    def test_recently_played(self, controller):
        controller.sp.current_user_recently_played.return_value = {
            "items": [
                {
                    "played_at": "2026-04-16T10:00:00Z",
                    "track": {
                        "name": "Wolf Totem",
                        "artists": [{"name": "The HU"}],
                        "uri": "spotify:track:abc",
                    },
                }
            ]
        }

        result = controller.recently_played(limit=10)

        assert result[0]["track"] == "Wolf Totem"
        assert result[0]["artist"] == "The HU"
        assert result[0]["played_at"] == "2026-04-16T10:00:00Z"
        controller.sp.current_user_recently_played.assert_called_once_with(limit=10)

    def test_top_tracks(self, controller):
        controller.sp.current_user_top_tracks.return_value = {
            "items": [
                {
                    "name": "EMV Charon",
                    "artists": [{"name": "Guillaume David"}],
                    "album": {"name": "IXION OST"},
                    "uri": "spotify:track:def",
                }
            ]
        }

        result = controller.top_tracks(time_range="short_term", limit=5)

        assert result[0]["track"] == "EMV Charon"
        controller.sp.current_user_top_tracks.assert_called_once_with(time_range="short_term", limit=5)

    def test_top_artists(self, controller):
        controller.sp.current_user_top_artists.return_value = {
            "items": [
                {"name": "The HU", "uri": "spotify:artist:abc", "genres": ["mongolian metal"]}
            ]
        }

        result = controller.top_artists(time_range="long_term", limit=5)

        assert result[0]["name"] == "The HU"
        assert result[0]["genres"] == ["mongolian metal"]
        controller.sp.current_user_top_artists.assert_called_once_with(time_range="long_term", limit=5)
