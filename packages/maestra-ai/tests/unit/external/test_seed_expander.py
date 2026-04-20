"""Valida SeedExpander: cache hit/miss, TTL 60d, fallback sem Last.fm."""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from maestra_ai.core.external.seed_expander import SeedExpander


@pytest.fixture(autouse=True)
def _isolate_cache(tmp_path, monkeypatch):
    from maestra_ai.core.external import cache
    fake_data_dir = tmp_path / "data"
    fake_data_dir.mkdir()
    monkeypatch.setattr(cache.storage, "data_dir", lambda: fake_data_dir)
    monkeypatch.setattr(cache.storage, "ensure_dirs", lambda: None)
    yield fake_data_dir


def test_expand_hits_network_when_cache_empty():
    lf = MagicMock()
    lf.get_similar_artists.return_value = ["Artist A", "Artist B"]
    expander = SeedExpander(lastfm_source=lf, limit=5)

    similars = expander.expand(["Fleetwood Mac"])

    assert similars == ["Artist A", "Artist B"]
    lf.get_similar_artists.assert_called_once_with("Fleetwood Mac", limit=5)


def test_expand_uses_cache_on_second_call():
    lf = MagicMock()
    lf.get_similar_artists.return_value = ["Artist A"]
    expander = SeedExpander(lastfm_source=lf, limit=5)

    first = expander.expand(["Fleetwood Mac"])
    second = expander.expand(["Fleetwood Mac"])

    assert first == second == ["Artist A"]
    lf.get_similar_artists.assert_called_once()


def test_expand_refreshes_after_ttl(monkeypatch):
    lf = MagicMock()
    lf.get_similar_artists.side_effect = [["A"], ["B"]]
    expander = SeedExpander(lastfm_source=lf, limit=5)

    expander.expand(["X"])

    from maestra_ai.core.external import seed_expander as se_mod
    original = se_mod._now_iso
    past = (datetime.now() - timedelta(days=61)).isoformat(timespec="seconds")
    monkeypatch.setattr(se_mod, "_now_iso", lambda: past)
    # forçar o cache a ficar com timestamp antigo
    from maestra_ai.core.external import cache as cache_mod
    data = cache_mod.load_cache()
    for key in data["similar_artists"]:
        data["similar_artists"][key]["fetched_at"] = past
    cache_mod.save_cache(data)

    monkeypatch.setattr(se_mod, "_now_iso", original)
    second = expander.expand(["X"])
    assert second == ["B"]
    assert lf.get_similar_artists.call_count == 2


def test_expand_dedupes_across_artists():
    lf = MagicMock()
    lf.get_similar_artists.side_effect = [["A", "B"], ["B", "C"]]
    expander = SeedExpander(lastfm_source=lf, limit=5)

    result = expander.expand(["X", "Y"])
    assert result == ["A", "B", "C"]


def test_expand_returns_empty_when_lastfm_none():
    expander = SeedExpander(lastfm_source=None, limit=5)
    assert expander.expand(["X"]) == []
