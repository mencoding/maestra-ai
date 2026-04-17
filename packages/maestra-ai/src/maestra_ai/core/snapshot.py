"""Snapshots automáticos antes de operações mutadoras."""
from __future__ import annotations

import gzip
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from maestra_ai.core import storage
from maestra_ai.core.errors import NotFoundError, StorageError, UserError

# Somente caracteres alfanuméricos, underline, dois-pontos e hífen são permitidos
_SNAP_ID_RE = re.compile(r"^[\w:\-]+$")

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
    # Granularidade de microsegundos evita colisão lexicográfica em
    # snapshots criados na mesma segundo (ex.: safety-before-rollback
    # imediatamente antes do rollback).
    ts = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d-%H%M%S-%f")
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
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or "id" not in data:
                continue
        except (json.JSONDecodeError, OSError):
            continue
        out.append({
            "id": data["id"],
            "operation": data.get("operation", "unknown"),
            "created_at": data.get("created_at", "unknown"),
            "path": str(path),
        })
    return out


def load(snap_id: str) -> dict:
    if not _SNAP_ID_RE.match(snap_id):
        raise UserError(f"ID de snapshot inválido: {snap_id}")
    snap_dir = _snap_dir()
    path = snap_dir / f"{snap_id}.json"
    # Defesa em profundidade
    if not path.resolve().is_relative_to(snap_dir.resolve()):
        raise UserError(f"ID de snapshot inválido: {snap_id}")
    if not path.exists():
        arch = _archive_dir() / f"{snap_id}.json.gz"
        if arch.exists():
            with gzip.open(arch, "rt", encoding="utf-8") as f:
                data = json.load(f)
        else:
            raise NotFoundError(f"Snapshot '{snap_id}' não encontrado.")
    else:
        data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "state" not in data:
        raise StorageError(
            f"Snapshot '{snap_id}' malformado: chave 'state' ausente.",
        )
    return data["state"]


def last() -> str | None:
    snaps = list_snapshots()
    return snaps[0]["id"] if snaps else None
