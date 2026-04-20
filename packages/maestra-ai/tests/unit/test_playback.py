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


def test_load_state_ignora_json_corrompido(tmp_path):
    state_path = tmp_path / "playback_state.json"
    log_path = tmp_path / "playback_events.jsonl"
    state_path.write_text("broken json {{{")
    observer = PlaybackObserver(str(state_path), str(log_path))
    result = observer.observe({"uri": "spotify:track:abc", "is_playing": True})
    assert result["events"][0]["event"] == "track_started"


def test_eventos_sao_gravados_em_jsonl(tmp_path):
    log_path = tmp_path / "events.jsonl"
    observer = PlaybackObserver(str(tmp_path / "state.json"), str(log_path))

    observer.observe(make_track(is_playing=True, progress_ms=1000), context="foco")

    events = read_events(log_path)
    assert events[0]["event"] == "track_started"
    assert events[0]["context"] == "foco"


def test_append_events_usa_lock_e_nao_corrompe_concorrencia(tmp_path):
    """S2: _append_events deve usar lock exclusivo para evitar intercalação.

    Payloads > PIPE_BUF (~4KB) podem intercalar entre threads/processos
    concorrentes se o write for feito sem fcntl.LOCK_EX. Corrupção vira
    JSONDecodeError silencioso no PlaybackEventProcessor → perda de evento.
    """
    import threading

    log_path = tmp_path / "playback_events.jsonl"
    obs_1 = PlaybackObserver(
        state_path=str(tmp_path / "state_1.json"),
        log_path=str(log_path),
    )
    obs_2 = PlaybackObserver(
        state_path=str(tmp_path / "state_2.json"),
        log_path=str(log_path),
    )

    # Payload inflado acima de PIPE_BUF (~4KB) — nome grande força o write
    # a ultrapassar o limite POSIX de atomicidade de append.
    big_name = "a" * 5000
    event_template = {
        "event": "track_started",
        "at": "2026-04-20T00:00:00",
        "context": "concurrency-test",
        "uri": "spotify:track:" + "x" * 22,
        "track": big_name,
        "artist": "Artist",
        "is_playing": True,
        "progress_ms": 0,
        "duration_ms": 100000,
    }

    def hammer(observer, n):
        for i in range(n):
            event = dict(event_template)
            event["progress_ms"] = i
            observer._append_events([event])

    t1 = threading.Thread(target=hammer, args=(obs_1, 50))
    t2 = threading.Thread(target=hammer, args=(obs_2, 50))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 100, f"esperado 100 linhas, obtido {len(lines)}"
    for line in lines:
        # Cada linha deve ser JSON válido — intercalação quebraria aqui.
        json.loads(line)
