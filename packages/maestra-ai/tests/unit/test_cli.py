"""Testes de handlers do CLI."""
from argparse import Namespace
from types import SimpleNamespace
from unittest.mock import MagicMock

from maestra_ai.cli import history as _cli_history
from maestra_ai.cli import playlist as _cli_playlist
from maestra_ai.cli import taste as _cli_taste
from maestra_ai.cli._common import PLAYLIST_ID as _PLAYLIST_ID

cli = SimpleNamespace(
    cmd_playlist_add=_cli_playlist.cmd_playlist_add,
    cmd_playlist_top_up=_cli_playlist.cmd_playlist_top_up,
    cmd_playlist_prune=_cli_playlist.cmd_playlist_prune,
    cmd_playlist_remove=_cli_playlist.cmd_playlist_remove,
    cmd_taste_review=_cli_taste.cmd_taste_review,
    cmd_history_import_outside=_cli_history.cmd_history_import_outside,
    PLAYLIST_ID=_PLAYLIST_ID,
)


def test_playlist_add_aceita_argumentos_extras_do_dispatcher(capsys):
    args = Namespace(context="foco", count=2, human=False)
    controller = MagicMock()
    taste = MagicMock()
    curator = MagicMock()
    context_state = MagicMock()
    context_state.show.return_value = None
    curator.curate.return_value = (
        [
            {"track": "Track A", "artist": "Artist A", "uri": "spotify:track:a"},
            {"track": "Track B", "artist": "Artist B", "uri": "spotify:track:b"},
        ],
        ["foco instrumental"],
    )

    cli.cmd_playlist_add(
        args,
        controller=controller,
        taste=taste,
        curator=curator,
        context_state=context_state,
    )

    controller.playlist_add.assert_called_once_with(
        cli.PLAYLIST_ID,
        ["spotify:track:a", "spotify:track:b"],
    )
    taste.record_added.assert_called_once()
    assert '"added": 2' in capsys.readouterr().out


def test_playlist_add_sem_contexto_usa_fallback_foco(capsys):
    args = Namespace(context=None, count=1, human=False)
    controller = MagicMock()
    taste = MagicMock()
    curator = MagicMock()
    context_state = MagicMock()
    context_state.show.return_value = None
    curator.curate.return_value = (
        [{"track": "Track A", "artist": "Artist A", "uri": "spotify:track:a"}],
        ["lo-fi instrumental"],
    )

    cli.cmd_playlist_add(
        args,
        controller=controller,
        taste=taste,
        curator=curator,
        context_state=context_state,
    )

    curator.curate.assert_called_once_with("foco", count=1)
    taste.record_added.assert_called_once()
    output = capsys.readouterr().out
    assert '"context": "foco"' in output
    assert '"context_source": "default"' in output


def test_playlist_add_sem_contexto_usa_contexto_ativo(capsys):
    args = Namespace(context="", count=1, human=False)
    controller = MagicMock()
    taste = MagicMock()
    curator = MagicMock()
    context_state = MagicMock()
    context_state.show.return_value = {"context": "energia", "expires_at": "2026-04-16T18:00:00"}
    curator.curate.return_value = (
        [{"track": "Track A", "artist": "Artist A", "uri": "spotify:track:a"}],
        ["epic orchestral"],
    )

    cli.cmd_playlist_add(
        args,
        controller=controller,
        taste=taste,
        curator=curator,
        context_state=context_state,
    )

    curator.curate.assert_called_once_with("energia", count=1)
    output = capsys.readouterr().out
    assert '"context": "energia"' in output
    assert '"context_source": "active"' in output


def test_playlist_top_up_aceita_argumentos_extras_do_dispatcher(capsys):
    args = Namespace(context="foco", target=3, human=False)
    controller = MagicMock()
    taste = MagicMock()
    curator = MagicMock()
    context_state = MagicMock()
    context_state.show.return_value = None
    controller.playlist_tracks.return_value = [
        {"track": "Track A", "artist": "Artist A", "uri": "spotify:track:a"}
    ]
    curator.curate.return_value = (
        [
            {"track": "Track B", "artist": "Artist B", "uri": "spotify:track:b"},
            {"track": "Track C", "artist": "Artist C", "uri": "spotify:track:c"},
        ],
        ["foco instrumental"],
    )

    cli.cmd_playlist_top_up(
        args,
        controller=controller,
        taste=taste,
        curator=curator,
        context_state=context_state,
    )

    controller.playlist_add.assert_called_once_with(
        cli.PLAYLIST_ID,
        ["spotify:track:b", "spotify:track:c"],
    )
    curator.curate.assert_called_once_with(
        "foco",
        count=2,
        exclude_uris={"spotify:track:a"},
    )
    taste.record_added.assert_called_once()
    assert '"added": 2' in capsys.readouterr().out


