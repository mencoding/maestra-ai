"""Testes do agregador `profile show`."""
import json

from maestra_ai.core.profile_view import build_profile_view


def test_build_profile_view_agrega_taste_e_rationale(tmp_path, monkeypatch):  # noqa: E501
    monkeypatch.setattr(
        "maestra_ai.core.init._has_token", lambda: True,
    )
    """Agrega taste_profile.json + onboard_rationale.json + state detectado."""
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    state_dir = tmp_path / "state"
    for d in (config_dir, data_dir, state_dir):
        d.mkdir()

    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(data_dir))
    monkeypatch.setenv("MAESTRA_STATE_DIR", str(state_dir))

    (config_dir / "config.json").write_text(json.dumps({
        "client_id": "abc", "client_secret": "def", "redirect_uri": "http://x",
    }))
    (data_dir / "taste_profile.json").write_text(json.dumps({
        "version": 1,
        "global_signal": {"top_genres": [["rock", 5]]},
        "tracks": {
            "spotify:track:a": {"feedback": "good", "artist": "X"},
            "spotify:track:b": {"feedback": "bad", "artist": "Y"},
            "spotify:track:c": {"feedback": None, "artist": "Z"},
        },
        "context_queries": {"foco": ["q1"]},
    }))
    (state_dir / "onboard_rationale.json").write_text(json.dumps({
        "generated_at": "2026-04-20T06:00:00-03:00",
        "suggestions": [
            {"text": "rock melódico", "based_on": {
                "genres": ["rock"], "decades": ["2010s"], "artists": ["X"],
            }, "contributing_tracks": [{"uri": "spotify:track:a"}]},
        ],
    }))

    view = build_profile_view()

    assert view["state"] == "C"
    assert view["total_tracks"] == 3
    assert view["feedback"]["good"] == 1
    assert view["feedback"]["bad"] == 1
    assert view["contexts"] == ["foco"]
    assert len(view["suggestions"]) == 1
    assert view["suggestions"][0]["text"] == "rock melódico"
    assert view["last_analysis_at"] == "2026-04-20T06:00:00-03:00"


def test_build_profile_view_sem_analise(tmp_path, monkeypatch):
    """Sem taste_profile.json nem rationale, retorna view minimal com state A/A2."""
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    state_dir = tmp_path / "state"
    for d in (config_dir, data_dir, state_dir):
        d.mkdir()

    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(data_dir))
    monkeypatch.setenv("MAESTRA_STATE_DIR", str(state_dir))

    view = build_profile_view()

    assert view["state"] == "A"
    assert view["total_tracks"] == 0
    assert view["suggestions"] == []
    assert view["last_analysis_at"] is None
