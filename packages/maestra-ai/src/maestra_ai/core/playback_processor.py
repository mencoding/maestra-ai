"""PlaybackEventProcessor — converte eventos observados em sinais contextuais."""
import hashlib
import json
import os


EVENT_RULES = {
    "listened_to_end_candidate": {
        "signal": "positive",
        "source": "listened_to_end",
        "weight": 1,
    },
    "skip_candidate": {
        "signal": "negative",
        "source": "skip_candidate",
        "weight": -1,
    },
}


class PlaybackEventProcessor:
    """Processa eventos de playback sem alterar feedback global."""

    def __init__(self, log_path, taste):
        self.log_path = log_path
        self.taste = taste

    def process(self):
        """Converte eventos elegíveis em sinais contextuais idempotentes."""
        processed = 0
        ignored = 0

        for event in self._read_events():
            rule = EVENT_RULES.get(event.get("event"))
            if not rule or not event.get("context") or not event.get("uri"):
                ignored += 1
                continue

            changed = self.taste.record_context_signal(
                event["uri"],
                rule["signal"],
                context=event["context"],
                source=rule["source"],
                event_id=self._event_id(event),
                weight=rule["weight"],
                at=event.get("at"),
            )
            if changed:
                processed += 1
            else:
                ignored += 1

        return {"processed": processed, "ignored": ignored}

    def _read_events(self):
        if not os.path.exists(self.log_path):
            return []

        events = []
        with open(self.log_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                events.append(json.loads(line))
        return events

    @staticmethod
    def _event_id(event):
        canonical = json.dumps(event, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
