"""Testes do shape dos TypedDicts de metadata externa."""
from maestra_ai.core.external.types import (
    AudioFeaturesData,
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


def test_audio_features_data_shape():
    af: AudioFeaturesData = {
        "tempo": 120.5,
        "key": 5,
        "mode": 1,
        "loudness": -8.3,
        "acousticness": 0.1,
        "danceability": 0.7,
        "energy": 0.8,
        "instrumentalness": 0.0,
        "liveness": 0.2,
        "speechiness": 0.05,
        "valence": 0.6,
    }
    assert af["tempo"] == 120.5
    assert af["key"] == 5


def test_enhanced_track_shape():
    e: EnhancedTrack = {
        "uri": "spotify:track:abc",
        "isrc": "USABC1234567",
        "artist_mbid": "art-mbid-1",
        "musicbrainz": {"mbid": "rec-mbid-1", "genres": ["rock"], "tags": []},
        "lastfm": None,
        "reccobeats": None,
        "sources": ["musicbrainz"],
        "enhanced_at": "2026-04-20T10:00:00-03:00",
        "match_method": "isrc",
    }
    assert e["sources"] == ["musicbrainz"]
    assert e["match_method"] == "isrc"
    assert e["reccobeats"] is None
    assert "bpm" not in e
