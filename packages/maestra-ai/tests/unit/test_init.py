"""Testes de `core/init.py`."""
from __future__ import annotations

import json


class TestDetectState:
    """Cobre as 4 combinações legítimas + 3 inconsistentes."""

    def test_empty_is_A(self, tmp_path, monkeypatch):
        from maestra_ai.core import init, storage
        monkeypatch.setattr(storage, "config_dir", lambda: tmp_path / "cfg")
        monkeypatch.setattr(storage, "data_dir", lambda: tmp_path / "data")
        monkeypatch.setattr(storage, "state_dir", lambda: tmp_path / "state")
        monkeypatch.setattr(init, "_has_token", lambda: False)
        assert init.detect_state() == "A"

    def test_config_only_is_A2(self, tmp_path, monkeypatch):
        from maestra_ai.core import init, storage
        cfg_dir = tmp_path / "cfg"
        cfg_dir.mkdir()
        (cfg_dir / "config.json").write_text(json.dumps({
            "client_id": "x", "client_secret": "y",
            "redirect_uri": "https://example.com/callback",
        }))
        monkeypatch.setattr(storage, "config_dir", lambda: cfg_dir)
        monkeypatch.setattr(storage, "data_dir", lambda: tmp_path / "data")
        monkeypatch.setattr(storage, "state_dir", lambda: tmp_path / "state")
        monkeypatch.setattr(init, "_has_token", lambda: False)
        assert init.detect_state() == "A2"

    def test_connected_no_taste_is_B(self, tmp_path, monkeypatch):
        from maestra_ai.core import init, storage
        cfg_dir = tmp_path / "cfg"
        cfg_dir.mkdir()
        (cfg_dir / "config.json").write_text(json.dumps({
            "client_id": "x", "client_secret": "y",
            "redirect_uri": "https://example.com/callback",
        }))
        monkeypatch.setattr(storage, "config_dir", lambda: cfg_dir)
        monkeypatch.setattr(storage, "data_dir", lambda: tmp_path / "data")
        monkeypatch.setattr(storage, "state_dir", lambda: tmp_path / "state")
        monkeypatch.setattr(init, "_has_token", lambda: True)
        assert init.detect_state() == "B"

    def test_everything_present_is_C(self, tmp_path, monkeypatch):
        from maestra_ai.core import init, storage
        cfg_dir = tmp_path / "cfg"; cfg_dir.mkdir()
        data_dir = tmp_path / "data"; data_dir.mkdir()
        (cfg_dir / "config.json").write_text(json.dumps({
            "client_id": "x", "client_secret": "y",
            "redirect_uri": "https://example.com/callback",
        }))
        (data_dir / "taste_profile.json").write_text(json.dumps({
            "global_signal": {"track_a": {"weight": 3.0}},
        }))
        monkeypatch.setattr(storage, "config_dir", lambda: cfg_dir)
        monkeypatch.setattr(storage, "data_dir", lambda: data_dir)
        monkeypatch.setattr(storage, "state_dir", lambda: tmp_path / "state")
        monkeypatch.setattr(init, "_has_token", lambda: True)
        assert init.detect_state() == "C"

    def test_token_without_config_treated_as_A(self, tmp_path, monkeypatch):
        """Token órfão sem config = inconsistente, volta pra A + aviso."""
        from maestra_ai.core import init, storage
        monkeypatch.setattr(storage, "config_dir", lambda: tmp_path / "cfg")
        monkeypatch.setattr(storage, "data_dir", lambda: tmp_path / "data")
        monkeypatch.setattr(storage, "state_dir", lambda: tmp_path / "state")
        monkeypatch.setattr(init, "_has_token", lambda: True)
        assert init.detect_state() == "A"

    def test_taste_without_token_treated_as_A(self, tmp_path, monkeypatch):
        """Taste órfão sem token = inconsistente, volta pra A + aviso."""
        from maestra_ai.core import init, storage
        data_dir = tmp_path / "data"; data_dir.mkdir()
        (data_dir / "taste_profile.json").write_text(json.dumps({
            "global_signal": {"x": {"weight": 1.0}},
        }))
        monkeypatch.setattr(storage, "config_dir", lambda: tmp_path / "cfg")
        monkeypatch.setattr(storage, "data_dir", lambda: data_dir)
        monkeypatch.setattr(storage, "state_dir", lambda: tmp_path / "state")
        monkeypatch.setattr(init, "_has_token", lambda: False)
        assert init.detect_state() == "A"

    def test_taste_profile_empty_global_signal_is_B(self, tmp_path, monkeypatch):
        """taste_profile existe mas global_signal vazio = ainda B."""
        from maestra_ai.core import init, storage
        cfg_dir = tmp_path / "cfg"; cfg_dir.mkdir()
        data_dir = tmp_path / "data"; data_dir.mkdir()
        (cfg_dir / "config.json").write_text(json.dumps({
            "client_id": "x", "client_secret": "y",
            "redirect_uri": "https://example.com/callback",
        }))
        (data_dir / "taste_profile.json").write_text(json.dumps({
            "global_signal": {},
        }))
        monkeypatch.setattr(storage, "config_dir", lambda: cfg_dir)
        monkeypatch.setattr(storage, "data_dir", lambda: data_dir)
        monkeypatch.setattr(storage, "state_dir", lambda: tmp_path / "state")
        monkeypatch.setattr(init, "_has_token", lambda: True)
        assert init.detect_state() == "B"
