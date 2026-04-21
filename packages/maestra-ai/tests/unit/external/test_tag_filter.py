"""Testes do filtro de tags Last.fm (issue #8)."""
from __future__ import annotations


def test_remove_tag_de_decada():
    from maestra_ai.core.external.tag_filter import filter_lastfm_tags
    raw = [{"name": "2010s", "count": 100}, {"name": "folk metal", "count": 50}]
    assert filter_lastfm_tags(raw) == {"folk metal"}


def test_remove_tag_de_pais():
    from maestra_ai.core.external.tag_filter import filter_lastfm_tags
    raw = [{"name": "brazilian", "count": 200}, {"name": "mpb", "count": 90}]
    assert filter_lastfm_tags(raw) == {"mpb"}


def test_remove_tag_avaliativa():
    from maestra_ai.core.external.tag_filter import filter_lastfm_tags
    raw = [{"name": "awesome", "count": 500}, {"name": "shoegaze", "count": 100}]
    assert filter_lastfm_tags(raw) == {"shoegaze"}


def test_top_n_corta_por_popularidade():
    from maestra_ai.core.external.tag_filter import filter_lastfm_tags
    raw = [
        {"name": "tag1", "count": 100},
        {"name": "tag2", "count": 90},
        {"name": "tag3", "count": 80},
        {"name": "tag4", "count": 70},
    ]
    assert filter_lastfm_tags(raw, top_n=2) == {"tag1", "tag2"}


def test_normaliza_case():
    from maestra_ai.core.external.tag_filter import filter_lastfm_tags
    raw = [{"name": "Folk Metal", "count": 50}, {"name": "folk metal", "count": 40}]
    result = filter_lastfm_tags(raw)
    # Depois da normalização, os dois viram "folk metal" e viram um único set
    assert result == {"folk metal"}


def test_input_vazio():
    from maestra_ai.core.external.tag_filter import filter_lastfm_tags
    assert filter_lastfm_tags([]) == set()


def test_item_sem_count_trata_como_zero():
    from maestra_ai.core.external.tag_filter import filter_lastfm_tags
    raw = [{"name": "shoegaze"}]  # sem count
    assert filter_lastfm_tags(raw) == {"shoegaze"}
