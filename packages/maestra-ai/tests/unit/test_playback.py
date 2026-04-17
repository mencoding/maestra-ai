"""Testes do PlaybackObserver — eventos conservadores de playback."""
import json

from maestra_ai.core.playback import PlaybackObserver


def make_track(uri="spotify:track:a", is_playing=True, progress_ms=1000, duration_ms=100000):
    return {
        "track": "Track A",
        "artist": "Artist A",
        "album": "Album A",
        "uri": uri,
        "is_playing": is_playing,
        "device": "Computer",
        "progress_ms": progress_ms,
        "duration_ms": duration_ms,
    }


def read_events(path):
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_primeira_observacao_registra_track_started(tmp_path):
    observer = PlaybackObserver(
        state_path=str(tmp_path / "state.json"),
        log_path=str(tmp_path / "events.jsonl"),
    )

    result = observer.observe(make_track(), context="foco")

    assert [e["event"] for e in result["events"]] == ["track_started"]
    assert result["events"][0]["context"] == "foco"


def test_pausa_registra_track_paused(tmp_path):
    observer = PlaybackObserver(str(tmp_path / "state.json"), str(tmp_path / "events.jsonl"))
    observer.observe(make_track(is_playing=True, progress_ms=10000))

    result = observer.observe(make_track(is_playing=False, progress_ms=12000))

    assert [e["event"] for e in result["events"]] == ["track_paused"]


def test_resume_registra_track_resumed(tmp_path):
    observer = PlaybackObserver(str(tmp_path / "state.json"), str(tmp_path / "events.jsonl"))
    observer.observe(make_track(is_playing=False, progress_ms=12000))

    result = observer.observe(make_track(is_playing=True, progress_ms=13000))

    assert [e["event"] for e in result["events"]] == ["track_resumed"]


def test_mudanca_rapida_enquanto_tocando_registra_skip_candidate(tmp_path):
    observer = PlaybackObserver(str(tmp_path / "state.json"), str(tmp_path / "events.jsonl"))
    observer.observe(make_track(uri="spotify:track:a", is_playing=True, progress_ms=9000))

    result = observer.observe(make_track(uri="spotify:track:b", is_playing=True, progress_ms=1000))

    assert [e["event"] for e in result["events"]] == ["skip_candidate", "track_started"]
    assert result["events"][0]["uri"] == "spotify:track:a"
    assert result["events"][1]["uri"] == "spotify:track:b"


def test_mudanca_apos_pausa_nao_registra_skip(tmp_path):
    observer = PlaybackObserver(str(tmp_path / "state.json"), str(tmp_path / "events.jsonl"))
    observer.observe(make_track(uri="spotify:track:a", is_playing=False, progress_ms=9000))

    result = observer.observe(make_track(uri="spotify:track:b", is_playing=True, progress_ms=1000))

    assert [e["event"] for e in result["events"]] == ["track_changed_after_pause", "track_started"]


def test_atingir_fim_enquanto_tocando_registra_listened_to_end_candidate(tmp_path):
    observer = PlaybackObserver(str(tmp_path / "state.json"), str(tmp_path / "events.jsonl"))
    observer.observe(make_track(is_playing=True, progress_ms=80000, duration_ms=100000))

    result = observer.observe(make_track(is_playing=True, progress_ms=91000, duration_ms=100000))

    assert [e["event"] for e in result["events"]] == ["listened_to_end_candidate"]


def test_fim_atingido_em_pausa_nao_registra_listened_to_end(tmp_path):
    observer = PlaybackObserver(str(tmp_path / "state.json"), str(tmp_path / "events.jsonl"))
    observer.observe(make_track(is_playing=False, progress_ms=80000, duration_ms=100000))

    result = observer.observe(make_track(is_playing=False, progress_ms=95000, duration_ms=100000))

    assert result["events"] == []


def test_session_end_enquanto_pausado_registra_evento_neutro(tmp_path):
    observer = PlaybackObserver(str(tmp_path / "state.json"), str(tmp_path / "events.jsonl"))
    observer.observe(make_track(is_playing=False, progress_ms=42000))

    result = observer.session_end(context="foco")

    assert [e["event"] for e in result["events"]] == ["session_ended_while_paused"]
    assert not (tmp_path / "state.json").exists()


def test_session_end_enquanto_tocando_registra_evento_neutro(tmp_path):
    observer = PlaybackObserver(str(tmp_path / "state.json"), str(tmp_path / "events.jsonl"))
    observer.observe(make_track(is_playing=True, progress_ms=42000))

    result = observer.session_end(context="foco")

    assert [e["event"] for e in result["events"]] == ["session_ended_while_playing"]


def test_eventos_sao_gravados_em_jsonl(tmp_path):
    log_path = tmp_path / "events.jsonl"
    observer = PlaybackObserver(str(tmp_path / "state.json"), str(log_path))

    observer.observe(make_track(is_playing=True, progress_ms=1000), context="foco")

    events = read_events(log_path)
    assert events[0]["event"] == "track_started"
    assert events[0]["context"] == "foco"
