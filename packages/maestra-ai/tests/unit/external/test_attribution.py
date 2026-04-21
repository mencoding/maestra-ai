"""Testes do bloco de atribuição."""
from maestra_ai.core.external.attribution import render_attribution


def test_render_empty_returns_empty_string():
    assert render_attribution([]) == ""


def test_render_musicbrainz_contains_link_and_label():
    output = render_attribution(["musicbrainz"])
    assert "MusicBrainz" in output
    assert "musicbrainz.org" in output
    assert "Metadata:" in output


def test_render_reccobeats_contains_link_and_label():
    output = render_attribution(["reccobeats"])
    assert "Reccobeats" in output
    assert "reccobeats.com" in output
    assert "Metadata:" in output


def test_render_multiple_sources():
    output = render_attribution(["musicbrainz", "lastfm", "reccobeats"])
    assert "MusicBrainz" in output
    assert "Last.fm" in output
    assert "Reccobeats" in output


def test_render_ignores_unknown_source():
    output = render_attribution(["musicbrainz", "does-not-exist"])
    assert "MusicBrainz" in output
    assert "does-not-exist" not in output


def test_render_attribution_lists_used_sources():
    out = render_attribution(["musicbrainz", "lastfm"])
    assert "MusicBrainz" in out
    assert "Last.fm" in out
    assert "Reccobeats" not in out


def test_render_attribution_none_returns_empty():
    assert render_attribution([]) == ""


def test_render_attribution_separator_is_middle_dot():
    out = render_attribution(["musicbrainz", "lastfm"])
    assert " · " in out


def test_render_no_getsongbpm():
    """GetSongBPM não deve aparecer em nenhuma renderização."""
    for sources in [
        ["musicbrainz"],
        ["lastfm"],
        ["reccobeats"],
        ["musicbrainz", "lastfm", "reccobeats"],
    ]:
        out = render_attribution(sources)
        assert "GetSongBPM" not in out
        assert "getsongbpm" not in out.lower()
