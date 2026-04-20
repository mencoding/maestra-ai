"""curate_weights: defaults + validação + leitura segura."""
from __future__ import annotations

import pytest

from maestra_ai.core.config import (
    DEFAULT_CURATE_WEIGHTS,
    load_curate_weights,
    validate_curate_weights,
)


def test_defaults_sum_to_one():
    s = sum(DEFAULT_CURATE_WEIGHTS.values())
    assert s == pytest.approx(1.0)


def test_validate_accepts_valid():
    w = {"taste": 0.5, "tag": 0.2, "decade": 0.2, "bpm": 0.1}
    assert validate_curate_weights(w) is True


def test_validate_rejects_bad_sum():
    w = {"taste": 0.5, "tag": 0.5, "decade": 0.5, "bpm": 0.5}
    assert validate_curate_weights(w) is False


def test_validate_rejects_out_of_range():
    w = {"taste": 1.5, "tag": -0.5, "decade": 0.0, "bpm": 0.0}
    assert validate_curate_weights(w) is False


def test_validate_rejects_missing_key():
    w = {"taste": 0.5, "tag": 0.3, "decade": 0.2}
    assert validate_curate_weights(w) is False


def test_load_returns_defaults_when_missing():
    cfg = {}
    assert load_curate_weights(cfg) == DEFAULT_CURATE_WEIGHTS


def test_load_returns_defaults_when_invalid():
    cfg = {"curate_weights": {"taste": 9.0, "tag": 0.0, "decade": 0.0, "bpm": 0.0}}
    assert load_curate_weights(cfg) == DEFAULT_CURATE_WEIGHTS


def test_load_returns_custom_when_valid():
    cfg = {"curate_weights": {"taste": 0.5, "tag": 0.2, "decade": 0.2, "bpm": 0.1}}
    assert load_curate_weights(cfg) == cfg["curate_weights"]
