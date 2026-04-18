"""Rate limiter (token bucket) e circuit breaker para chamadas à Spotify API.

Classes in-memory (TokenBucket, CircuitBreaker) são adequadas para um único
processo. A variante Persistent* compartilha estado entre processos via
SQLite com `journal_mode=WAL`, necessária para o daemon `director run`
coexistir com invocações manuais do CLI sem duplicar o budget de rate limit.
"""
from __future__ import annotations

import json
import os
import sqlite3
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


def _connect(db_path: str) -> sqlite3.Connection:
    """Abre conexão SQLite com WAL e schema garantido."""
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=5.0, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS token_bucket ("
        "name TEXT PRIMARY KEY, tokens REAL NOT NULL, last_refill REAL NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS circuit_breaker ("
        "name TEXT PRIMARY KEY, failures_json TEXT NOT NULL, opened_at REAL)"
    )
    return conn


class PersistentTokenBucket:
    """Token bucket persistido em SQLite.

    Diferenças em relação a TokenBucket:
    - Usa `time.time()` (wallclock) porque `time.monotonic()` não é
      comparável entre processos.
    - Toda operação abre transação SQLite (BEGIN IMMEDIATE) para serializar
      writes entre processos concorrentes.
    """

    def __init__(
        self,
        capacity: int,
        refill_per_sec: float,
        db_path: str,
        *,
        name: str = "default",
    ):
        self.capacity = capacity
        self.refill_per_sec = refill_per_sec
        self.db_path = db_path
        self.name = name

    def try_acquire(self, n: int = 1) -> bool:
        now = time.time()
        with _connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT tokens, last_refill FROM token_bucket WHERE name = ?",
                (self.name,),
            ).fetchone()
            if row is None:
                tokens, last_refill = float(self.capacity), now
            else:
                tokens, last_refill = row
                tokens = min(
                    self.capacity,
                    tokens + (now - last_refill) * self.refill_per_sec,
                )
            if tokens >= n:
                tokens -= n
                allowed = True
            else:
                allowed = False
            conn.execute(
                "INSERT INTO token_bucket(name, tokens, last_refill) VALUES(?, ?, ?) "
                "ON CONFLICT(name) DO UPDATE SET tokens = excluded.tokens, "
                "last_refill = excluded.last_refill",
                (self.name, tokens, now),
            )
            conn.execute("COMMIT")
            return allowed

    def wait_and_acquire(self, n: int = 1, timeout: float = 10.0) -> bool:
        start = time.time()
        while True:
            if self.try_acquire(n):
                return True
            if time.time() - start > timeout:
                return False
            time.sleep(0.05)


class PersistentCircuitBreaker:
    """Circuit breaker persistido em SQLite.

    Usa `time.time()` wallclock para timestamps comparáveis entre processos.
    Estado `failures` serializado como JSON array de timestamps (float).
    """

    def __init__(
        self,
        max_failures: int = 3,
        window_sec: int = 60,
        cooldown_sec: int = 300,
        db_path: str = "",
        *,
        name: str = "default",
    ):
        if not db_path:
            raise ValueError("db_path é obrigatório em PersistentCircuitBreaker")
        self.max_failures = max_failures
        self.window_sec = window_sec
        self.cooldown_sec = cooldown_sec
        self.db_path = db_path
        self.name = name

    def _load(self, conn: sqlite3.Connection) -> tuple[list[float], float | None]:
        row = conn.execute(
            "SELECT failures_json, opened_at FROM circuit_breaker WHERE name = ?",
            (self.name,),
        ).fetchone()
        if row is None:
            return [], None
        failures_json, opened_at = row
        try:
            failures = json.loads(failures_json)
            if not isinstance(failures, list):
                failures = []
        except (json.JSONDecodeError, TypeError):
            failures = []
        return failures, opened_at

    def _save(
        self, conn: sqlite3.Connection, failures: list[float], opened_at: float | None
    ) -> None:
        conn.execute(
            "INSERT INTO circuit_breaker(name, failures_json, opened_at) VALUES(?, ?, ?) "
            "ON CONFLICT(name) DO UPDATE SET failures_json = excluded.failures_json, "
            "opened_at = excluded.opened_at",
            (self.name, json.dumps(failures), opened_at),
        )

    def _prune(self, failures: list[float], now: float) -> list[float]:
        cutoff = now - self.window_sec
        return [t for t in failures if t >= cutoff]

    def allow(self) -> bool:
        now = time.time()
        with _connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            failures, opened_at = self._load(conn)
            if opened_at is None:
                conn.execute("COMMIT")
                return True
            if now - opened_at >= self.cooldown_sec:
                self._save(conn, [], None)
                conn.execute("COMMIT")
                return True
            conn.execute("COMMIT")
            return False

    def record_success(self) -> None:
        with _connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._save(conn, [], None)
            conn.execute("COMMIT")

    def record_failure(self) -> None:
        now = time.time()
        with _connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            failures, opened_at = self._load(conn)
            failures.append(now)
            failures = self._prune(failures, now)
            if len(failures) >= self.max_failures:
                opened_at = now
            self._save(conn, failures, opened_at)
            conn.execute("COMMIT")

    def failure_count(self) -> int:
        now = time.time()
        with _connect(self.db_path) as conn:
            failures, _ = self._load(conn)
            return len(self._prune(failures, now))
