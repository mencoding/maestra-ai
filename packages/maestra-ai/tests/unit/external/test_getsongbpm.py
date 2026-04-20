"""GetSongBpmSource: lookup por ISRC e name, parsing JSON, rate limit."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest


def _fake_response(payload: dict) -> MagicMock:
    r = MagicMock()
    r.read.return_value = json.dumps(payload).encode("utf-8")
    r.__enter__.return_value = r
    r.__exit__.return_value = False
    return r


def test_lookup_by_name_parses_bpm(mocker):
    from maestra_ai.core.external.getsongbpm import GetSongBpmSource
    payload = {"song": {"tempo": "128", "key_of": "C", "time_sig": "4/4"}}
    mocker.patch("maestra_ai.core.external.getsongbpm.urllib.request.urlopen", return_value=_fake_response(payload))

    source = GetSongBpmSource(api_key="key")
    result = source._lookup({"uri": "u", "name": "Song", "artists": ["Artist"], "isrc": None})
    assert result is not None
    assert result["bpm"]["bpm"] == pytest.approx(128.0)
    assert result["bpm"]["key"] == "C"
    assert result["bpm"]["time_signature"] == "4/4"


def test_lookup_returns_none_on_http_error(mocker):
    from maestra_ai.core.external.getsongbpm import GetSongBpmSource
    mocker.patch("maestra_ai.core.external.getsongbpm.urllib.request.urlopen", side_effect=Exception("http 500"))
    source = GetSongBpmSource(api_key="key")
    assert source._lookup({"uri": "u", "name": "S", "artists": ["A"], "isrc": None}) is None


def test_rate_limit_60_per_minute(mocker):
    from maestra_ai.core.external.getsongbpm import (
        _MAX_REQS_PER_MINUTE,
        GetSongBpmSource,
    )

    source = GetSongBpmSource(api_key="key")
    mocker.patch("maestra_ai.core.external.getsongbpm.time.monotonic", side_effect=[i * 0.5 for i in range(_MAX_REQS_PER_MINUTE * 2 + 5)])
    sleep = mocker.patch("maestra_ai.core.external.getsongbpm.time.sleep")

    for _ in range(_MAX_REQS_PER_MINUTE):
        source._respect_rate_limit()
    # 61ª chamada deve provocar sleep
    source._respect_rate_limit()
    assert sleep.called


def test_name_is_getsongbpm():
    from maestra_ai.core.external.getsongbpm import GetSongBpmSource
    source = GetSongBpmSource(api_key="key")
    assert source.name == "getsongbpm"
