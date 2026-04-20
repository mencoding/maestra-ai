"""ContextState — contexto musical ativo com target de BPM opcional.

v0.10: campo `context` passa a ser objeto `{text: str, bpm: {min, max} | None}`.
Migração automática e silenciosa no load quando o arquivo contém string legacy.
"""
import json
import os
from datetime import datetime, timedelta

from maestra_ai.core.storage import atomic_write_json

_BPM_MIN = 30
_BPM_MAX = 220


def validate_bpm_range(bpm: dict | None) -> bool:
    if bpm is None:
        return True
    if not isinstance(bpm, dict):
        return False
    lo = bpm.get("min")
    hi = bpm.get("max")
    if not isinstance(lo, int) or not isinstance(hi, int):
        return False
    if lo < _BPM_MIN or hi > _BPM_MAX:
        return False
    if lo >= hi:
        return False
    return True


def _normalize_context_field(raw) -> dict:
    """Aceita str (legacy) ou dict; retorna sempre {text, bpm}."""
    if isinstance(raw, str):
        return {"text": raw, "bpm": None}
    if isinstance(raw, dict):
        text = raw.get("text") or ""
        bpm = raw.get("bpm")
        if bpm is not None and not validate_bpm_range(bpm):
            bpm = None
        return {"text": text, "bpm": bpm}
    return {"text": "", "bpm": None}


class ContextState:
    def __init__(self, path):
        self.path = path

    def set(self, text: str, bpm: dict | None = None, ttl_minutes: int = 120):
        current = self._read_raw()
        previous = _normalize_context_field((current or {}).get("context"))

        if bpm is None:
            effective_bpm = previous["bpm"] if previous["text"] == text else None
        else:
            if not validate_bpm_range(bpm):
                raise ValueError(f"BPM range inválido: {bpm}")
            effective_bpm = bpm

        data = {
            "context": {"text": text, "bpm": effective_bpm},
            "set_at": datetime.now().isoformat(timespec="seconds"),
            "ttl_minutes": ttl_minutes,
        }
        atomic_write_json(self.path, data)
        return data

    def set_bpm(self, bpm: dict):
        current = self._read_raw() or {}
        previous = _normalize_context_field(current.get("context"))
        if not previous["text"]:
            raise ValueError("nenhum contexto ativo — use 'maestra context set' primeiro")
        return self.set(previous["text"], bpm=bpm)

    def clear_bpm(self):
        current = self._read_raw() or {}
        previous = _normalize_context_field(current.get("context"))
        if not previous["text"]:
            return {"status": "no-context"}
        data = {
            "context": {"text": previous["text"], "bpm": None},
            "set_at": datetime.now().isoformat(timespec="seconds"),
            "ttl_minutes": current.get("ttl_minutes", 120),
        }
        atomic_write_json(self.path, data)
        return data

    def show(self):
        data = self._read_raw()
        if data is None:
            return None
        ttl = data.get("ttl_minutes")
        try:
            set_at = datetime.fromisoformat(data["set_at"])
        except (ValueError, KeyError, TypeError):
            self.clear()
            return None
        if ttl is not None and datetime.now() - set_at > timedelta(minutes=ttl):
            self.clear()
            return None
        data["context"] = _normalize_context_field(data.get("context"))
        return data

    def clear(self):
        if os.path.exists(self.path):
            os.remove(self.path)
        return {"status": "cleared"}

    def _read_raw(self) -> dict | None:
        if not os.path.exists(self.path):
            return None
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict) or "context" not in data or "set_at" not in data:
                return None
            return data
        except (json.JSONDecodeError, OSError):
            return None
