"""Testes do rollback que chama snapshot antes de restaurar."""
from __future__ import annotations

from unittest.mock import patch

from maestra_ai.core import rollback, snapshot


def test_rollback_creates_safety_snapshot(monkeypatch, tmp_path):
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
    (tmp_path / "data").mkdir()
    snap_id = snapshot.create("test", {"playlist": ["a"]})

    with patch.object(rollback, "_apply_state") as apply_mock:
        result = rollback.rollback_to(snap_id, current_state_fn=lambda: {"playlist": ["x"]})
        assert result["restored"] == snap_id
        assert result["safety_snapshot"]
        apply_mock.assert_called_once()


def test_rollback_last(monkeypatch, tmp_path):
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
    (tmp_path / "data").mkdir()
    snapshot.create("first", {"idx": 1})
    second = snapshot.create("second", {"idx": 2})
    with patch.object(rollback, "_apply_state"):
        result = rollback.rollback_to(None, current_state_fn=lambda: {"idx": "now"})
        assert result["restored"] == second
