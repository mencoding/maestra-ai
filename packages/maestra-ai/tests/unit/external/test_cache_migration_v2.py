"""Valida migração de cache schema v1 → v2 (adiciona similar_artists)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from maestra_ai.core.external import cache


@pytest.fixture(autouse=True)
def _isolate_cache(tmp_path, monkeypatch):
    fake_data_dir = tmp_path / "data"
    fake_data_dir.mkdir()
    monkeypatch.setattr(cache.storage, "data_dir", lambda: fake_data_dir)
    monkeypatch.setattr(cache.storage, "ensure_dirs", lambda: None)
    yield fake_data_dir


def test_default_cache_is_v2():
    data = cache._default_cache()
    assert data["version"] == 2
    assert data["tracks"] == {}
    assert data["similar_artists"] == {}


def test_load_migrates_v1_to_v2(_isolate_cache: Path):
    path = _isolate_cache / "external_cache.json"
    path.write_text(json.dumps({"version": 1, "tracks": {"spotify:track:abc": {"uri": "spotify:track:abc"}}}), encoding="utf-8")
    loaded = cache.load_cache()
    assert loaded["version"] == 2
    assert "spotify:track:abc" in loaded["tracks"]
    assert loaded["similar_artists"] == {}


def test_load_preserves_v2(_isolate_cache: Path):
    path = _isolate_cache / "external_cache.json"
    path.write_text(
        json.dumps(
            {
                "version": 2,
                "tracks": {},
                "similar_artists": {"mbid-1": {"similars": ["Artist X"], "fetched_at": "2026-04-20T00:00:00"}},
            }
        ),
        encoding="utf-8",
    )
    loaded = cache.load_cache()
    assert loaded["similar_artists"]["mbid-1"]["similars"] == ["Artist X"]


def test_load_rejects_unknown_version(_isolate_cache: Path):
    path = _isolate_cache / "external_cache.json"
    path.write_text(json.dumps({"version": 99, "tracks": {}}), encoding="utf-8")
    loaded = cache.load_cache()
    assert loaded == cache._default_cache()
