"""Subcomando doctor."""
from __future__ import annotations

import argparse
import json

from maestra_ai.cli import register
from maestra_ai.core import doctor

_STATUS_SYMBOL = {"ok": "✓", "warning": "⚠", "error": "✗"}


def _handle(args: argparse.Namespace) -> int:
    # HIGH-3: reset manual do circuit breaker persistente.
    if getattr(args, "reset_breaker", False):
        from maestra_ai.core.ratelimit import reset_breaker
        reset_breaker()
        print("[OK] Circuit breaker resetado.")
        return 0
    results = doctor.run_all()
    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        try:
            from rich.console import Console
            from rich.table import Table
            console = Console()
            table = Table(title="Maestra Doctor")
            table.add_column("Check")
            table.add_column("Status")
            table.add_column("Mensagem")
            for r in results:
                sym = _STATUS_SYMBOL.get(r["status"], "?")
                style = {"ok": "green", "warning": "yellow", "error": "red"}.get(r["status"], "white")
                table.add_row(r["name"], f"[{style}]{sym} {r['status']}[/]", r["message"])
            console.print(table)
        except ImportError:
            for r in results:
                sym = _STATUS_SYMBOL.get(r["status"], "?")
                print(f"{sym} {r['name']}: {r['message']}")
    has_error = any(r["status"] == "error" for r in results)
    return 2 if has_error else 0


@register
def _register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("doctor", help="Diagnóstico self-service.")
    p.add_argument("--json", action="store_true", help="Saída JSON para scripts/MCP.")
    p.add_argument(
        "--reset-breaker",
        action="store_true",
        help="Zera o circuit breaker persistente (fecha, permite nova tentativa).",
    )
    p.set_defaults(func=_handle, skip_deps=True)
