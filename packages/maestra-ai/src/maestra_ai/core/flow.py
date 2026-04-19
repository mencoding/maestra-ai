"""FlowAnalyzer — detecta deriva negativa no fluxo musical."""
from collections import Counter

NEGATIVE_SIGNALS = {"bad", "skip", "negative"}
POSITIVE_SIGNALS = {"good", "positive"}
STYLE_TERMS = (
    "foco",
    "concentração",
    "concentracao",
    "tdah",
    "estudo",
    "estudar",
    "study",
    "lo-fi",
    "lofi",
    "dark",
    "ambient",
    "academia",
    "neoclassical",
    "classical",
    "coding",
)


class FlowAnalyzer:
    """Analisa sinais recentes de gosto para detectar contaminação do fluxo."""

    def __init__(self, taste):
        self.taste = taste

    def review(self, context, window=10, streak_threshold=3, negative_rate_threshold=0.3):
        signals = self._context_signals(context)
        recent = signals[-window:]
        negative = [item for item in recent if item["signal"] in NEGATIVE_SIGNALS]
        positive = [item for item in recent if item["signal"] in POSITIVE_SIGNALS]
        negative_streak = self._negative_streak(recent)
        negative_rate = round(len(negative) / len(recent), 2) if recent else 0.0
        drift = (
            negative_streak >= streak_threshold
            or (len(recent) >= max(3, streak_threshold) and negative_rate >= negative_rate_threshold)
        )

        return {
            "context": context,
            "window": window,
            "signals_considered": len(recent),
            "positive": len(positive),
            "negative": len(negative),
            "negative_rate": negative_rate,
            "negative_streak": negative_streak,
            "streak_threshold": streak_threshold,
            "negative_rate_threshold": negative_rate_threshold,
            "status": "drift_detected" if drift else "stable",
            "common_negative_artists": self._common_artists(negative),
            "common_negative_terms": self._common_terms(negative),
            "recent": recent,
            "recommended_action": self._recommended_action(drift, negative_streak, negative_rate),
            "note": "Leitura apenas; nenhuma playlist ou memória foi alterada.",
        }

    def _context_signals(self, context):
        items = []
        for uri, track in self.taste.data.get("tracks", {}).items():
            for signal in track.get("context_signals", []):
                if signal.get("context") != context:
                    continue
                items.append({
                    "at": signal.get("at") or "",
                    "uri": uri,
                    "track": track.get("name", "unknown"),
                    "artist": track.get("artist", "unknown"),
                    "signal": signal.get("signal"),
                    "source": signal.get("source"),
                    "weight": signal.get("weight"),
                })
        return sorted(items, key=lambda item: item["at"])

    def _negative_streak(self, signals):
        streak = 0
        for item in reversed(signals):
            if item["signal"] in NEGATIVE_SIGNALS:
                streak += 1
                continue
            break
        return streak

    def _common_artists(self, signals):
        return [
            {"artist": artist, "count": count}
            for artist, count in Counter(item["artist"] for item in signals).most_common(10)
        ]

    def _common_terms(self, signals):
        counter = Counter()
        for item in signals:
            text = f"{item['track']} {item['artist']}".lower()
            for term in STYLE_TERMS:
                if term in text:
                    counter[term] += 1
        return [
            {"term": term, "count": count}
            for term, count in counter.most_common(10)
        ]

    @staticmethod
    def _recommended_action(drift, negative_streak, negative_rate):
        if not drift:
            return "continue_observing"
        if negative_streak >= 3:
            return "pause_director_and_review_recent_style"
        if negative_rate >= 0.3:
            return "run_taste_review_and_prune_candidates"
        return "review_context"
