"""Subcomando `curate`: dry-run de curadoria."""
from __future__ import annotations

import argparse

from maestra_ai.cli import register
from maestra_ai.cli._common import _curation_context, error, output


def _maybe_print_external_attribution():
    """Imprime bloco de atribuição se fontes externas estão em uso (legacy).

    Mantido para compatibilidade com testes antigos. O novo fluxo usa
    sources_used retornado do curator.curate() diretamente.
    """
    from rich.console import Console

    from maestra_ai.core import storage
    from maestra_ai.core.config import any_source_enabled
    from maestra_ai.core.external import cache as ext_cache
    from maestra_ai.core.external.attribution import render_attribution

    cfg = storage.read_config()
    if not any_source_enabled(cfg):
        return
    cache = ext_cache.load_cache()
    sources_used: set[str] = set()
    for entry in cache.get("tracks", {}).values():
        for s in entry.get("sources", []) or []:
            sources_used.add(s)
    if not sources_used:
        return
    text = render_attribution(sorted(sources_used))
    if text:
        Console().print(text)


def cmd_curate(args, curator, context_state, **_):
    from rich.console import Console

    from maestra_ai.core.external.attribution import render_attribution

    context, _ = _curation_context(args, context_state)
    results, _, sources_used = curator.curate(context, count=args.count)
    if not results:
        error("Sem resultados para esse contexto.", "NO_RESULTS")
    output(results, args.human)
    if getattr(args, "human", False):
        # Imprime atribuição condicional se há fontes externas usadas
        if sources_used:
            attribution = render_attribution(sources_used)
            if attribution:
                console = Console()
                console.print()
                console.print(attribution)


@register
def _register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("curate", help="Gera faixas sem adicionar (dry-run)")
    p.add_argument("context", nargs="?", default=None, help="Contexto")
    p.add_argument("--count", type=int, default=5)
    p.add_argument("--human", action="store_true", help="Saída legível para humanos")
    p.set_defaults(func=cmd_curate)
