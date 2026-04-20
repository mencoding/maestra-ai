"""CLI entry para `maestra init` — wizard unificado de configuração.

Substitui `onboard` em v0.9. Delega toda a lógica para `core.init`:
detecta estado, orquestra fluxos A/A2/B/C e retorna `InitReport`.

Flags:
  --auto    Roda sem prompts (exige estado B ou C).
  --json    Saída estruturada JSON (implica --auto).
"""
from __future__ import annotations

import argparse
import json as _json

from maestra_ai.cli import register


@register
def register_parser(subparsers: argparse._SubParsersAction) -> None:
    """Registra o subcomando `init` no parser raiz."""
    p = subparsers.add_parser(
        "init",
        help="Wizard guiado de configuração e análise (substitui onboard em v0.9).",
        description=(
            "Configura Maestra passo a passo. Detecta estado atual e continua "
            "do ponto onde você parou. Use --auto para rodar sem prompts."
        ),
    )
    p.add_argument(
        "--auto",
        action="store_true",
        help="Roda sem prompts (requer estado B ou C).",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Saída estruturada JSON (implica --auto).",
    )
    # `init` não precisa de deps montadas pelo pipeline central — o core
    # constrói seus próprios clientes conforme o fluxo escolhido.
    p.set_defaults(func=_handle, skip_deps=True)


def _handle(args: argparse.Namespace) -> int:
    from maestra_ai.core import init as init_mod

    # --json implica --auto (saída para agentes, sem prompts).
    auto = bool(getattr(args, "auto", False) or getattr(args, "json", False))
    want_json = bool(getattr(args, "json", False))
    try:
        if auto:
            report = init_mod.run_auto()
        else:
            report = init_mod.run_interactive()
    except init_mod.UserAbort as e:
        if want_json:
            print(_json.dumps({"error": str(e)}, ensure_ascii=False))
        return 1

    if want_json:
        print(_json.dumps(dict(report), ensure_ascii=False, default=str))
    return 0
