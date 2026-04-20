"""FeedbackPrompter — sugere microperguntas sem falar automaticamente."""
import json
import os
from datetime import datetime, timedelta

from maestra_ai.core.storage import update_json_under_lock


class FeedbackPrompter:
    """Decide se há evidência suficiente para pedir feedback ao usuário."""

    def __init__(self, state_path, min_signals=3, cooldown_minutes=45):
        self.state_path = state_path
        self.min_signals = min_signals
        self.cooldown_minutes = cooldown_minutes

    def suggest(self, taste, context):
        """Retorna uma sugestão de pergunta ou motivo para não perguntar."""
        if not context:
            return {"should_prompt": False, "reason": "no_context"}

        if self._in_cooldown(context):
            return {"should_prompt": False, "reason": "cooldown", "context": context}

        signals = self._signals_for_context(taste, context)
        if len(signals) < self.min_signals:
            return {
                "should_prompt": False,
                "reason": "insufficient_signal",
                "context": context,
                "signals": len(signals),
            }

        score = sum(self._weight(signal) for signal in signals)
        if score > 0:
            return {
                "should_prompt": True,
                "kind": "confirm_positive",
                "context": context,
                "score": score,
                "signals": len(signals),
                "question": f"A Sincronia está funcionando para {context}?",
            }
        if score < 0:
            return {
                "should_prompt": True,
                "kind": "adjust_negative",
                "context": context,
                "score": score,
                "signals": len(signals),
                "question": f"Quer que eu afaste esse tipo de faixa de {context}?",
            }

        return {
            "should_prompt": False,
            "reason": "mixed_signal",
            "context": context,
            "signals": len(signals),
            "score": score,
        }

    def mark_prompted(self, context):
        """Registra que uma pergunta foi feita para aplicar cooldown.

        Usa read-modify-write atômico para não perder marcas de outros
        contextos gravadas por processos concorrentes (daemon + CLI).
        """
        now = datetime.now().isoformat(timespec="seconds")
        update_json_under_lock(
            self.state_path,
            lambda d: {**d, context: {"last_prompt_at": now}},
        )
        return {"status": "recorded", "context": context}

    def _signals_for_context(self, taste, context):
        signals = []
        for track in taste.data.get("tracks", {}).values():
            signals.extend(
                signal
                for signal in track.get("context_signals", [])
                if signal.get("context") == context
            )
        return signals

    def _in_cooldown(self, context):
        data = self._load_state()
        entry = data.get(context)
        if not entry:
            return False
        raw = entry.get("last_prompt_at")
        if not raw:
            return False
        try:
            last_prompt_at = datetime.fromisoformat(raw)
        except (ValueError, TypeError):
            # State corrompido: trata como cooldown expirado.
            return False
        return datetime.now() - last_prompt_at < timedelta(minutes=self.cooldown_minutes)

    def _load_state(self):
        if not os.path.exists(self.state_path):
            return {}
        try:
            with open(self.state_path, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return {}
            return data
        except (json.JSONDecodeError, OSError):
            return {}

    @staticmethod
    def _weight(signal):
        if "weight" in signal and signal["weight"] is not None:
            return signal["weight"]
        value = signal.get("signal")
        if value in ("good", "positive"):
            return 1
        if value in ("bad", "skip", "negative"):
            return -1
        return 0
