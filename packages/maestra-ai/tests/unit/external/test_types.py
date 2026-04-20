"""Testes do shape dos TypedDicts de metadata externa."""
from maestra_ai.core.external.types import (
    EnhancedTrack,
    MusicBrainzData,
    TrackInfo,
)


def test_track_info_shape():
    t: TrackInfo = {
        "uri": "spotify:track:abc",
        "name": "Song",
        "artists": ["Artist"],
        "isrc": "USABC1234567",
    }
    assert t["uri"] == "spotify:track:abc"
    assert t["artists"] == ["Artist"]


def test_musicbrainz_data_shape():
    d: MusicBrainzData = {
        "mbid": "rec-mbid-1",
        "genres": ["rock"],
        "tags": ["90s"],
    }
    assert d["mbid"] == "rec-mbid-1"


def test_enhanced_track_shape():
    e: EnhancedTrack = {
        "uri": "spotify:track:abc",
        "isrc": "USABC1234567",
        "artist_mbid": "art-mbid-1",
        "musicbrainz": {"mbid": "rec-mbid-1", "genres": ["rock"], "tags": []},
        "lastfm": None,
        "bpm": None,
        "sources": ["musicbrainz"],
        "enhanced_at": "2026-04-20T10:00:00-03:00",
        "match_method": "isrc",
    }
    assert e["sources"] == ["musicbrainz"]
    assert e["match_method"] == "isrc"
