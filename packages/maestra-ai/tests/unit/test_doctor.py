"""Testes dos checks do doctor."""
from __future__ import annotations

from maestra_ai.core import doctor


def test_check_python_version_ok():
    check = doctor.check_python()
    assert check["status"] in ("ok", "warning")


def test_check_config_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path / "empty"))
    (tmp_path / "empty").mkdir()
    check = doctor.check_config()
    assert check["status"] == "warning"
    assert "config.json" in check["message"].lower()


def test_check_config_with_client_id(monkeypatch, tmp_path):
    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path / "cfg"))
    (tmp_path / "cfg").mkdir()
    from maestra_ai.core import storage
    storage.write_config({"client_id": "abc"})
    check = doctor.check_config()
    assert check["status"] == "ok"


def test_check_disk_space():
    check = doctor.check_disk()
    assert check["status"] in ("ok", "warning", "error")
    assert "available" in check["details"]


def test_run_all_returns_list():
    results = doctor.run_all()
    assert isinstance(results, list)
    assert all("name" in r and "status" in r for r in results)
