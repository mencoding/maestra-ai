"""Testes para o suporte a --bpm e clear-bpm no CLI context."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest


def test_parse_bpm_flag_valid():
    """Verifica parsing válido de formato X-Y."""
    from maestra_ai.cli.context import _parse_bpm_flag

    assert _parse_bpm_flag("60-100") == {"min": 60, "max": 100}


def test_parse_bpm_flag_invalid_format_raises():
    """Verifica que formato inválido levanta ValueError."""
    from maestra_ai.cli.context import _parse_bpm_flag

    with pytest.raises(ValueError):
        _parse_bpm_flag("abc")


def test_parse_bpm_flag_invalid_range_raises():
    """Verifica que min >= max levanta ValueError."""
    from maestra_ai.cli.context import _parse_bpm_flag

    with pytest.raises(ValueError):
        _parse_bpm_flag("100-60")


def test_context_set_with_bpm(mocker):
    """Verifica que cmd_context_set passa bpm para context_state.set."""
    from maestra_ai.cli import context as cli_ctx

    context_state = MagicMock()
    context_state.set.return_value = {"context": "foco"}
    args = MagicMock(context="foco", bpm="60-90", ttl=120, human=False)

    mocker.patch.object(cli_ctx, "output", return_value=None)

    cli_ctx.cmd_context_set(args, context_state=context_state)
    context_state.set.assert_called_once_with(
        "foco", bpm={"min": 60, "max": 90}, ttl_minutes=120
    )


def test_context_set_without_bpm(mocker):
    """Verifica que cmd_context_set funciona sem --bpm (compatibilidade)."""
    from maestra_ai.cli import context as cli_ctx

    context_state = MagicMock()
    context_state.set.return_value = {"context": "foco"}
    args = MagicMock(context="foco", bpm=None, ttl=120, human=False)

    mocker.patch.object(cli_ctx, "output", return_value=None)

    cli_ctx.cmd_context_set(args, context_state=context_state)
    context_state.set.assert_called_once_with("foco", bpm=None, ttl_minutes=120)


def test_context_set_with_invalid_bpm(mocker):
    """Verifica que bpm inválido resulta em saída de erro."""
    from maestra_ai.cli import context as cli_ctx

    context_state = MagicMock()
    args = MagicMock(context="foco", bpm="invalid", ttl=120, human=False)
    output_mock = mocker.patch.object(cli_ctx, "output", return_value=None)

    cli_ctx.cmd_context_set(args, context_state=context_state)

    # Verifica que output foi chamado com um erro
    output_mock.assert_called_once()
    call_args = output_mock.call_args[0]
    assert "error" in call_args[0]
    # Não deve chamar context_state.set em caso de erro
    context_state.set.assert_not_called()


def test_context_clear_bpm(mocker):
    """Verifica que cmd_context_clear_bpm chama clear_bpm."""
    from maestra_ai.cli import context as cli_ctx

    context_state = MagicMock()
    context_state.clear_bpm.return_value = {"status": "cleared"}
    args = MagicMock(human=False)

    mocker.patch.object(cli_ctx, "output", return_value=None)

    cli_ctx.cmd_context_clear_bpm(args, context_state=context_state)
    context_state.clear_bpm.assert_called_once()
