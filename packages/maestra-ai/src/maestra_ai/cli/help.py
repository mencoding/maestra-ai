"""Subcomando `help <tópico>` — renderiza guias conceituais."""
from __future__ import annotations

import argparse
import re
from importlib import resources

from maestra_ai.cli import register

# S3 — defesa-em-profundidade contra path traversal no argumento `topic`.
# Nome deve começar por letra minúscula e conter apenas [a-z0-9_-].
_TOPIC_RE = re.compile(r"^[a-z][a-z0-9_-]*$")


def _topic_path(topic: str) -> str | None:
    try:
        resource = resources.files("maestra_ai").joinpath(f"docs/topics/{topic}.md")
        if resource.is_file():
            return resource.read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError):
        pass
    return None


def _list_topics() -> list[str]:
    try:
        pkg = resources.files("maestra_ai").joinpath("docs/topics")
        return sorted(
            p.name.removesuffix(".md")
            for p in pkg.iterdir()
            if p.name.endswith(".md")
        )
    except Exception:
        return []


def _handle(args: argparse.Namespace) -> int:
    if not args.topic:
        topics = _list_topics()
        if not topics:
            print("Nenhum tópico disponível.")
            return 1
        print("Tópicos disponíveis:")
        for t in topics:
            print(f"  maestra help {t}")
        return 0

    # Valida formato do tópico (letras minúsculas, dígitos, '-' e '_').
    if not _TOPIC_RE.fullmatch(args.topic):
        print(
            f"Tópico inválido: {args.topic!r}. "
            "Use letras minúsculas, dígitos, '-' ou '_'."
        )
        return 1

    content = _topic_path(args.topic)
    if not content:
        print(f"Tópico '{args.topic}' não encontrado.")
        available = _list_topics()
        if available:
            print(f"Disponíveis: {', '.join(available)}")
        return 1

    try:
        from rich.console import Console
        from rich.markdown import Markdown
        Console().print(Markdown(content))
    except ImportError:
        print(content)
    return 0


@register
def _register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("help", help="Guia conceitual por tópico")
    p.add_argument("topic", nargs="?", default=None, help="Nome do tópico")
    p.set_defaults(func=_handle, skip_deps=True)
