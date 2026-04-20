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
from maestra_ai.core.config import (
    any_source_enabled,
    delete_source_key,
    get_source_key,
    migrate_external_sources,
    normalize_playlist_id,
    set_source_key,
    source_enabled,
)

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
            "enabled": any_source_enabled(cfg),
            "per_source": {
                "musicbrainz": {"enabled": source_enabled(cfg, "musicbrainz")},
                "lastfm": {
                    "enabled": source_enabled(cfg, "lastfm"),
                    "has_key": get_source_key("lastfm") is not None,
                },
                "getsongbpm": {
                    "enabled": source_enabled(cfg, "getsongbpm"),
                    "has_key": get_source_key("getsongbpm") is not None,
                },
            },
        },
        getattr(args, "human", False),
    )


def cmd_config_external_enable(args, **_):
    cfg = storage.read_config()
    cfg = migrate_external_sources(cfg)
    cfg["external_sources"]["musicbrainz"]["enabled"] = True
    storage.write_config(cfg)
    output({"status": "enabled"}, getattr(args, "human", False))


def cmd_config_external_disable(args, **_):
    cfg = storage.read_config()
    cfg = migrate_external_sources(cfg)
    cfg["external_sources"]["musicbrainz"]["enabled"] = False
    storage.write_config(cfg)
    output({"status": "disabled"}, getattr(args, "human", False))


# --- Sources com chave de API ---

_VALID_KEYED_SOURCES = ("lastfm", "getsongbpm")


def _load_cfg() -> dict:
    """Carrega config.json pelo path canônico (monkeypatchável via storage.config_path)."""
    import json as _json
    path = storage.config_path()
    try:
        return _json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}


def _save_cfg(cfg: dict) -> None:
    """Persiste config.json de forma atômica pelo path canônico."""
    storage.atomic_write_json(storage.config_path(), cfg)


def _ensure_nested(cfg: dict) -> dict:
    return migrate_external_sources(cfg)


def cmd_config_external_set_key(args, **_):
    source = args.source
    if source not in _VALID_KEYED_SOURCES:
        output({"error": f"source inválido: {source}. Use um de {_VALID_KEYED_SOURCES}"}, getattr(args, "human", False))
        return
    try:
        set_source_key(source, args.key)
    except Exception as exc:
        output({"error": f"falha ao gravar no keyring: {exc}"}, getattr(args, "human", False))
        return
    cfg = _load_cfg()
    cfg = _ensure_nested(cfg)
    # Garantir que não haja api_key em plaintext após gravar no keyring
    cfg["external_sources"][source].pop("api_key", None)
    cfg["external_sources"][source]["enabled"] = True
    _save_cfg(cfg)
    output({"status": "set", "source": source, "enabled": True}, getattr(args, "human", False))


def cmd_config_external_clear_key(args, **_):
    source = args.source
    if source not in _VALID_KEYED_SOURCES:
        output({"error": f"source inválido: {source}"}, getattr(args, "human", False))
        return
    delete_source_key(source)
    cfg = _load_cfg()
    cfg = _ensure_nested(cfg)
    cfg["external_sources"][source].pop("api_key", None)
    cfg["external_sources"][source]["enabled"] = False
    _save_cfg(cfg)
    output({"status": "cleared", "source": source}, getattr(args, "human", False))


def cmd_config_external_enable_source(args, **_):
    source = args.source
    cfg = _load_cfg()
    cfg = _ensure_nested(cfg)
    if source in _VALID_KEYED_SOURCES and get_source_key(source) is None:
        output({"error": f"{source} precisa de API key. Use 'maestra config external set-key {source} <key>' ou 'guide {source}'."}, getattr(args, "human", False))
        return
    cfg["external_sources"][source]["enabled"] = True
    _save_cfg(cfg)
    output({"status": "enabled", "source": source}, getattr(args, "human", False))


def cmd_config_external_disable_source(args, **_):
    source = args.source
    cfg = _load_cfg()
    cfg = _ensure_nested(cfg)
    cfg["external_sources"][source]["enabled"] = False
    _save_cfg(cfg)
    output({"status": "disabled", "source": source}, getattr(args, "human", False))


def cmd_config_external_guide(args, **_):
    source = args.source
    from maestra_ai.core.external.setup_guides import guide_getsongbpm, guide_lastfm
    guides = {"lastfm": guide_lastfm, "getsongbpm": guide_getsongbpm}
    if source not in guides:
        output({"error": f"source inválido: {source}"}, getattr(args, "human", False))
        return
    enabled, key = guides[source]()
    if not enabled:
        output({"status": "skipped", "source": source}, getattr(args, "human", False))
        return
    if key:
        try:
            set_source_key(source, key)
        except Exception as exc:
            output({"error": f"falha ao gravar no keyring: {exc}"}, getattr(args, "human", False))
            return
    cfg = _load_cfg()
    cfg = _ensure_nested(cfg)
    cfg["external_sources"][source].pop("api_key", None)
    cfg["external_sources"][source]["enabled"] = True
    _save_cfg(cfg)
    output({"status": "configured", "source": source}, getattr(args, "human", False))


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

    p = ext_sub.add_parser("enable", help="Ativa fontes externas (bulk: musicbrainz)")
    p.add_argument("--human", action="store_true")
    p.set_defaults(func=cmd_config_external_enable, skip_deps=True)

    p = ext_sub.add_parser("disable", help="Desativa fontes externas (bulk: musicbrainz)")
    p.add_argument("--human", action="store_true")
    p.set_defaults(func=cmd_config_external_disable, skip_deps=True)

    p = ext_sub.add_parser("set-key", help="Define API key de uma source (lastfm ou getsongbpm)")
    p.add_argument("source", choices=["lastfm", "getsongbpm"])
    p.add_argument("key")
    p.set_defaults(func=cmd_config_external_set_key, skip_deps=True)

    p = ext_sub.add_parser("clear-key", help="Remove API key e desativa a source")
    p.add_argument("source", choices=["lastfm", "getsongbpm"])
    p.set_defaults(func=cmd_config_external_clear_key, skip_deps=True)

    p = ext_sub.add_parser("guide", help="Roda guia interativo de configuração")
    p.add_argument("source", choices=["lastfm", "getsongbpm"])
    p.set_defaults(func=cmd_config_external_guide, skip_deps=True)

    p = ext_sub.add_parser("enable-source", help="Ativa uma source específica")
    p.add_argument("source", choices=["musicbrainz", "lastfm", "getsongbpm"])
    p.set_defaults(func=cmd_config_external_enable_source, skip_deps=True)

    p = ext_sub.add_parser("disable-source", help="Desativa uma source específica")
    p.add_argument("source", choices=["musicbrainz", "lastfm", "getsongbpm"])
    p.set_defaults(func=cmd_config_external_disable_source, skip_deps=True)
