"""Live test Reccobeats. Opt-in via -m integration_live.

API aberta, sem key — executa sempre que a flag estiver presente.
ISRC de referência: USY252035241 (validado em 2026-04-20).
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration_live


def test_lookup_known_isrc_returns_features():
    from maestra_ai.core.external.reccobeats import ReccoBeatsSource

    source = ReccoBeatsSource()
    result = source.enhance_track({
        "uri": "spotify:track:00ErpkgqiTS4jbf8rQZm8x",
        "name": "Twist and Shout",
        "artists": ["Fleetwood Mac"],
        "isrc": "USY252035241",
    })
    assert result is not None, "Reccobeats deveria retornar audio features para ISRC conhecido"
    rb = result["reccobeats"]
    assert rb["tempo"] > 0
    assert isinstance(rb["key"], int)
    assert isinstance(rb["mode"], int)
    assert 0.0 <= rb["energy"] <= 1.0
    assert 0.0 <= rb["danceability"] <= 1.0
    assert 0.0 <= rb["valence"] <= 1.0
