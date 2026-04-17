"""Testes do FlowAnalyzer."""
from maestra_ai.core.flow import FlowAnalyzer
from maestra_ai.core.taste import TasteProfile


def test_flow_review_detecta_streak_negativo(tmp_path):
    taste = TasteProfile(str(tmp_path / "taste.json"))
    for idx in range(3):
        taste.record_context_signal(
            f"spotify:track:{idx}",
            "negative",
            context="foco",
            source="skip_candidate",
            event_id=f"evt-{idx}",
            weight=-1,
            at=f"2026-04-16T10:0{idx}:00",
        )
        taste.data["tracks"][f"spotify:track:{idx}"]["name"] = f"Foco {idx}"
        taste.data["tracks"][f"spotify:track:{idx}"]["artist"] = "Concentração Profunda"
    taste.save()

    result = FlowAnalyzer(taste).review("foco", window=5)

    assert result["status"] == "drift_detected"
    assert result["negative_streak"] == 3
    assert result["common_negative_artists"] == [{"artist": "Concentração Profunda", "count": 3}]
    assert result["common_negative_terms"][0]["term"] == "foco"
    assert result["recommended_action"] == "pause_director_and_review_recent_style"


def test_flow_review_estavel_com_sinais_positivos(tmp_path):
    taste = TasteProfile(str(tmp_path / "taste.json"))
    taste.record_context_signal(
        "spotify:track:a",
        "positive",
        context="foco",
        source="listened_to_end",
        event_id="evt-a",
        weight=1,
        at="2026-04-16T10:00:00",
    )
    taste.record_context_signal(
        "spotify:track:b",
        "negative",
        context="foco",
        source="skip_candidate",
        event_id="evt-b",
        weight=-1,
        at="2026-04-16T10:01:00",
    )

    result = FlowAnalyzer(taste).review("foco", window=5)

    assert result["status"] == "stable"
    assert result["negative_streak"] == 1
    assert result["recommended_action"] == "continue_observing"
