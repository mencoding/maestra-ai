"""Testes do rate limiter e circuit breaker."""
from __future__ import annotations

from freezegun import freeze_time

from maestra_ai.core.ratelimit import (
    CircuitBreaker,
    PersistentCircuitBreaker,
    PersistentTokenBucket,
    TokenBucket,
)


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


# ============================================================================
# P0-3: versões persistentes (SQLite) — estado compartilhado entre processos
# ============================================================================


class TestPersistentTokenBucket:
    def test_acquire_reduz_tokens_persistidos(self, tmp_path):
        db = tmp_path / "ratelimit.db"
        b1 = PersistentTokenBucket(capacity=3, refill_per_sec=0.0, db_path=str(db))
        assert b1.try_acquire() is True
        assert b1.try_acquire() is True

        # Segunda instância (novo processo simulado) vê estado persistido
        b2 = PersistentTokenBucket(capacity=3, refill_per_sec=0.0, db_path=str(db))
        assert b2.try_acquire() is True
        assert b2.try_acquire() is False  # capacity esgotada across "processos"

    def test_refill_usa_wallclock(self, tmp_path, monkeypatch):
        db = tmp_path / "ratelimit.db"
        t = [1_000_000.0]
        monkeypatch.setattr("maestra_ai.core.ratelimit.time.time", lambda: t[0])

        b = PersistentTokenBucket(capacity=2, refill_per_sec=1.0, db_path=str(db))
        b.try_acquire()
        b.try_acquire()
        assert b.try_acquire() is False

        t[0] += 1.5  # 1.5s → refill de 1.5 tokens
        assert b.try_acquire() is True

    def test_buckets_diferentes_nao_compartilham_estado(self, tmp_path):
        db = tmp_path / "ratelimit.db"
        a = PersistentTokenBucket(capacity=1, refill_per_sec=0.0, db_path=str(db), name="a")
        b = PersistentTokenBucket(capacity=1, refill_per_sec=0.0, db_path=str(db), name="b")
        assert a.try_acquire() is True
        assert b.try_acquire() is True  # bucket b não foi drenado


class TestPersistentCircuitBreaker:
    def test_allow_fecha_ao_atingir_threshold_entre_instancias(self, tmp_path):
        db = tmp_path / "ratelimit.db"
        cb1 = PersistentCircuitBreaker(
            max_failures=3, window_sec=60, cooldown_sec=300, db_path=str(db)
        )
        cb1.record_failure()
        cb1.record_failure()

        # Instância nova (outro processo) vê contador e fecha ao atingir 3
        cb2 = PersistentCircuitBreaker(
            max_failures=3, window_sec=60, cooldown_sec=300, db_path=str(db)
        )
        cb2.record_failure()
        assert cb2.allow() is False
        assert cb1.allow() is False

    def test_reabre_apos_cooldown(self, tmp_path, monkeypatch):
        db = tmp_path / "ratelimit.db"
        t = [1_000_000.0]
        monkeypatch.setattr("maestra_ai.core.ratelimit.time.time", lambda: t[0])

        cb = PersistentCircuitBreaker(
            max_failures=2, window_sec=60, cooldown_sec=10, db_path=str(db)
        )
        cb.record_failure()
        cb.record_failure()
        assert cb.allow() is False
        t[0] += 11
        assert cb.allow() is True

    def test_record_success_limpa_estado(self, tmp_path):
        db = tmp_path / "ratelimit.db"
        cb = PersistentCircuitBreaker(
            max_failures=3, window_sec=60, cooldown_sec=300, db_path=str(db)
        )
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.failure_count() == 0
        assert cb.allow() is True
