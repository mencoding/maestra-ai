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


def test_check_config_with_valid_credentials(monkeypatch, tmp_path):
    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path / "cfg"))
    (tmp_path / "cfg").mkdir()
    from maestra_ai.core import storage
    storage.write_config({
        "client_id": "a" * 32,
        "client_secret": "b" * 32,
        "redirect_uri": "https://maestra.dev/callback",
    })
    check = doctor.check_config()
    assert check["status"] == "ok"


def test_check_config_aceita_redirect_example_com(monkeypatch, tmp_path):
    """example.com/example.org são TLDs reservados (RFC 2606) e Spotify
    aceita via paste-back. Usar é legítimo — não deve ser warning."""
    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path / "cfg"))
    (tmp_path / "cfg").mkdir()
    from maestra_ai.core import storage
    storage.write_config({
        "client_id": "a" * 32,
        "client_secret": "b" * 32,
        "redirect_uri": "https://example.com/callback",
    })
    check = doctor.check_config()
    assert check["status"] == "ok"


def test_check_config_rejeita_redirect_localhost(monkeypatch, tmp_path):
    """Spotify rejeita http://localhost em apps criados após 2025."""
    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path / "cfg"))
    (tmp_path / "cfg").mkdir()
    from maestra_ai.core import storage
    storage.write_config({
        "client_id": "a" * 32,
        "client_secret": "b" * 32,
        "redirect_uri": "http://localhost:8888/callback",
    })
    check = doctor.check_config()
    assert check["status"] == "warning"
    assert "placeholder" in check["message"].lower()


def test_check_config_rejeita_client_id_placeholder(monkeypatch, tmp_path):
    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path / "cfg"))
    (tmp_path / "cfg").mkdir()
    from maestra_ai.core import storage
    storage.write_config({
        "client_id": "your_client_id",
        "client_secret": "your_client_secret",
        "redirect_uri": "https://maestra.dev/callback",
    })
    check = doctor.check_config()
    assert check["status"] == "warning"
    assert "placeholder" in check["message"].lower()


def test_check_config_rejeita_client_secret_ausente(monkeypatch, tmp_path):
    """Apenas client_id configurado não basta: auth login precisa do secret."""
    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path / "cfg"))
    (tmp_path / "cfg").mkdir()
    from maestra_ai.core import storage
    storage.write_config({"client_id": "a" * 32})
    check = doctor.check_config()
    assert check["status"] == "warning"
    assert "client_secret" in check["message"] or "incompleto" in check["message"].lower()


def test_check_config_rejeita_redirect_uri_ausente(monkeypatch, tmp_path):
    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path / "cfg"))
    (tmp_path / "cfg").mkdir()
    from maestra_ai.core import storage
    storage.write_config({
        "client_id": "a" * 32,
        "client_secret": "b" * 32,
    })
    check = doctor.check_config()
    assert check["status"] == "warning"
    assert "redirect_uri" in check["message"] or "incompleto" in check["message"].lower()


def test_check_disk_space():
    check = doctor.check_disk()
    assert check["status"] in ("ok", "warning", "error")
    assert "available" in check["details"]


def test_run_all_returns_list():
    results = doctor.run_all()
    assert isinstance(results, list)
    assert all("name" in r and "status" in r for r in results)


def test_doctor_reporta_director_rodando_quando_pid_existe_em_data_dir(
    monkeypatch, tmp_path
):
    """CRITICAL-1: doctor checava state_dir/director.pid mas director usa
    data_dir/director.pid. Doctor mostrava 'parado' para daemon vivo."""
    import os

    data = tmp_path / "data"
    state = tmp_path / "state"
    data.mkdir()
    state.mkdir()
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(data))
    monkeypatch.setenv("MAESTRA_STATE_DIR", str(state))

    # Usa PID do próprio processo (garantidamente vivo).
    (data / "director.pid").write_text(str(os.getpid()), encoding="utf-8")

    check = doctor.check_director()
    assert "rodando" in check["message"].lower() or "running" in check["message"].lower()
    assert check["details"].get("pid") == str(os.getpid())
