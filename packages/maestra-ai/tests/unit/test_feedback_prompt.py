"""Testes do FeedbackPrompter — microperguntas de feedback."""
import json
from datetime import datetime, timedelta

from maestra_ai.core.feedback_prompt import FeedbackPrompter
from maestra_ai.core.taste import TasteProfile


def add_signal(taste, uri, context, signal, weight, source="listened_to_end"):
    taste.record_context_signal(
        uri,
        signal,
        context=context,
        source=source,
        weight=weight,
        event_id=f"{uri}-{context}-{signal}-{source}",
    )


def test_sem_contexto_ativo_nao_sugere(tmp_path):
    taste = TasteProfile(str(tmp_path / "taste.json"))
    prompter = FeedbackPrompter(str(tmp_path / "prompt_state.json"))

    result = prompter.suggest(taste, context=None)

    assert result["should_prompt"] is False
    assert result["reason"] == "no_context"


def test_poucos_sinais_nao_sugere(tmp_path):
    taste = TasteProfile(str(tmp_path / "taste.json"))
    add_signal(taste, "spotify:track:a", "foco", "positive", 1)
    prompter = FeedbackPrompter(str(tmp_path / "prompt_state.json"), min_signals=2)

    result = prompter.suggest(taste, context="foco")

    assert result["should_prompt"] is False
    assert result["reason"] == "insufficient_signal"


def test_sugere_confirmacao_quando_sinais_positivos_predominam(tmp_path):
    taste = TasteProfile(str(tmp_path / "taste.json"))
    add_signal(taste, "spotify:track:a", "foco", "positive", 1)
    add_signal(taste, "spotify:track:b", "foco", "positive", 1)
    prompter = FeedbackPrompter(str(tmp_path / "prompt_state.json"), min_signals=2)

    result = prompter.suggest(taste, context="foco")

    assert result["should_prompt"] is True
    assert result["kind"] == "confirm_positive"
    assert "foco" in result["question"]


def test_sugere_ajuste_quando_sinais_negativos_predominam(tmp_path):
    taste = TasteProfile(str(tmp_path / "taste.json"))
    add_signal(taste, "spotify:track:a", "foco", "negative", -1, source="skip_candidate")
    add_signal(taste, "spotify:track:b", "foco", "negative", -1, source="skip_candidate")
    prompter = FeedbackPrompter(str(tmp_path / "prompt_state.json"), min_signals=2)

    result = prompter.suggest(taste, context="foco")

    assert result["should_prompt"] is True
    assert result["kind"] == "adjust_negative"


def test_cooldown_bloqueia_prompt_repetido(tmp_path):
    state_path = tmp_path / "prompt_state.json"
    state_path.write_text(json.dumps({
        "foco": {
            "last_prompt_at": datetime.now().isoformat(timespec="seconds")
        }
    }))
    taste = TasteProfile(str(tmp_path / "taste.json"))
    add_signal(taste, "spotify:track:a", "foco", "positive", 1)
    add_signal(taste, "spotify:track:b", "foco", "positive", 1)
    prompter = FeedbackPrompter(str(state_path), min_signals=2, cooldown_minutes=60)

    result = prompter.suggest(taste, context="foco")

    assert result["should_prompt"] is False
    assert result["reason"] == "cooldown"


def test_cooldown_expirado_permite_prompt(tmp_path):
    state_path = tmp_path / "prompt_state.json"
    state_path.write_text(json.dumps({
        "foco": {
            "last_prompt_at": (datetime.now() - timedelta(minutes=120)).isoformat(timespec="seconds")
        }
    }))
    taste = TasteProfile(str(tmp_path / "taste.json"))
    add_signal(taste, "spotify:track:a", "foco", "positive", 1)
    add_signal(taste, "spotify:track:b", "foco", "positive", 1)
    prompter = FeedbackPrompter(str(state_path), min_signals=2, cooldown_minutes=60)

    result = prompter.suggest(taste, context="foco")

    assert result["should_prompt"] is True


def test_cooldown_ignora_json_corrompido(tmp_path):
    path = tmp_path / "feedback_state.json"
    path.write_text("broken json")
    fp = FeedbackPrompter(str(path))
    assert not fp._in_cooldown("foco")


class TestCooldownCorrupcao:
    def test_cooldown_tolera_fromisoformat_invalido(self, tmp_path):
        """I6 v0.6.1: state corrompido não deve crashar o prompter.
        Retorna False (cooldown expirou, permite novo prompt)."""
        import json

        from maestra_ai.core.feedback_prompt import FeedbackPrompter

        state_path = tmp_path / "state.json"
        state_path.write_text(
            json.dumps({"workout": {"last_prompt_at": "banana"}}),
            encoding="utf-8",
        )
        fp = FeedbackPrompter(str(state_path), cooldown_minutes=60)
        assert fp._in_cooldown("workout") is False

    def test_cooldown_tolera_last_prompt_at_ausente(self, tmp_path):
        import json

        from maestra_ai.core.feedback_prompt import FeedbackPrompter

        state_path = tmp_path / "state.json"
        state_path.write_text(
            json.dumps({"workout": {"something_else": 1}}),
            encoding="utf-8",
        )
        fp = FeedbackPrompter(str(state_path), cooldown_minutes=60)
        assert fp._in_cooldown("workout") is False


def test_mark_prompted_registra_cooldown(tmp_path):
    state_path = tmp_path / "prompt_state.json"
    prompter = FeedbackPrompter(str(state_path))

    result = prompter.mark_prompted("foco")

    assert result["status"] == "recorded"
    assert json.loads(state_path.read_text())["foco"]["last_prompt_at"]
