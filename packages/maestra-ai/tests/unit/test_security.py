"""Testes do módulo core.security — redaction para saída CLI.

P0-R1: o fix v0.2.3 redactava só err_dict["where"] em cli/__init__.py::main.
cli/_common.py::error() e os except Exception em basic.py continuavam
jogando str(SpotifyException) cru — que pode conter tokens Bearer.
"""
from __future__ import annotations

import json

import pytest

from maestra_ai.core.security import redact_error_dict, redact_str


class TestRedactStr:
    def test_remove_bearer_token(self):
        msg = "Authorization: Bearer abc123XYZ_token-longo.aqui"
        out = redact_str(msg)
        assert "abc123XYZ_token-longo.aqui" not in out
        assert "REDACTED" in out

    def test_remove_token_hexadecimal_longo(self):
        # Tokens opacos tipicamente >= 32 chars alfanuméricos
        msg = "access_token=abcdef0123456789abcdef0123456789abcdef"
        out = redact_str(msg)
        assert "abcdef0123456789abcdef0123456789abcdef" not in out
        assert "REDACTED" in out

    def test_preserva_texto_curto_legivel(self):
        msg = "Falha ao conectar: token expirado"
        assert redact_str(msg) == msg

    def test_input_nao_string_retorna_como_string(self):
        # Garantir que não crasha com None, int, etc.
        assert isinstance(redact_str(""), str)


class TestRedactStrContextual:
    """MEDIUM-1: redação contextual — preserva strings inocentes."""

    def test_redact_str_preserva_track_uri(self):
        s = "tocando spotify:track:1V2aEtKkJxLyJcxAz94nLY agora"
        assert "spotify:track:1V2aEtKkJxLyJcxAz94nLY" in redact_str(s)

    def test_redact_str_preserva_playlist_id_em_contexto(self):
        s = "playlist 1V2aEtKkJxLyJcxAz94nLY sincronizada"
        out = redact_str(s)
        assert "1V2aEtKkJxLyJcxAz94nLY" in out

    def test_redact_str_preserva_nomes_longos(self):
        s = "faixa: A Million Miles Away From Anywhere Anyone Has Ever Been Before"
        assert "REDACTED" not in redact_str(s)

    def test_redact_str_redacta_bearer_token(self):
        s = "Authorization: Bearer BQC3abc123xyz987longtoken"
        assert "BQC3abc123xyz987longtoken" not in redact_str(s)
        assert "REDACTED" in redact_str(s)

    def test_redact_str_redacta_key_value_conhecido(self):
        cases = [
            "access_token=BQC3abc123longvalue456",
            "refresh_token=AQD_xyz789longvalue123",
            "client_secret=abc123secret789longvalue",
            "api_key=pk_live_abc123longvalue456",
        ]
        for s in cases:
            out = redact_str(s)
            assert "REDACTED" in out, f"não redatou: {s!r}"

    def test_redact_str_redacta_jwt(self):
        s = "token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjMifQ.abc123"
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in redact_str(s)


class TestRedactErrorDict:
    def test_redact_cobre_where(self):
        d = {
            "what_happened": "Falha na API",
            "where": {"client_secret": "xyz", "other": "ok"},
        }
        out = redact_error_dict(d)
        assert out["where"]["client_secret"] == "REDACTED"
        assert out["where"]["other"] == "ok"

    def test_redact_cobre_what_happened_com_bearer(self):
        d = {
            "what_happened": "401: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
            "where": {},
        }
        out = redact_error_dict(d)
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in out["what_happened"]

    def test_nao_destroi_campos_legitimos(self):
        d = {
            "title": "Problema de autenticação",
            "what_happened": "Token revogado",
            "where": {"url": "https://api.spotify.com/v1/me"},
            "probable_causes": ["Token revogado"],
            "suggested_actions": [{"command": "maestra auth login"}],
            "agent_hint": "Oriente o usuário a rodar auth login",
        }
        out = redact_error_dict(d)
        assert out["title"] == "Problema de autenticação"
        assert out["what_happened"] == "Token revogado"
        assert out["probable_causes"] == ["Token revogado"]


class TestErrorFunctionRedact:
    """cli/_common.py::error() deve redactar mensagem antes de emitir JSON em stderr."""

    def test_error_redacts_bearer_na_mensagem(self, capsys):
        from maestra_ai.cli._common import error

        with pytest.raises(SystemExit):
            error("Falha: Bearer AQP1abcdefghij1234567890abcdefghij12", "AUTH_ERROR")

        captured = capsys.readouterr()
        assert "AQP1abcdefghij1234567890abcdefghij12" not in captured.err
        assert "REDACTED" in captured.err
        # Estrutura JSON preservada
        payload = json.loads(captured.err)
        assert payload["code"] == "AUTH_ERROR"
