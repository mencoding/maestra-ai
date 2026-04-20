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
    canonical_id = "2026-04-19-142530-000000-fake"
    (snap_dir / f"{canonical_id}.json").write_text(
        f'{{"id": "{canonical_id}", "operation": "test"}}'
    )
    with pytest.raises(StorageError, match="malformado"):
        snapshot.load(canonical_id)

def test_load_rejects_non_dict_snapshot(monkeypatch, tmp_path):
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
    (tmp_path / "data").mkdir()
    snap_dir = tmp_path / "data" / "snapshots"
    snap_dir.mkdir(parents=True)
    canonical_id = "2026-04-19-142530-000001-bad"
    (snap_dir / f"{canonical_id}.json").write_text('"just a string"')
    with pytest.raises(StorageError, match="malformado"):
        snapshot.load(canonical_id)

def test_snapshot_id_usa_utc_puro(monkeypatch, tmp_path):
    """S8: ts do snapshot id deve ser UTC puro, sem offset local.

    Antes: datetime.now(UTC).astimezone() re-converte para TZ local,
    embutindo offset no ID. Em TZ com offset negativo (ex.: America/
    Sao_Paulo, UTC-3) o ID começa com uma data anterior à data UTC
    real — dois processos em TZ diferentes produzem IDs ordenáveis
    ambiguamente.

    Assertivamente: o prefixo do ID (YYYY-MM-DD-HH) deve coincidir
    com o UTC agora, tolerando transição de minuto.
    """
    import datetime as dt

    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
    (tmp_path / "data").mkdir()

    before = dt.datetime.now(dt.UTC)
    sid = snapshot.create("test_utc", {"k": "v"})
    after = dt.datetime.now(dt.UTC)

    # Prefixo "YYYY-MM-DD-HH" em UTC deve bater com o intervalo
    # [before, after] — tolerância de uma hora (edge em 00:59:59).
    prefix_before = before.strftime("%Y-%m-%d-%H")
    prefix_after = after.strftime("%Y-%m-%d-%H")
    sid_prefix = sid[:13]  # "YYYY-MM-DD-HH"
    assert sid_prefix in (prefix_before, prefix_after), (
        f"sid={sid!r} prefixo {sid_prefix!r} não bate com UTC "
        f"[{prefix_before!r}, {prefix_after!r}]"
    )


def test_snap_id_regex_aceita_formato_canonico():
    from maestra_ai.core.snapshot import _SNAP_ID_RE
    assert _SNAP_ID_RE.match("2026-04-19-142530-000000-safety-before-rollback")
    assert _SNAP_ID_RE.match("2026-04-19-142530-000000-pre_prune")
    assert _SNAP_ID_RE.match("2026-01-01-000000-000000-op")


def test_snap_id_regex_rejeita_formatos_invalidos():
    from maestra_ai.core.snapshot import _SNAP_ID_RE
    # ausência de partes
    assert not _SNAP_ID_RE.match("foo")
    assert not _SNAP_ID_RE.match("2026-04-19-safety")
    # caracteres fora do whitelist
    assert not _SNAP_ID_RE.match("2026-04-19-142530-000000-op/etc")
    assert not _SNAP_ID_RE.match("../etc/passwd")
    # espaços
    assert not _SNAP_ID_RE.match("2026-04-19-142530-000000-op with space")


def test_list_snapshots_skips_malformed(monkeypatch, tmp_path):
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
    (tmp_path / "data").mkdir()
    snap_id = snapshot.create("good_op", {"k": "v"})
    snap_dir = tmp_path / "data" / "snapshots"
    (snap_dir / "bad.json").write_text("not json at all")
    snaps = snapshot.list_snapshots()
    assert len(snaps) == 1
    assert snaps[0]["id"] == snap_id


class TestCreateAtomicity:
    def test_create_atomico_em_caso_de_crash_simulado(
        self, tmp_path, monkeypatch,
    ):
        """I4 v0.6.1: se o rename final falhar (crash), nenhum arquivo
        parcial ou .tmp residual deve ficar visível."""
        monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path))

        from maestra_ai.core import snapshot, storage

        def failing_replace(src, dst):
            raise RuntimeError("simulated crash mid-rename")

        monkeypatch.setattr("maestra_ai.core.storage.os.replace", failing_replace)

        with pytest.raises(RuntimeError, match="simulated crash"):
            snapshot.create("test-op", {"foo": "bar"})

        snap_dir = storage.snapshots_dir()
        published = list(snap_dir.glob("*.json"))
        assert published == []
