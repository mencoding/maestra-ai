"""Testes do bloco de atribuição."""
from maestra_ai.core.external.attribution import render_attribution


def test_render_empty_returns_empty_string():
    assert render_attribution([]) == ""


def test_render_musicbrainz_contains_link_and_label():
    output = render_attribution(["musicbrainz"])
    assert "MusicBrainz" in output
    assert "musicbrainz.org/doc/About" in output
    assert "Fontes usadas" in output


def test_render_multiple_sources():
    output = render_attribution(["musicbrainz", "lastfm", "getsongbpm"])
    assert "MusicBrainz" in output
    assert "Last.fm" in output
    assert "GetSongBPM" in output


def test_render_ignores_unknown_source():
    output = render_attribution(["musicbrainz", "does-not-exist"])
    assert "MusicBrainz" in output
    assert "does-not-exist" not in output
