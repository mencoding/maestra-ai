"""Testes do subcomando help — tópicos renderizáveis via importlib.resources."""
from __future__ import annotations

import argparse

from maestra_ai.cli.help import _handle, _list_topics, _topic_path


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


# ---------------------------------------------------------------------------
# S3 — validação de topic (defesa-em-profundidade contra path traversal)
# ---------------------------------------------------------------------------


def test_help_rejeita_topic_com_traversal(capsys):
    args = argparse.Namespace(topic="../cli/__init__")
    rc = _handle(args)
    assert rc != 0
    captured = capsys.readouterr()
    out = captured.out + captured.err
    assert "inválid" in out.lower() or "invalid" in out.lower()


def test_help_rejeita_topic_absoluto_e_maiusculas(capsys):
    for topic in ["/etc/passwd", "FOO_BAR", "topic.with.dots", "a/b"]:
        args = argparse.Namespace(topic=topic)
        rc = _handle(args)
        assert rc != 0, f"deveria rejeitar topic={topic!r}"
        captured = capsys.readouterr()
        out = captured.out + captured.err
        assert "inválid" in out.lower() or "invalid" in out.lower(), (
            f"esperava mensagem de inválido para topic={topic!r}, saiu={out!r}"
        )
