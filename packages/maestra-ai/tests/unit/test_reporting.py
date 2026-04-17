"""Testes de reporting.format_estimate — total sempre calculado."""
from __future__ import annotations

from maestra_ai.core.reporting import format_estimate, humanize_bytes


def test_format_estimate_sum():
    components = [
        ("Top tracks", 3, "requests"),
        ("Saved tracks", 20, "requests"),
        ("Recently played", 1, "requests"),
    ]
    text, total = format_estimate(components, unit="requests")
    assert total == 24
    assert "24 requests" in text
    assert "Top tracks" in text
    assert "Saved tracks" in text


def test_format_estimate_empty():
    text, total = format_estimate([], unit="requests")
    assert total == 0
    assert "0 requests" in text


def test_humanize_bytes():
    assert humanize_bytes(500) == "500 B"
    assert humanize_bytes(1024) == "1.0 KB"
    assert humanize_bytes(2_500_000) == "2.5 MB"


def test_format_estimate_with_bytes_hint():
    components = [("A", 10, "requests"), ("B", 5, "requests")]
    text, total = format_estimate(components, unit="requests", bytes_per_unit=2000)
    assert total == 15
    assert "30.0 KB" in text
