"""Testes do cliente MusicBrainz."""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from maestra_ai.core.external.musicbrainz import MusicBrainzSource

FIX = Path(__file__).parent.parent.parent / "fixtures" / "external"


@pytest.fixture
def mb():
    return MusicBrainzSource(app_version="9.9.9-test")


def _load(name):
    return json.loads((FIX / name).read_text())


def test_name_and_configured(mb):
    assert mb.name == "musicbrainz"
    assert mb.is_configured() is True


def test_enhance_track_by_isrc(mb):
    track = {
        "uri": "spotify:track:dreams",
        "name": "Dreams",
        "artists": ["Fleetwood Mac"],
        "isrc": "USUM71807351",
    }
    recording = _load("mb_recording_by_isrc.json")
    # Fixture reflete resposta real da lib com includes=["tags"] — sem genre-list
    artist_via_lib = _load("mb_artist_by_mbid.json")
    with patch("musicbrainzngs.get_recordings_by_isrc", return_value=recording), \
         patch("musicbrainzngs.get_artist_by_id", return_value=artist_via_lib), \
         patch.object(MusicBrainzSource, "_fetch_artist_genres_http", return_value=["rock", "soft rock"]):
        result = mb.enhance_track(track)

    assert result is not None
    assert result["match_method"] == "isrc"
    assert result["artist_mbid"] == "bd13909f-1c29-4c27-a874-d4aaf27c5b1a"
    assert result["musicbrainz"]["mbid"] == "recording-mbid-abc"
    assert "rock" in result["musicbrainz"]["genres"]
    assert "70s" in result["musicbrainz"]["tags"]


def test_enhance_track_without_isrc_falls_back_to_name(mb):
    track = {
        "uri": "spotify:track:obscure",
        "name": "Obscure Song",
        "artists": ["Obscure Artist"],
        "isrc": None,
    }
    search = _load("mb_recording_search.json")
    artist_via_lib = _load("mb_artist_by_mbid.json")
    with patch(
        "musicbrainzngs.search_recordings", return_value=search,
    ), patch(
        "musicbrainzngs.get_artist_by_id", return_value=artist_via_lib,
    ), patch.object(
        MusicBrainzSource, "_fetch_artist_genres_http", return_value=["rock"],
    ):
        result = mb.enhance_track(track)

    assert result is not None
    assert result["match_method"] == "name"
    assert result["artist_mbid"] == "artist-mbid-xyz"


def test_enhance_track_isrc_not_found_falls_back_to_name(mb):
    track = {
        "uri": "spotify:track:x",
        "name": "Obscure Song",
        "artists": ["Obscure Artist"],
        "isrc": "FAKE12345678",
    }
    search = _load("mb_recording_search.json")
    artist_via_lib = _load("mb_artist_by_mbid.json")
    with patch(
        "musicbrainzngs.get_recordings_by_isrc",
        return_value={"recording-list": []},
    ), patch(
        "musicbrainzngs.search_recordings", return_value=search,
    ), patch(
        "musicbrainzngs.get_artist_by_id", return_value=artist_via_lib,
    ), patch.object(
        MusicBrainzSource, "_fetch_artist_genres_http", return_value=[],
    ):
        result = mb.enhance_track(track)

    assert result is not None
    assert result["match_method"] == "name"


def _mb_network_error():
    import musicbrainzngs
    return musicbrainzngs.NetworkError("timeout")


def test_enhance_track_returns_none_on_network_failure(mb):
    track = {
        "uri": "spotify:track:x",
        "name": "N",
        "artists": ["A"],
        "isrc": None,
    }
    with patch(
        "musicbrainzngs.search_recordings",
        side_effect=_mb_network_error(),
    ):
        assert mb.enhance_track(track) is None


def test_enhance_track_returns_none_when_no_match(mb):
    track = {
        "uri": "spotify:track:x",
        "name": "N",
        "artists": ["A"],
        "isrc": None,
    }
    with patch(
        "musicbrainzngs.search_recordings",
        return_value={"recording-list": [], "recording-count": 0},
    ):
        assert mb.enhance_track(track) is None


# ---------------------------------------------------------------------------
# Testes isolados do helper HTTP de gêneros
# ---------------------------------------------------------------------------

def test_fetch_artist_genres_http_success(mb):
    """HTTP helper retorna lista de nomes quando a resposta é válida."""
    payload = json.dumps({
        "id": "some-mbid",
        "genres": [
            {"name": "rock", "count": 42},
            {"name": "pop", "count": 10},
        ],
    }).encode()
    mock_resp = MagicMock()
    mock_resp.__enter__ = lambda self: mock_resp
    mock_resp.__exit__ = lambda self, *a: None
    mock_resp.read = lambda: payload
    with patch("urllib.request.urlopen", return_value=mock_resp):
        genres = mb._fetch_artist_genres_http("some-mbid")
    assert genres == ["rock", "pop"]


def test_fetch_artist_genres_http_empty_genres_key(mb):
    """HTTP helper retorna [] quando o campo genres existe mas está vazio."""
    payload = json.dumps({"id": "some-mbid", "genres": []}).encode()
    mock_resp = MagicMock()
    mock_resp.__enter__ = lambda self: mock_resp
    mock_resp.__exit__ = lambda self, *a: None
    mock_resp.read = lambda: payload
    with patch("urllib.request.urlopen", return_value=mock_resp):
        genres = mb._fetch_artist_genres_http("some-mbid")
    assert genres == []


def test_fetch_artist_genres_http_missing_genres_key(mb):
    """HTTP helper retorna [] quando o campo genres não está presente."""
    payload = json.dumps({"id": "some-mbid"}).encode()
    mock_resp = MagicMock()
    mock_resp.__enter__ = lambda self: mock_resp
    mock_resp.__exit__ = lambda self, *a: None
    mock_resp.read = lambda: payload
    with patch("urllib.request.urlopen", return_value=mock_resp):
        genres = mb._fetch_artist_genres_http("some-mbid")
    assert genres == []


def test_fetch_artist_genres_http_network_error(mb):
    """HTTP helper retorna [] em caso de erro de rede, sem lançar exceção."""
    with patch("urllib.request.urlopen", side_effect=Exception("boom")):
        genres = mb._fetch_artist_genres_http("some-mbid")
    assert genres == []
