"""Testes de cli/director.py — loop respawn (Fix BLOCKER-2)."""
from __future__ import annotations

from argparse import Namespace
from unittest.mock import MagicMock

import pytest

from maestra_ai.cli.director import cmd_director_run
from maestra_ai.core.errors import RateLimitError


def _make_args(interval: int = 1) -> Namespace:
    return Namespace(
        interval=interval,
        target=40,
        count=2,
        import_outside="off",
        outside_min_plays=2,
        outside_count=2,
        outside_recent_limit=50,
        max_per_artist=1,
        max_artist_share=0.25,
    )


def test_director_run_loop_recupera_de_maestra_error(monkeypatch):
    """RateLimitError na 1a iteração não mata o loop; 2a sucede e depois para."""
    director = MagicMock()
    # 1ª chamada levanta; 2ª sucede; 3ª levanta KeyboardInterrupt para parar o loop.
    director.run_once.side_effect = [
        RateLimitError("throttle"),
        {"action": "hold"},
        KeyboardInterrupt(),
    ]

    # Mock time.sleep para não travar.
    import maestra_ai.cli.director as dmod
    monkeypatch.setattr(dmod.time, "sleep", lambda _s: None)

    with pytest.raises(KeyboardInterrupt):
        cmd_director_run(_make_args(interval=1), director=director)

    # Director rodou 3 vezes: falha, sucesso, KeyboardInterrupt.
    assert director.run_once.call_count == 3


def test_director_run_loop_recupera_de_erro_inesperado(monkeypatch):
    """Exceção genérica também não mata o loop; loga via logger."""
    director = MagicMock()
    director.run_once.side_effect = [
        ValueError("surpresa"),
        KeyboardInterrupt(),
    ]

    import maestra_ai.cli.director as dmod
    monkeypatch.setattr(dmod.time, "sleep", lambda _s: None)

    with pytest.raises(KeyboardInterrupt):
        cmd_director_run(_make_args(interval=1), director=director)

    assert director.run_once.call_count == 2
