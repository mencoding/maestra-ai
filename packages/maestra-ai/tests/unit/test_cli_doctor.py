"""HIGH-3: cenários CLI de `maestra doctor --reset-breaker`."""
from __future__ import annotations

import argparse


def test_doctor_reset_breaker_flag_invoca_reset(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("MAESTRA_STATE_DIR", str(tmp_path))
    from maestra_ai.cli import doctor as doctor_mod

    called = {"n": 0}

    def fake_reset():
        called["n"] += 1

    monkeypatch.setattr("maestra_ai.core.ratelimit.reset_breaker", fake_reset)

    ns = argparse.Namespace(reset_breaker=True, json=False)
    rc = doctor_mod._handle(ns)

    captured = capsys.readouterr()
    assert rc == 0
    assert called["n"] == 1
    assert "breaker" in captured.out.lower() or "reset" in captured.out.lower()


def test_doctor_sem_reset_flag_executa_diagnostico(monkeypatch, tmp_path, capsys):
    """Sem --reset-breaker, o fluxo normal de diagnóstico roda."""
    monkeypatch.setenv("MAESTRA_STATE_DIR", str(tmp_path))
    from maestra_ai.cli import doctor as doctor_mod

    called = {"n": 0}

    def fake_reset():
        called["n"] += 1

    monkeypatch.setattr("maestra_ai.core.ratelimit.reset_breaker", fake_reset)

    ns = argparse.Namespace(reset_breaker=False, json=True)
    doctor_mod._handle(ns)

    # reset_breaker não foi chamado
    assert called["n"] == 0
