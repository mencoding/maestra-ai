"""Valida LastfmSource: lookup, tags, similar_artists, rate limit."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from maestra_ai.core.external.lastfm import LastfmSource


@pytest.fixture
def mock_network(mocker):
    network = MagicMock(name="LastFMNetwork")
    mocker.patch("maestra_ai.core.external.lastfm.pylast.LastFMNetwork", return_value=network)
    return network


def test_lookup_by_name_returns_lastfm_data(mock_network):
    track = MagicMock()
    track.get_top_tags.return_value = [
        MagicMock(item=MagicMock(get_name=lambda: "rock")),
        MagicMock(item=MagicMock(get_name=lambda: "alternative")),
    ]
    track.get_playcount.return_value = 1234
    track.get_listener_count.return_value = 567
    artist = MagicMock()
    artist.get_name.return_value = "Fleetwood Mac"
    track.get_artist.return_value = artist
    mock_network.get_track.return_value = track

    source = LastfmSource(api_key="key")
    result = source._lookup({"uri": "spotify:track:x", "name": "Dreams", "artists": ["Fleetwood Mac"], "isrc": None})

    assert result is not None
    assert result["lastfm"]["top_tags"] == ["rock", "alternative"]
    assert result["lastfm"]["playcount"] == 1234
    assert result["lastfm"]["listeners"] == 567
    assert result["match_method"] == "name"


def test_lookup_returns_none_when_track_not_found(mock_network):
    mock_network.get_track.side_effect = Exception("Track not found")
    source = LastfmSource(api_key="key")
    result = source._lookup({"uri": "spotify:track:x", "name": "X", "artists": ["Y"], "isrc": None})
    assert result is None


def test_get_similar_artists_returns_names(mock_network):
    artist = MagicMock()
    similar_entries = [
        MagicMock(item=MagicMock(get_name=lambda: "Stevie Nicks")),
        MagicMock(item=MagicMock(get_name=lambda: "Lindsey Buckingham")),
    ]
    artist.get_similar.return_value = similar_entries
    mock_network.get_artist.return_value = artist

    source = LastfmSource(api_key="key")
    similars = source.get_similar_artists("Fleetwood Mac", limit=2)
    assert similars == ["Stevie Nicks", "Lindsey Buckingham"]


def test_rate_limit_blocks_second_call_within_window(mocker):
    mocker.patch("maestra_ai.core.external.lastfm.time.monotonic", side_effect=[0.0, 0.1, 0.1, 0.3])
    sleep = mocker.patch("maestra_ai.core.external.lastfm.time.sleep")
    mocker.patch("maestra_ai.core.external.lastfm.pylast.LastFMNetwork")

    source = LastfmSource(api_key="key")
    source._respect_rate_limit()
    source._respect_rate_limit()

    sleep.assert_called_once()
    assert sleep.call_args.args[0] == pytest.approx(0.1, rel=0.01)


def test_name_is_lastfm():
    source = LastfmSource(api_key="key")
    assert source.name == "lastfm"
