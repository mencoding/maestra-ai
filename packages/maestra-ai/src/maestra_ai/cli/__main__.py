"""Entry point para `python -m maestra_ai.cli`.

Necessário porque `core/director.py` spawna o daemon via
`[sys.executable, "-m", "maestra_ai.cli", "director", "run", ...]`.
Sem este módulo, Python falha com "No module named maestra_ai.cli.__main__".

Issue #6.
"""
from __future__ import annotations

import sys

from maestra_ai.cli import main

if __name__ == "__main__":
    sys.exit(main())
