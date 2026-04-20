"""Testes para handlers do cli/basic.py — M7 v0.6.2."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from maestra_ai.cli.basic import cmd_next, cmd_pause, cmd_play, cmd_queue_add, cmd_queue_context
from maestra_ai.core.errors import AuthError, RateLimitError, SpotifyAPIError


class TestCmdPlayPropagaMaestraError:
    """M7 v0.6.2: handlers de CLI não engolem MaestraError em str(e).
    MaestraError deve propagar ao main() para render estruturada."""

    def test_cmd_play_propaga_rate_limit_error(self):
        controller = MagicMock()
        controller.play.side_effect = RateLimitError("429", retry_after=30)
        args = MagicMock(uri=None, human=False)

        with pytest.raises(RateLimitError):
            cmd_play(args, controller=controller)

    def test_cmd_queue_add_propaga_auth_error(self):
        controller = MagicMock()
        controller.queue_add.side_effect = AuthError("token expirou")
        args = MagicMock(uri="spotify:track:xxx", human=False)

        with pytest.raises(AuthError, match="token expirou"):
            cmd_queue_add(args, controller=controller)

    def test_cmd_pause_propaga_maestra_error(self):
        controller = MagicMock()
        controller.pause.side_effect = SpotifyAPIError("403 forbidden", status=403)
        args = MagicMock(human=False)

        with pytest.raises(SpotifyAPIError):
            cmd_pause(args, controller=controller)

    def test_cmd_next_propaga_maestra_error(self):
        controller = MagicMock()
        controller.next_track.side_effect = SpotifyAPIError("500 error", status=500)
        args = MagicMock(human=False)

        with pytest.raises(SpotifyAPIError):
            cmd_next(args, controller=controller)


class TestQueueContextFailedField:
    """M7 v0.6.2: cmd_queue_context mantém try/except por-track MAS
    usa MaestraError e registra no campo 'failed' em vez de abortar
    o loop com error()."""

    def test_falhas_por_track_registradas_em_failed(self, capsys):
        controller = MagicMock()
        taste = MagicMock()
        curator = MagicMock()
        context_state = MagicMock()
        context_state.show.return_value = {"context": "workout"}

        tracks = [
            {"uri": "spotify:track:t1", "track": "a", "artist": "x"},
            {"uri": "spotify:track:t2", "track": "b", "artist": "y"},
        ]
        curator.curate.return_value = (tracks, ["q1"])

        def _queue_add(uri):
            if uri == "spotify:track:t2":
                raise SpotifyAPIError("500 server error", status=500)

        controller.queue_add.side_effect = _queue_add

        args = MagicMock(human=False, count=2)
        # context attribute para _curation_context
        args.context = None
        cmd_queue_context(
            args,
            controller=controller,
            taste=taste,
            curator=curator,
            context_state=context_state,
        )
        out = capsys.readouterr().out
        payload = json.loads(out)
        # "tracks" é a lista; "added" é o count inteiro
        assert payload["added"] == 1
        assert len(payload["tracks"]) == 1
        assert payload["tracks"][0]["uri"] == "spotify:track:t1"
        assert len(payload["failed"]) == 1
        assert payload["failed"][0]["uri"] == "spotify:track:t2"
        assert payload["failed"][0]["error"]["code"] == "SpotifyAPIError"

    def test_sem_falhas_failed_vazio(self, capsys):
        controller = MagicMock()
        taste = MagicMock()
        curator = MagicMock()
        context_state = MagicMock()
        context_state.show.return_value = {"context": "foco"}

        tracks = [
            {"uri": "spotify:track:t1", "track": "a", "artist": "x"},
        ]
        curator.curate.return_value = (tracks, ["q1"])

        args = MagicMock(human=False, count=1)
        args.context = None
        cmd_queue_context(
            args,
            controller=controller,
            taste=taste,
            curator=curator,
            context_state=context_state,
        )
        out = capsys.readouterr().out
        payload = json.loads(out)
        assert payload["failed"] == []
        assert payload["added"] == 1
        assert len(payload["tracks"]) == 1
