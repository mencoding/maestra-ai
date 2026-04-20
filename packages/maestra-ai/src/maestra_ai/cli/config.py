"""Subcomando `config`: get, set, list.

Gerencia ~/.config/maestra/config.json sem tocar em credenciais sensíveis
expostas em plain (secrets são mascarados no `list`). Normaliza
`playlist_id` via `core.config.normalize_playlist_id` antes de gravar.
"""
from __future__ import annotations

import argparse
import json
import sys

from maestra_ai.cli import register
from maestra_ai.cli._common import output
from maestra_ai.core import storage
from maestra_ai.core.audit import _redact
from maestra_ai.core.config import normalize_playlist_id

# Keys permitidas no `set`. Qualquer outra é rejeitada com lista.
_ALLOWED_KEYS: tuple[str, ...] = (
    "client_id",
    "client_secret",
    "redirect_uri",
    "playlist_id",
    "playlist_name",
)


def cmd_config_list(args, **_):
    """Imprime config.json com secrets redactados."""
    cfg = storage.read_config()
    redacted = _redact(cfg)
    output(redacted, getattr(args, "human", False))


def cmd_config_get(args, **_):
    """Retorna o valor de uma key. Para playlist_id, normaliza o retorno."""
    cfg = storage.read_config()
    value = cfg.get(args.key)
    # Se for playlist_id e houver valor, garante que saia já normalizado
    # (config pode ter sido escrito manualmente com URL/URI legada).
    if args.key == "playlist_id" and value:
        try:
            value = normalize_playlist_id(value)
        except ValueError:
            # Mantém o valor bruto se não casar — o `doctor` reportaria.
            pass
    output(value, getattr(args, "human", False))


def cmd_config_set(args, **_):
    """Grava uma key no config.json com validação."""
    key = args.key
    value = args.value

    if key not in _ALLOWED_KEYS:
        allowed = ", ".join(_ALLOWED_KEYS)
        print(
            json.dumps(
                {
                    "error": f"key desconhecida: {key!r}. Keys aceitas: {allowed}",
                    "code": "INVALID_KEY",
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        sys.exit(1)

    if key == "playlist_id":
        try:
            value = normalize_playlist_id(value)
        except ValueError as e:
            print(
                json.dumps(
                    {"error": str(e), "code": "INVALID_PLAYLIST_ID"},
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )
            sys.exit(1)

    cfg = storage.read_config()
    cfg[key] = value
    storage.write_config(cfg)
    output({"status": "set", "key": key}, getattr(args, "human", False))


def cmd_config_external_status(args, **_):
    cfg = storage.read_config()
    output(
        {
            "enabled": bool(cfg.get("external_sources_enabled")),
            "musicbrainz": "available",
        },
        getattr(args, "human", False),
    )


def cmd_config_external_enable(args, **_):
    cfg = storage.read_config()
    cfg["external_sources_enabled"] = True
    storage.write_config(cfg)
    output({"status": "enabled"}, getattr(args, "human", False))


def cmd_config_external_disable(args, **_):
    cfg = storage.read_config()
    cfg["external_sources_enabled"] = False
    storage.write_config(cfg)
    output({"status": "disabled"}, getattr(args, "human", False))


@register
def _register(subparsers: argparse._SubParsersAction) -> None:
    from maestra_ai.cli import group_help_handler
    config_parser = subparsers.add_parser("config", help="Gerencia config.json")
    config_parser.set_defaults(func=group_help_handler(config_parser))
    sub = config_parser.add_subparsers(dest="config_command", required=False)

    p = sub.add_parser("list", help="Lista todas as keys (secrets redactados)")
    p.set_defaults(func=cmd_config_list, skip_deps=True)

    p = sub.add_parser("get", help="Lê o valor de uma key")
    p.add_argument("key", help="Nome da key")
    p.set_defaults(func=cmd_config_get, skip_deps=True)

    p = sub.add_parser("set", help="Grava uma key")
    p.add_argument("key", help=f"Keys aceitas: {', '.join(_ALLOWED_KEYS)}")
    p.add_argument("value", help="Valor a gravar")
    p.set_defaults(func=cmd_config_set, skip_deps=True)

    ext = sub.add_parser("external", help="Fontes externas de metadata")
    ext.set_defaults(func=group_help_handler(ext))
    ext_sub = ext.add_subparsers(dest="config_external_command", required=False)

    p = ext_sub.add_parser("status", help="Mostra estado das fontes externas")
    p.add_argument("--human", action="store_true")
    p.set_defaults(func=cmd_config_external_status, skip_deps=True)

    p = ext_sub.add_parser("enable", help="Ativa fontes externas")
    p.add_argument("--human", action="store_true")
    p.set_defaults(func=cmd_config_external_enable, skip_deps=True)

    p = ext_sub.add_parser("disable", help="Desativa fontes externas")
    p.add_argument("--human", action="store_true")
    p.set_defaults(func=cmd_config_external_disable, skip_deps=True)
