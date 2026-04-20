"""Testes da integração enhancer no onboard.run."""
from unittest.mock import MagicMock

from maestra_ai.core.onboard import _build_top_100_for_enhancement, _emit_mb_summary


def test_build_top_100_combines_sources():
    top_long = [{"uri": "spotify:track:long1", "name": "L", "artists": [{"name": "A"}]}]
    saved = [{"uri": "spotify:track:saved1", "name": "S", "artists": [{"name": "B"}]}]
    recent = [{"uri": "spotify:track:recent1", "name": "R", "artists": [{"name": "C"}]}]
    weights = {
        "spotify:track:long1": 5.0,
        "spotify:track:saved1": 3.0,
        "spotify:track:recent1": 1.0,
    }
    result = _build_top_100_for_enhancement(
        top_long=top_long, saved=saved, recent=recent, weights=weights,
    )
    assert len(result) == 3
    assert result[0]["uri"] == "spotify:track:long1"


def test_build_top_100_limits_to_100():
    tracks = [
        {"uri": f"spotify:track:{i}", "name": str(i), "artists": [{"name": "X"}]}
        for i in range(150)
    ]
    weights = {t["uri"]: float(150 - i) for i, t in enumerate(tracks)}
    result = _build_top_100_for_enhancement(
        top_long=tracks, saved=[], recent=[], weights=weights,
    )
    assert len(result) == 100


def test_emit_mb_summary_counts():
    enhanced_tracks = [
        {"musicbrainz": {"genres": ["rock"]}, "sources": ["musicbrainz"]},
        {"musicbrainz": {"genres": []}, "sources": ["musicbrainz"]},
        {"musicbrainz": None, "sources": []},
    ]
    _console = MagicMock()
    _emit_mb_summary(enhanced_tracks, console=_console)
    # Deve ter ao menos menção à contagem (1 com genres, 3 total).
    assert _console.print.called