def test_playlist_prune_dry_run_nao_remove_candidatos_contextuais(capsys):
    # Contrato novo: cmd_playlist_prune delega em curator.prune().
    args = Namespace(context=None, dry_run=True, human=False)
    controller = MagicMock()
    taste = MagicMock()
    context_state = MagicMock()
    context_state.show.return_value = {"context": "foco"}
    curator = MagicMock()
    curator.prune.return_value = {
        "dry_run": True,
        "context": "foco",
        "candidates": [{"uri": "spotify:track:bad-context"}],
        "total_candidates": 1,
        "removed": 0,
    }

    cli.cmd_playlist_prune(
        args,
        controller=controller,
        taste=taste,
        context_state=context_state,
        curator=curator,
    )

    curator.prune.assert_called_once_with(
        playlist_id=cli.PLAYLIST_ID,
        context="foco",
        confirm=False,
    )
    controller.playlist_remove.assert_not_called()
    output = capsys.readouterr().out
    assert '"dry_run": true' in output
    assert '"spotify:track:bad-context"' in output


def test_playlist_remove_remove_uris_unicas(capsys):
    args = Namespace(
        uris=["spotify:track:a", "spotify:track:a", "spotify:track:b"],
        human=False,
    )
    controller = MagicMock()

    cli.cmd_playlist_remove(args, controller=controller)

    controller.playlist_remove.assert_called_once_with(
        cli.PLAYLIST_ID,
        ["spotify:track:a", "spotify:track:b"],
    )
    output = capsys.readouterr().out
    assert '"removed": 2' in output


def test_playlist_prune_confirm_remove_candidatos(capsys):
    # Contrato novo: dry_run=False aciona execução real no Curator.
    args = Namespace(context="foco", dry_run=False, human=False)
    controller = MagicMock()
    taste = MagicMock()
    context_state = MagicMock()
    context_state.show.return_value = None
    curator = MagicMock()
    curator.prune.return_value = {
        "dry_run": False,
        "context": "",
        "removed": 1,
        "snapshot_id": "snap_abc",
        "uris_removed": ["spotify:track:global-bad"],
    }

    cli.cmd_playlist_prune(
        args,
        controller=controller,
        taste=taste,
        context_state=context_state,
        curator=curator,
    )

    curator.prune.assert_called_once_with(
        playlist_id=cli.PLAYLIST_ID,
        context="",
        confirm=True,
    )
    output = capsys.readouterr().out
    assert '"removed": 1' in output
    assert '"snapshot_id": "snap_abc"' in output


def test_playlist_prune_sem_candidatos_retorna_unchanged(capsys):
    # Sem candidatos: Curator retorna removed=0 em execução real.
    args = Namespace(context="foco", dry_run=False, human=False)
    controller = MagicMock()
    taste = MagicMock()
    context_state = MagicMock()
    context_state.show.return_value = None
    curator = MagicMock()
    curator.prune.return_value = {
        "dry_run": False,
        "context": "",
        "removed": 0,
        "snapshot_id": "snap_empty",
        "uris_removed": [],
    }

    cli.cmd_playlist_prune(
        args,
        controller=controller,
        taste=taste,
        context_state=context_state,
        curator=curator,
    )

    controller.playlist_remove.assert_not_called()
    assert '"removed": 0' in capsys.readouterr().out


