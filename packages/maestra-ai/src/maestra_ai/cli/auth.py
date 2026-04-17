"""Subcomando `auth` — stub v0.1.x (implementação real no Plano 3)."""
from __future__ import annotations

import argparse

from maestra_ai.cli import register


def cmd_auth_stub(args):
    print(f"auth {args.auth_command}: stub v0.1.0 — implementado no Plano 3")
    return 0


@register
def _register(subparsers: argparse._SubParsersAction) -> None:
    auth_parser = subparsers.add_parser("auth", help="Autenticação Spotify")
    sub = auth_parser.add_subparsers(dest="auth_command", required=True)
    p = sub.add_parser("setup", help="Configura client_id/secret")
    p.set_defaults(func=cmd_auth_stub, skip_deps=True)
    p = sub.add_parser("login", help="Autentica via OAuth")
    p.set_defaults(func=cmd_auth_stub, skip_deps=True)
