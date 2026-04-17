"""Testes de snapshot e rollback."""
from __future__ import annotations

import pytest

from maestra_ai.core import snapshot
from maestra_ai.core.errors import StorageError, UserError


def test_create_snapshot(monkeypatch, tmp_path):
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
    (tmp_path / "data").mkdir()
    snap_id = snapshot.create("test_op", {"playlist": ["uri1", "uri2"]})
    assert snap_id
    snaps = snapshot.list_snapshots()
    assert len(snaps) == 1
    assert snaps[0]["id"] == snap_id
    assert snaps[0]["operation"] == "test_op"


def test_load_snapshot(monkeypatch, tmp_path):
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
    (tmp_path / "data").mkdir()
    snap_id = snapshot.create("prune", {"playlist": ["a", "b"]})
    state = snapshot.load(snap_id)
    assert state["playlist"] == ["a", "b"]


def test_rotation_keeps_last_20(monkeypatch, tmp_path):
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
    (tmp_path / "data").mkdir()
    for i in range(25):
        snapshot.create(f"op_{i:02d}", {"idx": i})
    snaps = snapshot.list_snapshots()
    assert len(snaps) == 20
    archive = tmp_path / "data" / "snapshots" / "archive"
    if archive.exists():
        archived = list(archive.glob("*.json.gz"))
        assert len(archived) == 5


def test_list_last_snapshot(monkeypatch, tmp_path):
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
    (tmp_path / "data").mkdir()
    snapshot.create("first", {})
    second = snapshot.create("second", {})
    last = snapshot.last()
    assert last == second


def test_rapid_snapshots_unique_ids(monkeypatch, tmp_path):
    """Granularidade de microsegundos evita colisão entre snapshots próximos."""
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
    (tmp_path / "data").mkdir()
    ids = [snapshot.create("op_z", {"i": i}) for i in range(5)]
    assert len(set(ids)) == 5
    # last() deve retornar o mais recente mesmo com operações de nome idêntico
    assert snapshot.last() == ids[-1]


def test_rejects_path_traversal(monkeypatch, tmp_path):
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
    (tmp_path / "data").mkdir()
    with pytest.raises(UserError, match="ID de snapshot"):
        snapshot.load("../../../etc/passwd")


def test_rejects_snap_id_with_slash(monkeypatch, tmp_path):
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
    (tmp_path / "data").mkdir()
    with pytest.raises(UserError, match="ID de snapshot"):
        snapshot.load("foo/bar")


def test_rejects_snap_id_with_dotdot(monkeypatch, tmp_path):
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
    (tmp_path / "data").mkdir()
    with pytest.raises(UserError, match="ID de snapshot"):
        snapshot.load("..sneaky")


def test_load_rejects_malformed_snapshot(monkeypatch, tmp_path):
    """P0-4: snapshot sem chave 'state' deve levantar StorageError."""
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
    (tmp_path / "data").mkdir()
    snap_dir = tmp_path / "data" / "snapshots"
    snap_dir.mkdir(parents=True)
    (snap_dir / "fake-snap.json").write_text('{"id": "fake-snap", "operation": "test"}')
    with pytest.raises(StorageError, match="malformado"):
        snapshot.load("fake-snap")

def test_load_rejects_non_dict_snapshot(monkeypatch, tmp_path):
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
    (tmp_path / "data").mkdir()
    snap_dir = tmp_path / "data" / "snapshots"
    snap_dir.mkdir(parents=True)
    (snap_dir / "bad.json").write_text('"just a string"')
    with pytest.raises(StorageError, match="malformado"):
        snapshot.load("bad")

def test_list_snapshots_skips_malformed(monkeypatch, tmp_path):
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
    (tmp_path / "data").mkdir()
    snap_id = snapshot.create("good_op", {"k": "v"})
    snap_dir = tmp_path / "data" / "snapshots"
    (snap_dir / "bad.json").write_text("not json at all")
    snaps = snapshot.list_snapshots()
    assert len(snaps) == 1
    assert snaps[0]["id"] == snap_id
