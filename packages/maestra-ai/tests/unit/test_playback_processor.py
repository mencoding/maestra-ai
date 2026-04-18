"""Testes do PlaybackEventProcessor — eventos para sinais de gosto."""
import json

from maestra_ai.core.playback_processor import PlaybackEventProcessor
from maestra_ai.core.taste import TasteProfile


def append_event(path, event):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def make_event(event, uri="spotify:track:a", context="foco"):
    return {
        "event": event,
        "at": "2026-04-16T10:00:00",
        "context": context,
        "uri": uri,
        "track": "Track A",
        "artist": "Artist A",
        "is_playing": True,
        "progress_ms": 90000,
        "duration_ms": 100000,
    }


def test_listened_to_end_vira_sinal_positivo(tmp_path):
    log_path = tmp_path / "events.jsonl"
    taste = TasteProfile(str(tmp_path / "taste.json"))
    append_event(log_path, make_event("listened_to_end_candidate"))

    result = PlaybackEventProcessor(str(log_path), taste).process()

    signals = taste.get_context_signals("spotify:track:a", context="foco")
    assert result["processed"] == 1
    assert signals[0]["signal"] == "positive"
    assert signals[0]["source"] == "listened_to_end"
    assert signals[0]["weight"] == 1


def test_skip_candidate_vira_sinal_negativo_fraco_contextual(tmp_path):
    log_path = tmp_path / "events.jsonl"
    taste = TasteProfile(str(tmp_path / "taste.json"))
    append_event(log_path, make_event("skip_candidate"))

    result = PlaybackEventProcessor(str(log_path), taste).process()

    signals = taste.get_context_signals("spotify:track:a", context="foco")
    assert result["processed"] == 1
    assert signals[0]["signal"] == "negative"
    assert signals[0]["source"] == "skip_candidate"
    assert signals[0]["weight"] == -1
    assert taste.data["tracks"]["spotify:track:a"]["feedback"] is None


def test_eventos_neutros_sao_ignorados(tmp_path):
    log_path = tmp_path / "events.jsonl"
    taste = TasteProfile(str(tmp_path / "taste.json"))
    append_event(log_path, make_event("track_paused"))
    append_event(log_path, make_event("session_ended_while_paused"))

    result = PlaybackEventProcessor(str(log_path), taste).process()

    assert result["processed"] == 0
    assert taste.get_context_signals("spotify:track:a") == []


def test_evento_sem_contexto_nao_vira_sinal(tmp_path):
    log_path = tmp_path / "events.jsonl"
    taste = TasteProfile(str(tmp_path / "taste.json"))
    append_event(log_path, make_event("listened_to_end_candidate", context=None))

    result = PlaybackEventProcessor(str(log_path), taste).process()

    assert result["processed"] == 0
    assert taste.get_context_signals("spotify:track:a") == []


def test_linha_malformada_pulada_sem_abortar(tmp_path):
    """P0-N2: linha com JSON inválido no meio do JSONL não deve abortar o loop."""
    log_path = tmp_path / "events.jsonl"
    taste = TasteProfile(str(tmp_path / "taste.json"))
    append_event(log_path, make_event("listened_to_end_candidate", uri="spotify:track:a"))
    with open(log_path, "a", encoding="utf-8") as f:
        f.write("{linha quebrada sem fechar\n")
    append_event(log_path, make_event("listened_to_end_candidate", uri="spotify:track:b"))

    result = PlaybackEventProcessor(str(log_path), taste).process()

    # linha ruim é ignorada; 2 eventos válidos processados
    assert result["processed"] == 2


def test_linha_nao_dict_ignorada(tmp_path):
    """P0-N2: linha com JSON válido mas não-dict (ex: lista) deve ser ignorada."""
    log_path = tmp_path / "events.jsonl"
    taste = TasteProfile(str(tmp_path / "taste.json"))
    with open(log_path, "a", encoding="utf-8") as f:
        f.write('[1, 2, 3]\n')
    append_event(log_path, make_event("listened_to_end_candidate"))

    result = PlaybackEventProcessor(str(log_path), taste).process()

    assert result["processed"] == 1


def test_processamento_e_idempotente(tmp_path):
    log_path = tmp_path / "events.jsonl"
    taste = TasteProfile(str(tmp_path / "taste.json"))
    append_event(log_path, make_event("listened_to_end_candidate"))
    processor = PlaybackEventProcessor(str(log_path), taste)

    first = processor.process()
    second = processor.process()

    signals = taste.get_context_signals("spotify:track:a")
    assert first["processed"] == 1
    assert second["processed"] == 0
    assert len(signals) == 1