def test_taste_review_resume_contexto_sem_alterar_playlist(capsys):
    args = Namespace(context=None, top=5, human=False)
    controller = MagicMock()
    taste = MagicMock()
    context_state = MagicMock()
    context_state.show.return_value = {"context": "foco"}
    controller.playlist_tracks.return_value = [
        {"track": "Boa", "artist": "Artist A", "uri": "spotify:track:good"},
        {"track": "Ruim", "artist": "Artist A", "uri": "spotify:track:bad"},
        {"track": "Neutra", "artist": "Artist B", "uri": "spotify:track:neutral"},
    ]
    taste.data = {
        "tracks": {
            "spotify:track:good": {"name": "Boa", "artist": "Artist A", "added_in_context": "foco"},
            "spotify:track:bad": {"name": "Ruim", "artist": "Artist A", "added_in_context": "foco"},
            "spotify:track:outside": {"name": "Fora", "artist": "Artist C", "added_in_context": "energia"},
        }
    }
    taste.should_remove.return_value = False
    taste.context_score.side_effect = lambda uri, context: {
        "spotify:track:good": 2,
        "spotify:track:bad": -1,
        "spotify:track:neutral": 0,
        "spotify:track:outside": 1,
    }.get(uri, 0)
    taste.get_context_signals.side_effect = lambda uri, context=None: {
        "spotify:track:good": [{"signal": "good"}, {"signal": "positive"}],
        "spotify:track:bad": [{"signal": "bad"}],
        "spotify:track:outside": [{"signal": "good"}],
    }.get(uri, [])

    cli.cmd_taste_review(
        args,
        controller=controller,
        taste=taste,
        context_state=context_state,
    )

    controller.playlist_remove.assert_not_called()
    output = capsys.readouterr().out
    assert '"playlist_count": 3' in output
    assert '"tracked_in_playlist": 2' in output
    assert '"unscored_in_playlist": 1' in output
    assert '"dominant_artists"' in output
    assert '"prune_candidates"' in output
    assert '"spotify:track:bad"' in output
    assert '"tracked_outside_playlist"' in output


def test_history_import_outside_dry_run_nao_altera_playlist_ou_gosto(capsys):
    args = Namespace(
        recent_limit=20,
        count=1,
        min_plays=1,
        context=None,
        signal="good",
        dry_run=True,
        human=False,
    )
    controller = MagicMock()
    taste = MagicMock()
    history_analyzer = MagicMock()
    context_state = MagicMock()
    context_state.show.return_value = {"context": "foco"}
    history_analyzer.outside_playlist.return_value = {
        "recent_count": 2,
        "outside_count": 1,
        "candidates": [
            {
                "track": "Track Fora",
                "artist": "Artist Fora",
                "uri": "spotify:track:outside",
                "plays": 1,
            }
        ],
    }

    cli.cmd_history_import_outside(
        args,
        controller=controller,
        taste=taste,
        history_analyzer=history_analyzer,
        context_state=context_state,
    )

    controller.playlist_add.assert_not_called()
    taste.record_added.assert_not_called()
    taste.record_context_signal.assert_not_called()
    output = capsys.readouterr().out
    assert '"status": "dry_run"' in output
    assert '"would_add": 1' in output


def test_history_import_outside_adiciona_playlist_e_sinal_contextual(capsys):
    args = Namespace(
        recent_limit=20,
        count=2,
        min_plays=2,
        context="revisao",
        signal="good",
        dry_run=False,
        human=False,
    )
    controller = MagicMock()
    taste = MagicMock()
    taste.record_context_signal.return_value = True
    history_analyzer = MagicMock()
    context_state = MagicMock()
    context_state.show.return_value = None
    history_analyzer.outside_playlist.return_value = {
        "recent_count": 3,
        "outside_count": 2,
        "candidates": [
            {
                "track": "Track Forte",
                "artist": "Artist A",
                "uri": "spotify:track:a",
                "plays": 2,
            },
            {
                "track": "Track Fraca",
                "artist": "Artist B",
                "uri": "spotify:track:b",
                "plays": 1,
            },
        ],
    }

    cli.cmd_history_import_outside(
        args,
        controller=controller,
        taste=taste,
        history_analyzer=history_analyzer,
        context_state=context_state,
    )

    controller.playlist_add.assert_called_once_with(
        cli.PLAYLIST_ID,
        ["spotify:track:a"],
    )
    taste.record_added.assert_called_once_with(
        [{"uri": "spotify:track:a", "name": "Track Forte", "artist": "Artist A"}],
        context="revisao",
        queries_used=["outside-playlist"],
    )
    taste.record_context_signal.assert_called_once()
    output = capsys.readouterr().out
    assert '"status": "imported"' in output
    assert '"recorded_signals": 1' in output
