"""Componentes puros e composição do score."""
from __future__ import annotations

import pytest

from maestra_ai.core.scoring import (
    bpm_proximity,
    compose_score,
    decade_match,
    effective_weights,
    tag_similarity,
)

# ------- tag_similarity (Jaccard) -------

def test_tag_similarity_identical():
    assert tag_similarity({"rock", "pop"}, {"rock", "pop"}) == pytest.approx(1.0)


def test_tag_similarity_disjoint():
    assert tag_similarity({"rock"}, {"jazz"}) == 0.0


def test_tag_similarity_half_overlap():
    assert tag_similarity({"rock", "pop"}, {"rock", "jazz"}) == pytest.approx(1 / 3)


def test_tag_similarity_empty_returns_zero():
    assert tag_similarity(set(), {"rock"}) == 0.0
    assert tag_similarity({"rock"}, set()) == 0.0
    assert tag_similarity(set(), set()) == 0.0


def test_tag_similarity_case_insensitive():
    assert tag_similarity({"Rock"}, {"rock"}) == pytest.approx(1.0)


# ------- decade_match -------

def test_decade_match_hit():
    assert decade_match("2015-03-01", {"2010s"}) == 1.0


def test_decade_match_miss():
    assert decade_match("2015-03-01", {"1990s", "2000s"}) == 0.0


def test_decade_match_invalid_date_returns_zero():
    assert decade_match("not-a-date", {"2010s"}) == 0.0


def test_decade_match_empty_dominant_returns_zero():
    assert decade_match("2015-01-01", set()) == 0.0


# ------- bpm_proximity -------

def test_bpm_proximity_center_is_one():
    assert bpm_proximity(track_bpm=80, target={"min": 60, "max": 100}) == pytest.approx(1.0)


def test_bpm_proximity_edge_is_about_half():
    # center 80, half_range = 20 + 10 = 30
    # |60-80| / 30 = 0.666, prox = 1 - 0.666 = 0.333
    assert bpm_proximity(track_bpm=60, target={"min": 60, "max": 100}) == pytest.approx(1 - 20/30)


def test_bpm_proximity_far_is_zero():
    assert bpm_proximity(track_bpm=200, target={"min": 60, "max": 100}) == 0.0


def test_bpm_proximity_none_track_bpm():
    assert bpm_proximity(track_bpm=None, target={"min": 60, "max": 100}) == 0.0


def test_bpm_proximity_none_target():
    assert bpm_proximity(track_bpm=80, target=None) == 0.0


# ------- effective_weights -------

DEFAULTS = {"taste": 0.4, "tag": 0.3, "decade": 0.2, "bpm": 0.1}


def test_effective_weights_all_signals_present():
    w = effective_weights(DEFAULTS, has_lastfm=True, has_bpm_target=True, track_has_bpm=True, has_decade=True)
    assert w == DEFAULTS


def test_effective_weights_no_lastfm_redistributes_to_taste():
    w = effective_weights(DEFAULTS, has_lastfm=False, has_bpm_target=True, track_has_bpm=True, has_decade=True)
    assert w["tag"] == 0.0
    assert w["taste"] == pytest.approx(0.4 + 0.3)


def test_effective_weights_no_bpm_target_zeros_bpm():
    w = effective_weights(DEFAULTS, has_lastfm=True, has_bpm_target=False, track_has_bpm=False, has_decade=True)
    assert w["bpm"] == 0.0
    assert w["taste"] == pytest.approx(0.5)


def test_effective_weights_no_decade_redistributes():
    w = effective_weights(DEFAULTS, has_lastfm=True, has_bpm_target=True, track_has_bpm=True, has_decade=False)
    assert w["decade"] == 0.0
    assert w["taste"] == pytest.approx(0.6)


def test_effective_weights_nothing_but_taste():
    w = effective_weights(DEFAULTS, has_lastfm=False, has_bpm_target=False, track_has_bpm=False, has_decade=False)
    assert w["taste"] == pytest.approx(1.0)
    assert w["tag"] == w["decade"] == w["bpm"] == 0.0


# ------- compose_score -------

def test_compose_score_all_one():
    w = {"taste": 0.4, "tag": 0.3, "decade": 0.2, "bpm": 0.1}
    score = compose_score(weights=w, taste=1.0, tag=1.0, decade=1.0, bpm=1.0)
    assert score == pytest.approx(1.0)


def test_compose_score_taste_negative_pulls_down():
    w = {"taste": 0.4, "tag": 0.3, "decade": 0.2, "bpm": 0.1}
    score = compose_score(weights=w, taste=-1.0, tag=0.0, decade=0.0, bpm=0.0)
    assert score == pytest.approx(-0.4)


# ------- anti_tag_penalty -------

class TestAntiTagPenalty:
    def test_sem_overlap_retorna_zero(self):
        from maestra_ai.core.scoring import anti_tag_penalty
        assert anti_tag_penalty({"rock"}, {"ambient"}, degraded=True) == 0.0

    def test_com_overlap_retorna_negativo(self):
        from maestra_ai.core.scoring import anti_tag_penalty
        p = anti_tag_penalty({"rock", "ambient"}, {"ambient"}, degraded=True)
        assert p < 0

    def test_degraded_false_sempre_zero(self):
        from maestra_ai.core.scoring import anti_tag_penalty
        assert anti_tag_penalty({"ambient"}, {"ambient"}, degraded=False) == 0.0

    def test_multiplos_overlaps_penalizam_mais_ate_limite(self):
        from maestra_ai.core.scoring import anti_tag_penalty
        p1 = anti_tag_penalty({"a"}, {"a"}, degraded=True)
        p2 = anti_tag_penalty({"a", "b"}, {"a", "b"}, degraded=True)
        p5 = anti_tag_penalty({"a", "b", "c", "d", "e"}, {"a", "b", "c", "d", "e"}, degraded=True)
        assert p2 < p1  # mais negativo
        assert p5 <= p2  # não pior que 3 (limite em 3 pela spec)

    def test_negative_tags_vazio_retorna_zero(self):
        from maestra_ai.core.scoring import anti_tag_penalty
        assert anti_tag_penalty({"rock"}, set(), degraded=True) == 0.0
