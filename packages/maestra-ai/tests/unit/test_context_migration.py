"""context.json: string legacy migra para {text, bpm}."""
from __future__ import annotations

import json
from datetime import datetime

import pytest

from maestra_ai.core.context import ContextState


@pytest.fixture
def ctx_path(tmp_path):
    return tmp_path / "context.json"


def test_show_migrates_legacy_string(ctx_path):
    ctx_path.write_text(json.dumps({"context": "foco profundo", "set_at": datetime.now().isoformat(timespec="seconds"), "ttl_minutes": 120}), encoding="utf-8")
    state = ContextState(ctx_path)
    data = state.show()
    assert data is not None
    assert isinstance(data["context"], dict)
    assert data["context"]["text"] == "foco profundo"
    assert data["context"]["bpm"] is None


def test_set_with_bpm_writes_objeto(ctx_path):
    state = ContextState(ctx_path)
    state.set("foco", bpm={"min": 60, "max": 90})
    data = json.loads(ctx_path.read_text())
    assert data["context"]["text"] == "foco"
    assert data["context"]["bpm"] == {"min": 60, "max": 90}


def test_set_without_bpm_preserves_when_text_same(ctx_path):
    state = ContextState(ctx_path)
    state.set("foco", bpm={"min": 60, "max": 90})
    state.set("foco")  # sem bpm explícito
    data = json.loads(ctx_path.read_text())
    assert data["context"]["bpm"] == {"min": 60, "max": 90}


def test_set_without_bpm_clears_when_text_changes(ctx_path):
    state = ContextState(ctx_path)
    state.set("foco", bpm={"min": 60, "max": 90})
    state.set("treino")
    data = json.loads(ctx_path.read_text())
    assert data["context"]["text"] == "treino"
    assert data["context"]["bpm"] is None


def test_clear_bpm(ctx_path):
    state = ContextState(ctx_path)
    state.set("foco", bpm={"min": 60, "max": 90})
    state.clear_bpm()
    data = json.loads(ctx_path.read_text())
    assert data["context"]["text"] == "foco"
    assert data["context"]["bpm"] is None


def test_validate_bpm_rejects_out_of_range():
    from maestra_ai.core.context import validate_bpm_range
    assert validate_bpm_range({"min": 20, "max": 100}) is False  # min < 30
    assert validate_bpm_range({"min": 60, "max": 250}) is False  # max > 220
    assert validate_bpm_range({"min": 100, "max": 60}) is False  # min >= max
    assert validate_bpm_range({"min": 60, "max": 100}) is True
