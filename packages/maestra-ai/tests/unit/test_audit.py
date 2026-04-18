"""Testes de audit log: append, redação de secrets, rotação."""
from __future__ import annotations

import json

from maestra_ai.core import audit


def test_append_basic(monkeypatch, tmp_path):
    monkeypatch.setenv("MAESTRA_STATE_DIR", str(tmp_path / "state"))
    (tmp_path / "state").mkdir()
    audit.log("play", {"track_uri": "spotify:track:abc"}, {"status": "ok"})
    lines = list((tmp_path / "state" / "audit.jsonl").read_text().splitlines())
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["tool"] == "play"


def test_redacts_secrets(monkeypatch, tmp_path):
    monkeypatch.setenv("MAESTRA_STATE_DIR", str(tmp_path / "state"))
    (tmp_path / "state").mkdir()
    audit.log("auth_login", {"client_secret": "abc123", "refresh_token": "xyz"}, {"status": "ok"})
    content = (tmp_path / "state" / "audit.jsonl").read_text()
    assert "abc123" not in content
    assert "xyz" not in content
    assert "REDACTED" in content


def test_redact_result_trata_lista_top_level():
    """Fix M2: listas top-level devem virar {items_count: N} em vez de
    passar o payload inteiro via _redact. Antes, handlers que retornam
    list (ex.: devices, search) vazavam o payload completo no audit."""
    out = audit._redact_result([{"uri": "spotify:track:a"}, {"uri": "spotify:track:b"}])
    assert out == {"items_count": 2}
    # Lista vazia
    assert audit._redact_result([]) == {"items_count": 0}
    # Dicts top-level continuam com comportamento atual
    out_dict = audit._redact_result({"status": "ok"})
    assert out_dict == {"status": "ok"}


def test_rotate_to_gzip(monkeypatch, tmp_path):
    monkeypatch.setenv("MAESTRA_STATE_DIR", str(tmp_path / "state"))
    (tmp_path / "state").mkdir()
    audit.log("t", {}, {})
    audit._force_rotate()
    archive = list((tmp_path / "state").glob("audit.*.jsonl.gz"))
    assert len(archive) == 1
