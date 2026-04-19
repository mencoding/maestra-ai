"""Audit log das chamadas MCP.

Retenção: 15 dias ativos + 30 dias arquivados (gzip). Total 45 dias.
Redige secrets antes de gravar.
"""
from __future__ import annotations

import gzip
import json
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from maestra_ai.core import storage

_SECRET_KEYS = {"refresh_token", "client_secret", "access_token", "password", "token"}
_ACTIVE_DAYS = 15
_ARCHIVE_DAYS = 30
# MEDIUM-3: dispara rotação mesmo antes da idade, para evitar crescer >100MB
# em uso intensivo via MCP.
_MAX_SIZE_BYTES = 10 * 1024 * 1024  # 10MB


def _path_active() -> Path:
    storage.ensure_dirs()
    return storage.state_dir() / "audit.jsonl"


def _redact(data: Any) -> Any:
    if isinstance(data, dict):
        return {k: ("REDACTED" if k.lower() in _SECRET_KEYS else _redact(v)) for k, v in data.items()}
    if isinstance(data, list):
        return [_redact(x) for x in data]
    return data


def log(tool: str, args: dict, result: dict) -> None:
    entry = {
        "ts": datetime.now(UTC).isoformat(timespec="seconds"),
        "tool": tool,
        "args": _redact(args),
        "result_summary": _redact_result(result),
    }
    _path_active().parent.mkdir(parents=True, exist_ok=True)
    with _path_active().open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    _maybe_rotate()


def _redact_result(result: Any) -> Any:
    """Resultado resumido — mantém status e counts, remove payloads grandes."""
    if isinstance(result, dict):
        summary = {}
        for k, v in result.items():
            if k in ("tracks", "items") and isinstance(v, list):
                summary[k + "_count"] = len(v)
            else:
                summary[k] = _redact(v)
        return summary
    # Fix M2: listas top-level viram summary de tamanho. Antes, caíam no
    # fallback _redact e o payload inteiro (faixas, artistas) ia parar no
    # audit log, derrotando o propósito do resumo.
    if isinstance(result, list):
        return {"items_count": len(result)}
    return _redact(result)


def _maybe_rotate() -> None:
    """Chama rotate se arquivo tem tamanho ou idade que justifique."""
    p = _path_active()
    if not p.exists():
        return
    # MEDIUM-3: checagem por tamanho (stat barato) roda antes da idade.
    try:
        if p.stat().st_size >= _MAX_SIZE_BYTES:
            _force_rotate()
            return
    except OSError:
        return
    age = (datetime.now(UTC) - datetime.fromtimestamp(p.stat().st_mtime, tz=UTC)).days
    if age >= _ACTIVE_DAYS:
        _force_rotate()


def _force_rotate() -> None:
    p = _path_active()
    if not p.exists():
        return
    ts = datetime.now(UTC).strftime("%Y-%m-%d")
    archive = storage.state_dir() / f"audit.{ts}.jsonl.gz"
    with p.open("rb") as src, gzip.open(archive, "wb") as dst:
        shutil.copyfileobj(src, dst)
    p.unlink()
    _purge_old_archives()


def _purge_old_archives() -> None:
    cutoff = datetime.now(UTC) - timedelta(days=_ARCHIVE_DAYS)
    for f in storage.state_dir().glob("audit.*.jsonl.gz"):
        mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=UTC)
        if mtime < cutoff:
            f.unlink()
