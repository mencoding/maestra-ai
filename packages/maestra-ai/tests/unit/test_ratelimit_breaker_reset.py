"""HIGH-3: reset manual do circuit breaker (core + CLI)."""
from __future__ import annotations


def test_reset_breaker_zera_estado_aberto(monkeypatch, tmp_path):
    """Breaker aberto deve ficar fechado após reset_breaker()."""
    monkeypatch.setenv("MAESTRA_STATE_DIR", str(tmp_path))
    from maestra_ai.core import ratelimit

    # Força abertura via record_failure consecutivos
    breaker = ratelimit._get_breaker()
    for _ in range(breaker.max_failures + 1):
        breaker.record_failure()
    was_open = not breaker.allow()
    assert was_open, "setup: breaker deveria abrir após N falhas"

    ratelimit.reset_breaker()

    # Após reset, deve permitir de novo
    breaker_after = ratelimit._get_breaker()
    assert breaker_after.allow() is True, "reset deve fechar o breaker"


def test_reset_breaker_idempotente(monkeypatch, tmp_path):
    """Chamar reset em breaker já fechado é seguro (no-op)."""
    monkeypatch.setenv("MAESTRA_STATE_DIR", str(tmp_path))
    from maestra_ai.core import ratelimit

    ratelimit.reset_breaker()
    ratelimit.reset_breaker()
    assert ratelimit._get_breaker().allow() is True
