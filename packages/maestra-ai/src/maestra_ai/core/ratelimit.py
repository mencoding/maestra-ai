"""Rate limiter (token bucket) e circuit breaker para chamadas à Spotify API."""
from __future__ import annotations

import time
from collections import deque
from threading import Lock


class TokenBucket:
    """Permite N ações por segundo; bloqueia/retorna False quando esgotado."""

    def __init__(self, capacity: int, refill_per_sec: float):
        self.capacity = capacity
        self.refill_per_sec = refill_per_sec
        self._tokens = float(capacity)
        self._last = time.monotonic()
        self._lock = Lock()

    def _refill(self) -> None:
        now = time.monotonic()
        delta = now - self._last
        self._tokens = min(self.capacity, self._tokens + delta * self.refill_per_sec)
        self._last = now

    def try_acquire(self, n: int = 1) -> bool:
        with self._lock:
            self._refill()
            if self._tokens >= n:
                self._tokens -= n
                return True
            return False

    def wait_and_acquire(self, n: int = 1, timeout: float = 10.0) -> bool:
        start = time.monotonic()
        while True:
            if self.try_acquire(n):
                return True
            if time.monotonic() - start > timeout:
                return False
            time.sleep(0.05)


class CircuitBreaker:
    """Abre após N falhas em uma janela; re-tenta após cooldown."""

    def __init__(self, max_failures: int = 3, window_sec: int = 60, cooldown_sec: int = 300):
        self.max_failures = max_failures
        self.window_sec = window_sec
        self.cooldown_sec = cooldown_sec
        self._failures: deque[float] = deque()
        self._opened_at: float | None = None
        self._lock = Lock()

    def _prune_window(self) -> None:
        cutoff = time.monotonic() - self.window_sec
        while self._failures and self._failures[0] < cutoff:
            self._failures.popleft()

    def allow(self) -> bool:
        with self._lock:
            if self._opened_at is None:
                return True
            if time.monotonic() - self._opened_at >= self.cooldown_sec:
                self._opened_at = None
                self._failures.clear()
                return True
            return False

    def record_success(self) -> None:
        with self._lock:
            self._failures.clear()
            self._opened_at = None

    def record_failure(self) -> None:
        with self._lock:
            self._failures.append(time.monotonic())
            self._prune_window()
            if len(self._failures) >= self.max_failures:
                self._opened_at = time.monotonic()

    def failure_count(self) -> int:
        with self._lock:
            self._prune_window()
            return len(self._failures)
