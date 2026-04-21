"""Onboard popula artists_tags com tags Last.fm quando source ativa."""
from __future__ import annotations


def test_artists_tags_agrega_lastfm(mocker):
    """Se LF retorna tags, artists_tags do onboard deve contê-las."""
    from maestra_ai.core import onboard

    enhanced = {
        "uri": "spotify:track:t1",
        "isrc": "ABC",
        "artist_mbid": None,
        "musicbrainz": {"mbid": "m", "genres": ["rock"], "tags": ["uplifting"]},
        "lastfm": {"top_tags": ["dreamy", "psychedelic"], "playcount": 1, "listeners": 1, "similar_artists": []},
        "reccobeats": None,
        "sources": ["musicbrainz", "lastfm"],
        "enhanced_at": "2026-04-20T00:00:00",
        "match_method": "isrc",
    }

    artists_tags: dict[str, list[str]] = {}
    track_info = {"uri": "spotify:track:t1", "artists": [{"id": "a1", "name": "Artist X"}]}
    onboard._aggregate_tags_from_enhanced(enhanced, track_info, artists_tags)
    assert "a1" in artists_tags
    tags = artists_tags["a1"]
    assert "dreamy" in tags or "psychedelic" in tags
