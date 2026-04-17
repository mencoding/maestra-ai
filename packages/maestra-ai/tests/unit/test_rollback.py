"""Testes do rollback que chama snapshot antes de restaurar."""
from __future__ import annotations

from maestra_ai.core import rollback, snapshot


def test_rollback_creates_safety_snapshot(monkeypatch, tmp_path):
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
    (tmp_path / "data").mkdir()
    snap_id = snapshot.create("test", {"playlist": ["a"]})

    applied = []
    result = rollback.rollback_to(
        snap_id,
        current_state_fn=lambda: {"playlist": ["x"]},
        apply_state_fn=lambda s: applied.append(s),
    )
    assert result["restored"] == snap_id
    assert result["safety_snapshot"]
    assert len(applied) == 1
    assert applied[0] == {"playlist": ["a"]}


def test_rollback_last(monkeypatch, tmp_path):
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
    (tmp_path / "data").mkdir()
    snapshot.create("first", {"idx": 1})
    second = snapshot.create("second", {"idx": 2})
    applied = []
    result = rollback.rollback_to(
        None,
        current_state_fn=lambda: {"idx": "now"},
        apply_state_fn=lambda s: applied.append(s),
    )
    assert result["restored"] == second
    assert applied[0] == {"idx": 2}


def test_rollback_no_snapshot_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
    (tmp_path / "data").mkdir()
    from maestra_ai.core.errors import NotFoundError
    try:
        rollback.rollback_to(
            None,
            current_state_fn=lambda: {},
            apply_state_fn=lambda s: None,
        )
    except NotFoundError:
        return
    raise AssertionError("deveria levantar NotFoundError")
