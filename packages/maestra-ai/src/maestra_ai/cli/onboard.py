"""Subcomando `onboard` — stub v0.1.x (implementação real no Plano 3)."""
from __future__ import annotations

import argparse

from maestra_ai.cli import register


def cmd_onboard_stub(args):
    print("onboard: stub v0.1.0 — implementado no Plano 3")
    return 0


@register
def _register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("onboard", help="Bootstrap do perfil por histórico")
    p.add_argument("--playlist-name", default="Maestra")
    p.add_argument("--seed-playlist", type=int, default=30)
    p.set_defaults(func=cmd_onboard_stub, skip_deps=True)
