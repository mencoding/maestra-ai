"""Testes para atribuição condicional no cmd_curate."""
from __future__ import annotations

from unittest.mock import MagicMock


def test_curate_human_prints_attribution(mocker, capsys):
    """Quando human=True e sources_used não vazio, imprime atribuição."""
    from maestra_ai.cli import curate as cli_curate

    curator = MagicMock()
    curator.curate.return_value = (
        [{"uri": "spotify:track:A", "name": "T", "artist": "Art"}],
        ["q"],
        ["musicbrainz", "lastfm"],
    )
    mocker.patch.object(cli_curate, "_curation_context", return_value=("foco", None))

    args = MagicMock(human=True, context=None, count=5)
    cli_curate.cmd_curate(args, curator, None)
    out = capsys.readouterr().out
    assert "Metadata:" in out
    assert "MusicBrainz" in out
    assert "Last.fm" in out


def test_curate_human_no_sources_no_attribution(mocker, capsys):
    """Quando sources_used vazio, NÃO imprime atribuição."""
    from maestra_ai.cli import curate as cli_curate

    curator = MagicMock()
    curator.curate.return_value = (
        [{"uri": "spotify:track:A", "name": "T", "artist": "Art"}],
        ["q"],
        [],
    )
    mocker.patch.object(cli_curate, "_curation_context", return_value=("foco", None))

    args = MagicMock(human=True, context=None, count=5)
    cli_curate.cmd_curate(args, curator, None)
    out = capsys.readouterr().out
    assert "Metadata:" not in out
