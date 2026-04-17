"""CLI da Maestra.

Em v0.1.0 o CLI é o monolito portado (`_monolith.py`). A refatoração em módulos
por grupo de subcomando está planejada para v0.2.0+, após a introdução de
`rich`, `@handle_errors` e `core/storage.py` — assim evitamos reescrever os
handlers duas vezes.
"""
from __future__ import annotations

import sys

from maestra_ai.cli import _monolith


def main(argv: list[str] | None = None) -> int:
    # argparse do _monolith lê sys.argv direto; para compatibilidade com
    # execução programática (testes), permitimos sobrescrever sys.argv.
    if argv is not None:
        old_argv = sys.argv
        sys.argv = ["maestra", *argv]
        try:
            result = _monolith.main()
        finally:
            sys.argv = old_argv
    else:
        result = _monolith.main()
    return int(result) if result is not None else 0


if __name__ == "__main__":
    sys.exit(main())
