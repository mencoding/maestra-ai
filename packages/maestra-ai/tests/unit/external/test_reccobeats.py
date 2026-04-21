"""ReccoBeatsSource: lookup por ISRC, 2-step, rate limit."""
from __future__ import annotations

import json
from unittest.mock import MagicMock


def _fake_response(payload: dict) -> MagicMock:
    r = MagicMock()
    r.read.return_value = json.dumps(payload).encode("utf-8")
    r.__enter__.return_value = r
    r.__exit__.return_value = False
    return r


def test_is_configured_always_true():
    from maestra_ai.core.external.reccobeats import ReccoBeatsSource
    source = ReccoBeatsSource()
    assert source.is_configured() is True


def test_enhance_track_no_isrc_returns_none():
    from maestra_ai.core.external.reccobeats import ReccoBeatsSource
    source = ReccoBeatsSource()
    result = source.enhance_track({"uri": "u", "name": "Song", "artists": ["A"], "isrc": None})
    assert result is None


def test_enhance_track_full_flow(mocker):
    """Simula as 2 chamadas: track lookup + audio features."""
    from maestra_ai.core.external.reccobeats import ReccoBeatsSource

    track_resp = _fake_response({
        "content": [{"id": "rb-uuid-1", "isrc": "USTEST1234567", "href": "https://open.spotify.com/track/x"}]
    })
    feats_resp = _fake_response({
        "content": [{
            "id": "rb-uuid-1",
            "tempo": 117.346,
            "key": 2,
            "mode": 1,
            "loudness": -12.994,
            "acousticness": 0.244,
            "danceability": 0.403,
            "energy": 0.786,
            "instrumentalness": 0.0,
            "liveness": 0.688,
            "speechiness": 0.049,
            "valence": 0.785,
        }]
    })

    mocker.patch(
        "maestra_ai.core.external.reccobeats.urllib.request.urlopen",
        side_effect=[track_resp, feats_resp],
    )

    source = ReccoBeatsSource()
    result = source.enhance_track({
        "uri": "spotify:track:x",
        "name": "Song",
        "artists": ["Artist"],
        "isrc": "USTEST1234567",
    })

    assert result is not None
    assert result["reccobeats"]["tempo"] == 117.346
    assert result["reccobeats"]["key"] == 2
    assert result["reccobeats"]["mode"] == 1
    assert result["reccobeats"]["energy"] == 0.786
    assert result["reccobeats"]["valence"] == 0.785
    assert result["match_method"] == "isrc"


def test_enhance_track_isrc_not_found(mocker):
    """track lookup retorna content=[] — nenhuma entry com o ISRC buscado."""
    from maestra_ai.core.external.reccobeats import ReccoBeatsSource

    empty_resp = _fake_response({"content": []})
    mocker.patch(
        "maestra_ai.core.external.reccobeats.urllib.request.urlopen",
        return_value=empty_resp,
    )

    source = ReccoBeatsSource()
    result = source.enhance_track({
        "uri": "u",
        "name": "Unknown",
        "artists": ["X"],
        "isrc": "NOTFOUND0001",
    })
    assert result is None


def test_rate_limit_blocks_second_call(mocker):
    """Segunda chamada dentro do intervalo deve provocar sleep."""
    from maestra_ai.core.external.reccobeats import ReccoBeatsSource

    source = ReccoBeatsSource()
    sleep_mock = mocker.patch("maestra_ai.core.external.reccobeats.time.sleep")

    # Simula: primeira chamada a now = 0.0, segunda a now = 0.1 (< 1.0)
    mocker.patch(
        "maestra_ai.core.external.reccobeats.time.monotonic",
        side_effect=[float("-inf"), 0.0, 0.1, 0.1],
    )

    source._respect_rate_limit()  # primeira — sem sleep
    source._respect_rate_limit()  # segunda — deve sleepy

    assert sleep_mock.called
