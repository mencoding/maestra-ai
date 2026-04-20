"""Skip automático de testes `integration_live` fora de execução opt-in.

Sem este conftest, `pytest -q` coleta e executa os testes marcados com
`integration_live`, fazendo chamadas HTTP reais a cada rodada. Isso viola
rate limits, polui logs e torna a suite dependente de rede.

Comportamento: se o usuário rodar `pytest -m integration_live`, os testes
rodam normalmente. Qualquer outra invocação pula os testes marcados.
"""
from __future__ import annotations

import pytest


def pytest_collection_modifyitems(config, items):
    marker_expr = config.getoption("-m") or ""
    if "integration_live" in marker_expr:
        return
    skip_live = pytest.mark.skip(
        reason="integration_live pulado por padrão; rode com: pytest -m integration_live",
    )
    for item in items:
        if "integration_live" in item.keywords:
            item.add_marker(skip_live)
