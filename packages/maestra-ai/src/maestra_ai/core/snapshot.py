"""Snapshots automáticos antes de operações mutadoras."""
from __future__ import annotations

import gzip
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from maestra_ai.core import storage

_MAX_ACTIVE = 20


def _snap_dir() -> Path:
    d = storage.snapshots_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d


def _archive_dir() -> Path:
    d = _snap_dir() / "archive"
    d.mkdir(parents=True, exist_ok=True)
    return d


def create(operation: str, state: dict) -> str:
    """Cria snapshot; retorna ID (nome do arquivo sem extensão)."""
    ts = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d-%H%M%S")
    snap_id = f"{ts}-{operation}"
    path = _snap_dir() / f"{snap_id}.json"
    payload = {
        "id": snap_id,
        "operation": operation,
        "created_at": ts,
        "state": state,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    _rotate()
    return snap_id


def _rotate() -> None:
    active = sorted(_snap_dir().glob("*.json"))
    overflow = len(active) - _MAX_ACTIVE
    if overflow <= 0:
        return
    for path in active[:overflow]:
        dest = _archive_dir() / (path.name + ".gz")
        with path.open("rb") as src, gzip.open(dest, "wb") as dst:
            shutil.copyfileobj(src, dst)
        path.unlink()


def list_snapshots() -> list[dict]:
    out = []
    for path in sorted(_snap_dir().glob("*.json"), reverse=True):
        data = json.loads(path.read_text(encoding="utf-8"))
        out.append({
            "id": data["id"],
            "operation": data["operation"],
            "created_at": data["created_at"],
            "path": str(path),
        })
    return out


def load(snap_id: str) -> dict:
    path = _snap_dir() / f"{snap_id}.json"
    if not path.exists():
        arch = _archive_dir() / f"{snap_id}.json.gz"
        if arch.exists():
            with gzip.open(arch, "rt", encoding="utf-8") as f:
                data = json.load(f)
        else:
            from maestra_ai.core.errors import NotFoundError
            raise NotFoundError(f"Snapshot '{snap_id}' não encontrado.")
    else:
        data = json.loads(path.read_text(encoding="utf-8"))
    return data["state"]


def last() -> str | None:
    snaps = list_snapshots()
    return snaps[0]["id"] if snaps else None
