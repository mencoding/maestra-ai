"""Testes da hierarquia de erros — garante 5 campos humanos."""
from __future__ import annotations

import pytest

from maestra_ai.core.errors import (
    AuthError,
    ConfigError,
    MaestraError,
    NetworkError,
    NotFoundError,
    RateLimitError,
    SpotifyAPIError,
    StorageError,
    UserError,
)


ALL_ERRORS = [
    AuthError, NetworkError, SpotifyAPIError, RateLimitError,
    NotFoundError, StorageError, ConfigError, UserError,
]


def test_base_is_exception():
    assert issubclass(MaestraError, Exception)


@pytest.mark.parametrize("cls", ALL_ERRORS)
def test_has_human_dict(cls):
    err = cls("mensagem de teste")
    d = err.to_human_dict()
    assert "code" in d
    assert "title" in d
    assert "what_happened" in d
    assert "probable_causes" in d
    assert "suggested_actions" in d
    assert isinstance(d["probable_causes"], list)
    assert isinstance(d["suggested_actions"], list)


@pytest.mark.parametrize("cls", ALL_ERRORS)
def test_no_placeholder_in_human_dict(cls):
    err = cls("teste")
    d = err.to_human_dict()
    for field in ("title", "what_happened"):
        assert d[field], f"{cls.__name__}: campo {field} vazio"
        assert "TODO" not in d[field]
        assert "TBD" not in d[field]


def test_auth_error_agent_hint():
    err = AuthError("token revogado")
    d = err.to_human_dict()
    assert "agent_hint" in d
    assert "maestra" in d["agent_hint"].lower() or "auth" in d["agent_hint"].lower()


def test_rate_limit_retry_after():
    err = RateLimitError("429 recebido", retry_after=30)
    assert err.retry_after == 30
    d = err.to_human_dict()
    assert "30" in d["what_happened"] or "30" in str(d["probable_causes"])


def test_spotify_api_error_preserves_status():
    err = SpotifyAPIError("falhou", status=500, body={"error": "server"})
    assert err.status == 500
    assert err.body == {"error": "server"}
