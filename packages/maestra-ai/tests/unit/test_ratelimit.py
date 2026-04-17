"""Testes do rate limiter e circuit breaker."""
from __future__ import annotations

from freezegun import freeze_time

from maestra_ai.core.ratelimit import CircuitBreaker, TokenBucket


def test_token_bucket_allows_within_rate():
    bucket = TokenBucket(capacity=5, refill_per_sec=5)
    for _ in range(5):
        assert bucket.try_acquire() is True
    assert bucket.try_acquire() is False


def test_token_bucket_refills():
    with freeze_time("2026-04-16 12:00:00") as frozen:
        bucket = TokenBucket(capacity=5, refill_per_sec=5)
        for _ in range(5):
            bucket.try_acquire()
        assert bucket.try_acquire() is False
        frozen.tick(1.0)
        assert bucket.try_acquire() is True


def test_circuit_breaker_opens_on_threshold():
    cb = CircuitBreaker(max_failures=3, window_sec=60, cooldown_sec=300)
    assert cb.allow() is True
    for _ in range(3):
        cb.record_failure()
    assert cb.allow() is False


def test_circuit_breaker_half_opens_after_cooldown():
    with freeze_time("2026-04-16 12:00:00") as frozen:
        cb = CircuitBreaker(max_failures=3, window_sec=60, cooldown_sec=300)
        for _ in range(3):
            cb.record_failure()
        assert cb.allow() is False
        frozen.tick(301)
        assert cb.allow() is True


def test_circuit_breaker_clears_on_success():
    cb = CircuitBreaker(max_failures=3, window_sec=60, cooldown_sec=300)
    cb.record_failure()
    cb.record_failure()
    cb.record_success()
    assert cb.failure_count() == 0
