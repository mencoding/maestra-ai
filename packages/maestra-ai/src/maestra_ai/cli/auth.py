"""Subcomandos `auth setup` e `auth login` — fluxo OAuth paste-back."""
from __future__ import annotations

import argparse
import json
import sys
import webbrowser

from maestra_ai.cli import register
from maestra_ai.core import auth
from maestra_ai.core.errors import NonInteractiveError


def _handle_setup(args: argparse.Namespace) -> int:
    cid = args.client_id
    sec = args.client_secret
    redirect = args.redirect_uri

    if not cid or not sec or not redirect:
        if not sys.stdin.isatty():
            raise NonInteractiveError(
                "Faltam credenciais e stdin não é interativo. "
                "Passe --client-id, --client-secret e --redirect-uri "
                "explicitamente.",
            )
        try:
            from rich.prompt import Prompt
            cid = cid or Prompt.ask("Cole seu Spotify client_id")
            sec = sec or Prompt.ask("Cole seu Spotify client_secret", password=True)
            redirect = redirect or Prompt.ask(
                "Redirect URI registrado no app (ex: https://example.com/callback)",
            )
        except ImportError:
            cid = cid or input("client_id: ").strip()
            sec = sec or input("client_secret: ").strip()
            redirect = redirect or input("redirect_uri: ").strip()

    result = auth.setup(client_id=cid, client_secret=sec, redirect_uri=redirect)

    if getattr(args, "json", False):
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"✓ Credenciais salvas em {result['config_path']}")
    return 0


def _handle_login(args: argparse.Namespace) -> int:
    def pasted_getter(auth_url: str) -> str:
        print()
        print("Abra a URL abaixo no navegador (tentando abrir automaticamente):")
        print(f"  {auth_url}")
        print()
        print(
            "Após autorizar, o Spotify redireciona pro seu redirect_uri.\n"
            "Copie a URL COMPLETA da barra do navegador (mesmo se der 404)\n"
            "e cole aqui. Alternativamente, só o valor do parâmetro ?code= serve.",
        )
        print()
        try:
            from rich.prompt import Prompt
            return Prompt.ask("URL ou code")
        except ImportError:
            return input("URL ou code: ").strip()

    result = auth.login(
        pasted_url_getter=pasted_getter,
        browser_opener=webbrowser.open,
    )

    if getattr(args, "json", False):
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("✓ Autenticação Spotify concluída.")
        print(f"  Scopes: {result['scopes']}")
    return 0


@register
def _register(subparsers: argparse._SubParsersAction) -> None:
    auth_p = subparsers.add_parser("auth", help="Autenticação Spotify")
    sub = auth_p.add_subparsers(dest="auth_command", required=True)

    setup_p = sub.add_parser("setup", help="Configura client_id/secret")
    setup_p.add_argument("--client-id", default=None)
    setup_p.add_argument("--client-secret", default=None)
    setup_p.add_argument(
        "--redirect-uri",
        default=None,
        help="URL HTTPS registrada no app Spotify. "
        "Spotify rejeita localhost/127.0.0.1 em apps criados após 2025.",
    )
    setup_p.add_argument("--json", action="store_true")
    setup_p.set_defaults(func=_handle_setup, skip_deps=True)

    login_p = sub.add_parser("login", help="Autentica via OAuth (paste-back)")
    login_p.add_argument("--json", action="store_true")
    login_p.set_defaults(func=_handle_login, skip_deps=True)
