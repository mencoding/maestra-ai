"""Live test GetSongBPM. Opt-in via -m integration_live + MAESTRA_GETSONGBPM_KEY."""
from __future__ import annotations

import os

import pytest

from maestra_ai.core.external.getsongbpm import GetSongBpmSource

pytestmark = pytest.mark.integration_live


@pytest.fixture
def _api_key() -> str:
    key = os.environ.get("MAESTRA_GETSONGBPM_KEY")
    if not key:
        pytest.skip("MAESTRA_GETSONGBPM_KEY não configurada")
    return key


def test_lookup_known_track(_api_key: str):
    source = GetSongBpmSource(api_key=_api_key)
    result = source._lookup({
        "uri": "spotify:track:x",
        "name": "Smells Like Teen Spirit",
        "artists": ["Nirvana"],
        "isrc": None,
    })
    assert result is not None
    assert result["bpm"]["bpm"] > 0
