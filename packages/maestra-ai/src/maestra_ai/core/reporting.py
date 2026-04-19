"""Helpers de relatório: estimativas sempre com total calculado."""
from __future__ import annotations

from collections.abc import Iterable


def humanize_bytes(n: int) -> str:
    for unit, divisor in (("GB", 1_000_000_000), ("MB", 1_000_000), ("KB", 1000)):
        if n >= divisor:
            return f"{n / divisor:.1f} {unit}"
    return f"{n} B"


def format_estimate(
    components: Iterable[tuple[str, int, str]],
    *,
    unit: str,
    bytes_per_unit: int = 0,
) -> tuple[str, int]:
    """Formata lista de componentes com total calculado.

    components: iterable de (nome, quantidade, unidade) — a unidade individual
                pode diferir da unit final.

    Retorna (texto_formatado, total_absoluto).
    """
    items = list(components)
    total = sum(n for _, n, _ in items)
    width = max((len(name) for name, _, _ in items), default=10)
    lines = []
    for name, qtd, u in items:
        lines.append(f"  • {name:<{width}}   {qtd} {u}")
    lines.append(f"                      {'─' * 18}")
    total_line = f"  Total estimado:     {total} {unit}"
    if bytes_per_unit:
        total_bytes = total * bytes_per_unit
        total_line += f" ≈ {humanize_bytes(total_bytes)}"
    lines.append(total_line)
    return "\n".join(lines), total
