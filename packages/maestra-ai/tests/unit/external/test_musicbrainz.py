"""Testes do cliente MusicBrainz."""
import json
from pathlib import Path
from unittest.mock import patch

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
    artist = _load("mb_artist_by_mbid.json")
    with patch("musicbrainzngs.get_recordings_by_isrc", return_value=recording), \
         patch("musicbrainzngs.get_artist_by_id", return_value=artist):
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
    artist = _load("mb_artist_by_mbid.json")
    with patch(
        "musicbrainzngs.search_recordings", return_value=search,
    ), patch(
        "musicbrainzngs.get_artist_by_id", return_value=artist,
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
    artist = _load("mb_artist_by_mbid.json")
    with patch(
        "musicbrainzngs.get_recordings_by_isrc",
        return_value={"recording-list": []},
    ), patch(
        "musicbrainzngs.search_recordings", return_value=search,
    ), patch(
        "musicbrainzngs.get_artist_by_id", return_value=artist,
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
