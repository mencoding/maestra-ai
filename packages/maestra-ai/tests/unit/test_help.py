"""Testes do subcomando help — tópicos renderizáveis via importlib.resources."""
from __future__ import annotations

from maestra_ai.cli.help import _list_topics, _topic_path


def test_list_topics_inclui_onboarding():
    topics = _list_topics()
    assert "onboarding" in topics


def test_topic_path_onboarding_retorna_conteudo():
    content = _topic_path("onboarding")
    assert content is not None
    assert "Onboarding" in content
    assert "auth setup" in content


def test_topic_path_inexistente_retorna_none():
    assert _topic_path("tópico-que-não-existe") is None
