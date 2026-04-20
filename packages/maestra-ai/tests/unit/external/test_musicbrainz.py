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
