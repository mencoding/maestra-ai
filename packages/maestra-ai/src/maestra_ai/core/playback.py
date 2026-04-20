"""PlaybackObserver — registro conservador de eventos de playback."""
import json
import os
from datetime import datetime

from maestra_ai.core.storage import append_jsonl_locked, atomic_write_json


class PlaybackObserver:
    """Detecta transições de playback sem inferir gosto musical."""

    def __init__(
        self,
        state_path,
        log_path,
        skip_threshold_ms=15000,
        end_ratio=0.9,
    ):
        self.state_path = state_path
        self.log_path = log_path
        self.skip_threshold_ms = skip_threshold_ms
        self.end_ratio = end_ratio

    def observe(self, current, context=None):
        """Observa o estado atual e registra eventos neutros/candidatos."""
        previous = self._load_state()
        events = self._detect_events(previous, current, context)
        self._append_events(events)
        self._save_state(current)
        return {"events": events}

    def session_end(self, context=None):
        """Registra encerramento de sessão sem converter em sinal de gosto."""
        previous = self._load_state()
        events = []

        if previous:
            event_name = (
                "session_ended_while_playing"
                if previous.get("is_playing")
                else "session_ended_while_paused"
            )
            events.append(self._event(event_name, previous, context=context))

        self._append_events(events)
        self._clear_state()
        return {"events": events}

    def _detect_events(self, previous, current, context):
        if current is None:
            if previous is None:
                return []
            return [self._event("playback_unavailable", previous, context=context)]

        if previous is None:
            return [self._event("track_started", current, context=context)]

        if previous.get("uri") != current.get("uri"):
            events = []
            if previous.get("is_playing") and self._progress(previous) < self.skip_threshold_ms:
                events.append(self._event("skip_candidate", previous, context=context))
            elif not previous.get("is_playing"):
                events.append(self._event("track_changed_after_pause", previous, context=context))
            else:
                events.append(self._event("track_changed", previous, context=context))
            events.append(self._event("track_started", current, context=context))
            return events

        if previous.get("is_playing") and not current.get("is_playing"):
            return [self._event("track_paused", current, context=context)]

        if not previous.get("is_playing") and current.get("is_playing"):
            return [self._event("track_resumed", current, context=context)]

        if self._crossed_end_threshold(previous, current):
            return [self._event("listened_to_end_candidate", current, context=context)]

        return []

    def _crossed_end_threshold(self, previous, current):
        if not current.get("is_playing"):
            return False

        duration = current.get("duration_ms") or 0
        if duration <= 0:
            return False

        threshold = duration * self.end_ratio
        return self._progress(previous) < threshold <= self._progress(current)

    @staticmethod
    def _progress(track):
        return track.get("progress_ms") or 0

    def _event(self, name, track, context=None):
        return {
            "event": name,
            "at": datetime.now().isoformat(timespec="seconds"),
            "context": context,
            "uri": track.get("uri"),
            "track": track.get("track"),
            "artist": track.get("artist"),
            "is_playing": track.get("is_playing"),
            "progress_ms": track.get("progress_ms"),
            "duration_ms": track.get("duration_ms"),
        }

    def _load_state(self):
        if not os.path.exists(self.state_path):
            return None
        try:
            with open(self.state_path, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return None
            return data
        except (json.JSONDecodeError, OSError):
            return None

    def _save_state(self, current):
        if current is None:
            self._clear_state()
            return
        atomic_write_json(self.state_path, current)

    def _clear_state(self):
        if os.path.exists(self.state_path):
            os.remove(self.state_path)

    def _append_events(self, events):
        # S2: delega para append_jsonl_locked (fcntl.LOCK_EX) — serializa
        # writes entre processos concorrentes (daemon director + CLI manual).
        # Sem o lock, payloads > PIPE_BUF (~4KB) podem intercalar e corromper
        # linhas do JSONL, gerando JSONDecodeError silencioso no
        # PlaybackEventProcessor (perda de evento).
        if not events:
            return
        for event in events:
            append_jsonl_locked(self.log_path, event)
