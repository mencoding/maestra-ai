"""Testes de `core/init.py`."""
from __future__ import annotations

import json

import pytest


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


class TestMenuRendering:
    def test_menu_A_mostra_saudacao_e_duas_opcoes(self, capsys):
        from maestra_ai.core import init
        init.render_menu("A")
        out = capsys.readouterr().out
        assert "Olá" in out
        assert "[1]" in out and "Começar agora" in out
        assert "[2]" in out and "Sair" in out

    def test_menu_A2_mostra_app_configurada(self, capsys):
        from maestra_ai.core import init
        init.render_menu("A2")
        out = capsys.readouterr().out
        assert "app Spotify já está configurada" in out or "app já está configurad" in out
        assert "[1]" in out and "autorizar" in out.lower()
        assert "[2]" in out and "Recomeçar" in out
        assert "[3]" in out and "Sair" in out

    def test_menu_B_mostra_conta_conectada(self, capsys):
        from maestra_ai.core import init
        init.render_menu("B")
        out = capsys.readouterr().out
        assert "conta Spotify já está conectada" in out
        assert "analisar preferências" in out
        assert "[3]" in out

    def test_menu_C_mostra_tudo_pronto(self, capsys):
        from maestra_ai.core import init
        init.render_menu("C")
        out = capsys.readouterr().out
        assert "Tudo pronto" in out
        assert "Atualizar preferências" in out
        assert "[2]" in out and "Recomeçar" in out

    def test_render_update_submenu(self, capsys):
        from maestra_ai.core import init
        init.render_update_submenu()
        out = capsys.readouterr().out
        assert "mood recente" in out.lower()
        assert "Tudo" in out
        assert "Voltar" in out


class TestRetryLoop:
    def test_sucesso_primeira_tentativa_nao_pergunta(self, capsys, monkeypatch):
        from maestra_ai.core import init
        calls = {"n": 0}

        def fn():
            calls["n"] += 1
            return "ok"

        result = init._retry_loop(
            fn,
            classifier=lambda e: "network",
            hints={"network": "Cheque sua conexão."},
        )
        assert result == "ok"
        assert calls["n"] == 1

    def test_recuperacao_na_segunda(self, capsys, monkeypatch):
        from maestra_ai.core import init
        calls = {"n": 0}

        def fn():
            calls["n"] += 1
            if calls["n"] == 1:
                raise ConnectionError("timeout")
            return "ok"

        monkeypatch.setattr(init, "_ask_retry", lambda: True)
        result = init._retry_loop(
            fn,
            classifier=lambda e: "network",
            hints={"network": "Cheque sua conexão."},
        )
        assert result == "ok"
        assert calls["n"] == 2

    def test_tres_falhas_mesmo_tipo_retorna_smart_hint(self, capsys, monkeypatch):
        from maestra_ai.core import init

        def fn():
            raise ConnectionError("fail")

        monkeypatch.setattr(init, "_ask_retry", lambda: True)
        monkeypatch.setattr(init, "_ask_smart_exit", lambda *a, **k: False)

        with pytest.raises(init.UserAbort):
            init._retry_loop(
                fn,
                classifier=lambda e: "network",
                hints={"network": "Cheque sua conexão."},
            )
        out = capsys.readouterr().out
        assert "terceira tentativa" in out.lower() or "3" in out
