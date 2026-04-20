"""Testes de `core/init.py`."""
from __future__ import annotations

import json

import pytest


class TestDetectState:
    """Cobre as 4 combinações legítimas + 3 inconsistentes."""

    def test_empty_is_A(self, tmp_path, monkeypatch):  # noqa: N802 — ecoa nome do state (A) para legibilidade
        from maestra_ai.core import init, storage
        monkeypatch.setattr(storage, "config_dir", lambda: tmp_path / "cfg")
        monkeypatch.setattr(storage, "data_dir", lambda: tmp_path / "data")
        monkeypatch.setattr(storage, "state_dir", lambda: tmp_path / "state")
        monkeypatch.setattr(init, "_has_token", lambda: False)
        assert init.detect_state() == "A"

    def test_config_only_is_A2(self, tmp_path, monkeypatch):  # noqa: N802 — ecoa nome do state (A2) para legibilidade
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

    def test_connected_no_taste_is_B(self, tmp_path, monkeypatch):  # noqa: N802 — ecoa nome do state (B) para legibilidade
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

    def test_everything_present_is_C(self, tmp_path, monkeypatch):  # noqa: N802 — ecoa nome do state (C) para legibilidade
        from maestra_ai.core import init, storage
        cfg_dir = tmp_path / "cfg"
        cfg_dir.mkdir()
        data_dir = tmp_path / "data"
        data_dir.mkdir()
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

    def test_token_without_config_treated_as_A(self, tmp_path, monkeypatch):  # noqa: N802 — ecoa nome do state (A) para legibilidade
        """Token órfão sem config = inconsistente, volta pra A + aviso."""
        from maestra_ai.core import init, storage
        monkeypatch.setattr(storage, "config_dir", lambda: tmp_path / "cfg")
        monkeypatch.setattr(storage, "data_dir", lambda: tmp_path / "data")
        monkeypatch.setattr(storage, "state_dir", lambda: tmp_path / "state")
        monkeypatch.setattr(init, "_has_token", lambda: True)
        assert init.detect_state() == "A"

    def test_taste_without_token_treated_as_A(self, tmp_path, monkeypatch):  # noqa: N802 — ecoa nome do state (A) para legibilidade
        """Taste órfão sem token = inconsistente, volta pra A + aviso."""
        from maestra_ai.core import init, storage
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "taste_profile.json").write_text(json.dumps({
            "global_signal": {"x": {"weight": 1.0}},
        }))
        monkeypatch.setattr(storage, "config_dir", lambda: tmp_path / "cfg")
        monkeypatch.setattr(storage, "data_dir", lambda: data_dir)
        monkeypatch.setattr(storage, "state_dir", lambda: tmp_path / "state")
        monkeypatch.setattr(init, "_has_token", lambda: False)
        assert init.detect_state() == "A"

    def test_taste_profile_empty_global_signal_is_B(self, tmp_path, monkeypatch):  # noqa: N802 — ecoa nome do state (B) para legibilidade
        """taste_profile existe mas global_signal vazio = ainda B."""
        from maestra_ai.core import init, storage
        cfg_dir = tmp_path / "cfg"
        cfg_dir.mkdir()
        data_dir = tmp_path / "data"
        data_dir.mkdir()
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
    def test_menu_A_mostra_saudacao_e_duas_opcoes(self, capsys):  # noqa: N802 — ecoa nome do state (A) para legibilidade
        from maestra_ai.core import init
        init.render_menu("A")
        out = capsys.readouterr().out
        assert "Olá" in out
        assert "[1]" in out and "Começar agora" in out
        assert "[2]" in out and "Sair" in out

    def test_menu_A2_mostra_app_configurada(self, capsys):  # noqa: N802 — ecoa nome do state (A2) para legibilidade
        from maestra_ai.core import init
        init.render_menu("A2")
        out = capsys.readouterr().out
        assert "app Spotify já está configurada" in out or "app já está configurad" in out
        assert "[1]" in out and "autorizar" in out.lower()
        assert "[2]" in out and "Recomeçar" in out
        assert "[3]" in out and "Sair" in out

    def test_menu_B_mostra_conta_conectada(self, capsys):  # noqa: N802 — ecoa nome do state (B) para legibilidade
        from maestra_ai.core import init
        init.render_menu("B")
        out = capsys.readouterr().out
        assert "conta Spotify já está conectada" in out
        assert "analisar preferências" in out
        assert "[3]" in out

    def test_menu_C_mostra_tudo_pronto(self, capsys):  # noqa: N802 — ecoa nome do state (C) para legibilidade
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


class TestFlowA:
    def test_collect_credentials_persist_config(self, tmp_path, monkeypatch):
        from maestra_ai.core import init, storage
        cfg_dir = tmp_path / "cfg"
        monkeypatch.setattr(storage, "config_dir", lambda: cfg_dir)

        prompts = iter([
            "s",  # Você criou o app?
            "abc123",  # client_id
            "def456",  # client_secret
            "",  # redirect_uri (Enter = default)
        ])
        monkeypatch.setattr("rich.prompt.Prompt.ask", lambda *a, **k: next(prompts))
        monkeypatch.setattr(init, "_open_url", lambda url: None)

        init._flow_A_collect_credentials()

        cfg = json.loads((cfg_dir / "config.json").read_text())
        assert cfg["client_id"] == "abc123"
        assert cfg["client_secret"] == "def456"
        assert cfg["redirect_uri"] == "https://example.com/callback"


class TestFlowA2:
    def test_oauth_paste_back_persist_token(self, monkeypatch, capsys):
        from maestra_ai.core import init

        monkeypatch.setattr(init, "_open_url", lambda url: True)
        monkeypatch.setattr(init, "_build_authorization_url", lambda: "https://accounts.spotify.com/authorize?x=1")

        # Simula URL de retorno com code
        paste_url = "https://example.com/callback?code=AQD_abc123&state=xyz"
        monkeypatch.setattr("rich.prompt.Prompt.ask", lambda *a, **k: paste_url)

        saved = {}

        def fake_exchange(code):
            saved["code"] = code
            return "refresh_tok_xyz"

        monkeypatch.setattr(init, "_exchange_code_for_refresh_token", fake_exchange)
        monkeypatch.setattr(init, "_persist_refresh_token", lambda t: saved.setdefault("token", t))

        init._flow_A2_oauth_paste_back()

        assert saved["code"] == "AQD_abc123"
        assert saved["token"] == "refresh_tok_xyz"

    def test_paste_url_sem_code_entra_retry(self, monkeypatch):
        from maestra_ai.core import init

        monkeypatch.setattr(init, "_build_authorization_url", lambda: "https://accounts.spotify.com/authorize?x=1")
        monkeypatch.setattr(init, "_open_url", lambda url: True)
        attempts = iter([
            "https://example.com/callback?state=xyz",  # sem code
            "https://example.com/callback?code=AQD_ok",  # ok
        ])
        monkeypatch.setattr("rich.prompt.Prompt.ask", lambda *a, **k: next(attempts))
        monkeypatch.setattr(init, "_ask_retry", lambda: True)

        saved = {}

        def fake_exchange(code):
            saved["code"] = code
            return "tok"

        monkeypatch.setattr(init, "_exchange_code_for_refresh_token", fake_exchange)
        monkeypatch.setattr(init, "_persist_refresh_token", lambda t: saved.setdefault("token", t))

        init._flow_A2_oauth_paste_back()
        assert saved["code"] == "AQD_ok"
        assert saved["token"] == "tok"


class TestFlowB:
    """Fluxo B → [1]: análise de preferências delegando a `onboard.run`."""

    def test_flow_B_delega_onboard_run_e_imprime_narrativa(  # noqa: N802 — ecoa nome do state (B) para legibilidade
        self, tmp_path, monkeypatch, capsys
    ):
        from maestra_ai.core import init, onboard

        # Report fake devolvido por onboard.run, no shape atual
        fake_report = {
            "playlist_id": "pl_123",
            "playlist_name": "Maestra",
            "tracks_analyzed": 150,
            "signals": {
                "top_genres": [("indie folk", 100.0), ("ambient", 80.0)],
                "dominant_decades": [("2010s", 200.0)],
                "top_artists": [("Artist A", 50.0)],
            },
            "suggestions": ["contexto A", "contexto B"],
            "rationale_path": str(tmp_path / "onboard_rationale.json"),
            "warnings": [],
        }

        captured = {}

        def fake_run(sp, taste, **kw):
            captured["sp"] = sp
            captured["taste"] = taste
            captured["kw"] = kw
            return fake_report

        monkeypatch.setattr(onboard, "run", fake_run)

        # Prompt.ask devolve o link da playlist criada pelo usuário
        monkeypatch.setattr(
            "rich.prompt.Prompt.ask",
            lambda *a, **k: "https://open.spotify.com/playlist/6c2ppkdUfGKJNWwBl0MC4w?si=xyz",
        )

        class FakeSP:
            pass

        class FakeTaste:
            pass

        monkeypatch.setattr(init, "_build_spotify_client", lambda: FakeSP())
        monkeypatch.setattr(init, "_build_taste_profile", lambda: FakeTaste())

        report = init._flow_B_analysis(
            playlist_name_hint=None, skip_expansion=True
        )

        out = capsys.readouterr().out
        # Narrativa: menciona playlist e contextos sugeridos
        assert "playlist" in out.lower()
        assert "contexto a" in out.lower() or "contexto A" in out
        assert "indie folk" in out.lower()
        # InitReport
        assert report["state_before"] == "B"
        assert report["action"] == "initial_analysis"
        assert report["playlist_id"] == "pl_123"
        assert report["taste_profile_updated"] is True
        assert report["suggestions"] == ["contexto A", "contexto B"]
        # onboard.run foi chamado com playlist_name
        assert captured["kw"].get("playlist_name") == "Maestra"

    def test_flow_B_403_playlist_create_classifica_como_user_management(  # noqa: N802 — ecoa nome do state (B) para legibilidade
        self, monkeypatch
    ):
        from maestra_ai.core import init, onboard
        from maestra_ai.core.errors import PlaylistCreateForbiddenError

        calls = {"n": 0}

        def fake_run(sp, taste, **kw):
            calls["n"] += 1
            if calls["n"] == 1:
                raise PlaylistCreateForbiddenError("403", status=403)
            return {
                "playlist_id": "pl_ok",
                "signals": {},
                "suggestions": [],
                "rationale_path": None,
                "warnings": [],
            }

        monkeypatch.setattr(onboard, "run", fake_run)
        monkeypatch.setattr(init, "_build_spotify_client", lambda: object())
        monkeypatch.setattr(init, "_build_taste_profile", lambda: object())
        # Com existing_playlist_id fornecido, o fluxo pula o prompt de link.
        # Depois da 1ª falha, _ask_retry = tentar de novo
        monkeypatch.setattr(init, "_ask_retry", lambda: True)

        report = init._flow_B_analysis(
            playlist_name_hint="Maestra",
            skip_expansion=True,
            existing_playlist_id="6c2ppkdUfGKJNWwBl0MC4w",
        )
        assert report["playlist_id"] == "pl_ok"
        assert calls["n"] == 2

    def test_flow_B_sem_playlist_id_pede_link_interativo(self, monkeypatch):  # noqa: N802
        """Sem existing_playlist_id, flow B instrui e pede link da playlist criada."""
        from maestra_ai.core import init, onboard

        captured = {}
        def fake_run(sp, taste, **kw):
            captured.update(kw)
            return {
                "playlist_id": kw.get("existing_playlist_id"),
                "playlist_name": kw.get("playlist_name", "Maestra"),
                "signals": {},
                "suggestions": [],
                "rationale_path": None,
                "warnings": [],
            }
        monkeypatch.setattr(onboard, "run", fake_run)
        monkeypatch.setattr(init, "_build_spotify_client", lambda: object())
        monkeypatch.setattr(init, "_build_taste_profile", lambda: object())
        monkeypatch.setattr(
            "rich.prompt.Prompt.ask",
            lambda *a, **k: "https://open.spotify.com/playlist/6c2ppkdUfGKJNWwBl0MC4w?si=xyz",
        )

        report = init._flow_B_analysis(skip_expansion=True)
        assert captured["existing_playlist_id"] == "6c2ppkdUfGKJNWwBl0MC4w"
        assert report["playlist_id"] == "6c2ppkdUfGKJNWwBl0MC4w"


    def test_flow_B_link_invalido_entra_retry(self, monkeypatch):  # noqa: N802
        """Link malformado repete o prompt até um válido."""
        from maestra_ai.core import init, onboard

        captured = {}
        def fake_run(sp, taste, **kw):
            captured.update(kw)
            return {
                "playlist_id": kw.get("existing_playlist_id"),
                "playlist_name": "Maestra",
                "signals": {},
                "suggestions": [],
                "rationale_path": None,
                "warnings": [],
            }
        monkeypatch.setattr(onboard, "run", fake_run)
        monkeypatch.setattr(init, "_build_spotify_client", lambda: object())
        monkeypatch.setattr(init, "_build_taste_profile", lambda: object())

        answers = iter([
            "lixo qualquer",  # inválido — retry
            "spotify:playlist:6c2ppkdUfGKJNWwBl0MC4w",  # válido
        ])
        monkeypatch.setattr("rich.prompt.Prompt.ask", lambda *a, **k: next(answers))
        monkeypatch.setattr(init, "_ask_retry", lambda: True)

        init._flow_B_analysis(skip_expansion=True)
        assert captured["existing_playlist_id"] == "6c2ppkdUfGKJNWwBl0MC4w"


    def test_flow_B_com_playlist_id_pula_criacao(self, monkeypatch):  # noqa: N802 — ecoa nome do state (B) para legibilidade
        from maestra_ai.core import init, onboard

        captured = {}

        def fake_run(sp, taste, **kw):
            captured.update(kw)
            return {
                "playlist_id": kw.get("existing_playlist_id"),
                "playlist_name": kw.get("playlist_name"),
                "signals": {},
                "suggestions": [],
                "rationale_path": None,
                "warnings": [],
            }

        monkeypatch.setattr(onboard, "run", fake_run)
        monkeypatch.setattr(init, "_build_spotify_client", lambda: object())
        monkeypatch.setattr(init, "_build_taste_profile", lambda: object())

        report = init._flow_B_analysis(
            playlist_name_hint="Maestra",
            skip_expansion=True,
            existing_playlist_id="6c2ppkdUfGKJNWwBl0MC4w",
        )
        assert captured["existing_playlist_id"] == "6c2ppkdUfGKJNWwBl0MC4w"
        assert report["playlist_id"] == "6c2ppkdUfGKJNWwBl0MC4w"


class TestFlowC:
    """Fluxo C → [1]: atualização incremental.

    Dois modos:
      - recent_mood: só top_short + recent (skip library/long/medium/playlist).
      - full: re-analisa tudo exceto criação de playlist.
    """

    def test_update_recent_mood(self, monkeypatch):
        from maestra_ai.core import init, onboard

        captured_kwargs = {}

        def fake_run(sp, taste, **kw):
            captured_kwargs.update(kw)
            return {
                "playlist_id": "pl_x",
                "signals": {"top_genres": [("ambient", 10.0)]},
                "suggestions": [],
                "rationale_path": None,
                "warnings": [],
            }

        monkeypatch.setattr(onboard, "run", fake_run)
        monkeypatch.setattr(init, "_build_spotify_client", lambda: object())
        monkeypatch.setattr(init, "_build_taste_profile", lambda: object())

        report = init._flow_C_update(mode="recent_mood")

        assert report["action"] == "update_recent_mood"
        assert report["state_before"] == "C"
        # Modo recent_mood: pula library/long/medium e playlist creation
        assert captured_kwargs.get("skip_library") is True
        assert captured_kwargs.get("skip_long_term") is True
        assert captured_kwargs.get("skip_medium_term") is True
        assert captured_kwargs.get("skip_playlist_creation") is True

    def test_update_full(self, monkeypatch):
        from maestra_ai.core import init, onboard

        captured_kwargs = {}

        def fake_run(sp, taste, **kw):
            captured_kwargs.update(kw)
            return {
                "playlist_id": "pl_x",
                "signals": {"top_genres": [("ambient", 10.0)]},
                "suggestions": [],
                "rationale_path": None,
                "warnings": [],
            }

        monkeypatch.setattr(onboard, "run", fake_run)
        monkeypatch.setattr(init, "_build_spotify_client", lambda: object())
        monkeypatch.setattr(init, "_build_taste_profile", lambda: object())

        report = init._flow_C_update(mode="full")

        assert report["action"] == "update_full"
        assert report["state_before"] == "C"
        # Modo full: só pula criação de playlist
        assert captured_kwargs.get("skip_playlist_creation") is True
        assert not captured_kwargs.get("skip_library", False)
        assert not captured_kwargs.get("skip_long_term", False)
        assert not captured_kwargs.get("skip_medium_term", False)


class TestReset:
    """Fluxos de Recomeçar: B→[2] (parcial) e C→[2] (total)."""

    def test_reset_partial_apaga_token_e_config_nao_mexe_taste(
        self, tmp_path, monkeypatch
    ):
        from maestra_ai.core import init, storage

        cfg_dir = tmp_path / "cfg"
        cfg_dir.mkdir()
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (cfg_dir / "config.json").write_text("{}")
        (data_dir / "taste_profile.json").write_text("{}")

        monkeypatch.setattr(storage, "config_dir", lambda: cfg_dir)
        monkeypatch.setattr(storage, "data_dir", lambda: data_dir)
        monkeypatch.setattr(storage, "state_dir", lambda: tmp_path / "state")
        monkeypatch.setattr("rich.prompt.Prompt.ask", lambda *a, **k: "s")

        removed_tokens = {"n": 0}
        monkeypatch.setattr(
            init, "_delete_refresh_token", lambda: removed_tokens.update(n=1)
        )

        report = init._flow_reset_partial()
        assert report["action"] == "reset_partial"
        assert report["state_before"] == "B"
        assert not (cfg_dir / "config.json").exists()
        # taste_profile NÃO pode ter sido apagado
        assert (data_dir / "taste_profile.json").exists()
        assert removed_tokens["n"] == 1

    def test_reset_full_apaga_tudo_com_confirmacao_dupla(
        self, tmp_path, monkeypatch
    ):
        from maestra_ai.core import init, storage

        cfg_dir = tmp_path / "cfg"
        cfg_dir.mkdir()
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        (cfg_dir / "config.json").write_text("{}")
        (data_dir / "taste_profile.json").write_text("{}")
        (state_dir / "onboard_rationale.json").write_text("{}")

        monkeypatch.setattr(storage, "config_dir", lambda: cfg_dir)
        monkeypatch.setattr(storage, "data_dir", lambda: data_dir)
        monkeypatch.setattr(storage, "state_dir", lambda: state_dir)

        answers = iter(["s", "s"])
        monkeypatch.setattr(
            "rich.prompt.Prompt.ask", lambda *a, **k: next(answers)
        )
        monkeypatch.setattr(init, "_delete_refresh_token", lambda: None)

        report = init._flow_reset_full()
        assert report["action"] == "reset_full"
        assert report["state_before"] == "C"
        assert not (cfg_dir / "config.json").exists()
        assert not (data_dir / "taste_profile.json").exists()
        assert not (state_dir / "onboard_rationale.json").exists()

    def test_reset_partial_cancela_se_usuario_responde_n(
        self, tmp_path, monkeypatch
    ):
        from maestra_ai.core import init, storage

        cfg_dir = tmp_path / "cfg"
        cfg_dir.mkdir()
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (cfg_dir / "config.json").write_text("{}")
        (data_dir / "taste_profile.json").write_text("{}")

        monkeypatch.setattr(storage, "config_dir", lambda: cfg_dir)
        monkeypatch.setattr(storage, "data_dir", lambda: data_dir)
        monkeypatch.setattr(storage, "state_dir", lambda: tmp_path / "state")
        monkeypatch.setattr("rich.prompt.Prompt.ask", lambda *a, **k: "n")

        token_calls = {"n": 0}
        monkeypatch.setattr(
            init, "_delete_refresh_token", lambda: token_calls.update(n=1)
        )

        report = init._flow_reset_partial()
        assert report["action"] == "exit"
        assert report["state_before"] == "B"
        # Nada foi apagado
        assert (cfg_dir / "config.json").exists()
        assert (data_dir / "taste_profile.json").exists()
        assert token_calls["n"] == 0

    def test_reset_full_cancela_se_segunda_confirmacao_n(
        self, tmp_path, monkeypatch
    ):
        from maestra_ai.core import init, storage

        cfg_dir = tmp_path / "cfg"
        cfg_dir.mkdir()
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        (cfg_dir / "config.json").write_text("{}")
        (data_dir / "taste_profile.json").write_text("{}")
        (state_dir / "onboard_rationale.json").write_text("{}")

        monkeypatch.setattr(storage, "config_dir", lambda: cfg_dir)
        monkeypatch.setattr(storage, "data_dir", lambda: data_dir)
        monkeypatch.setattr(storage, "state_dir", lambda: state_dir)

        # Primeira "s", segunda "n" — aborta antes de apagar
        answers = iter(["s", "n"])
        monkeypatch.setattr(
            "rich.prompt.Prompt.ask", lambda *a, **k: next(answers)
        )

        token_calls = {"n": 0}
        monkeypatch.setattr(
            init, "_delete_refresh_token", lambda: token_calls.update(n=1)
        )

        report = init._flow_reset_full()
        assert report["action"] == "exit"
        assert report["state_before"] == "C"
        # Nada foi apagado — taste preservado
        assert (cfg_dir / "config.json").exists()
        assert (data_dir / "taste_profile.json").exists()
        assert (state_dir / "onboard_rationale.json").exists()
        assert token_calls["n"] == 0


class TestRunOrchestration:
    """Orquestração `run_interactive` / `run_auto` — dispatch por estado."""

    def test_run_interactive_estado_A_menu_sair(self, monkeypatch):  # noqa: N802 — ecoa nome do state (A) para legibilidade
        from maestra_ai.core import init

        monkeypatch.setattr(init, "detect_state", lambda: "A")
        monkeypatch.setattr("rich.prompt.Prompt.ask", lambda *a, **k: "2")

        report = init.run_interactive()
        assert report["action"] == "exit"
        assert report["state_before"] == "A"

    def test_run_auto_estado_A_falha_com_erro(self, monkeypatch):  # noqa: N802 — ecoa nome do state (A) para legibilidade
        from maestra_ai.core import init
        from maestra_ai.core.errors import UserError

        monkeypatch.setattr(init, "detect_state", lambda: "A")
        with pytest.raises(UserError, match="requer interação"):
            init.run_auto()

    def test_run_auto_estado_A2_falha_com_erro(self, monkeypatch):  # noqa: N802 — ecoa nome do state (A2) para legibilidade
        from maestra_ai.core import init
        from maestra_ai.core.errors import UserError

        monkeypatch.setattr(init, "detect_state", lambda: "A2")
        with pytest.raises(UserError, match="requer interação"):
            init.run_auto()

    def test_run_auto_estado_B_executa_analise(self, monkeypatch):  # noqa: N802 — ecoa nome do state (B) para legibilidade
        from maestra_ai.core import init

        captured = {}

        def fake_flow_B(**kwargs):  # noqa: N802 — ecoa nome do state (B) para legibilidade
            captured.update(kwargs)
            return {
                "state_before": "B",
                "action": "initial_analysis",
                "playlist_id": "pl_auto",
                "taste_profile_updated": True,
                "rationale_path": None,
                "signals": None,
                "suggestions": [],
                "warnings": [],
            }

        monkeypatch.setattr(init, "detect_state", lambda: "B")
        monkeypatch.setattr(init, "_flow_B_analysis", fake_flow_B)

        report = init.run_auto(playlist_id="spotify:playlist:6c2ppkdUfGKJNWwBl0MC4w")
        assert report["action"] == "initial_analysis"
        assert captured.get("playlist_name_hint") == "Maestra"
        assert captured.get("skip_expansion") is True

    def test_run_auto_estado_C_executa_update_full(self, monkeypatch):  # noqa: N802 — ecoa nome do state (C) para legibilidade
        from maestra_ai.core import init

        captured = {}

        def fake_flow_C(**kwargs):  # noqa: N802 — ecoa nome do state (C) para legibilidade
            captured.update(kwargs)
            return {
                "state_before": "C",
                "action": "update_full",
                "playlist_id": None,
                "taste_profile_updated": True,
                "rationale_path": None,
                "signals": None,
                "suggestions": [],
                "warnings": [],
            }

        monkeypatch.setattr(init, "detect_state", lambda: "C")
        monkeypatch.setattr(init, "_flow_C_update", fake_flow_C)

        report = init.run_auto()
        assert report["action"] == "update_full"
        assert captured.get("mode") == "full"

    def test_run_auto_B_sem_playlist_id_falha(self, monkeypatch):  # noqa: N802
        """--auto em estado B sem --playlist-id levanta UserError."""
        from maestra_ai.core import init
        from maestra_ai.core.errors import UserError
        monkeypatch.setattr(init, "detect_state", lambda: "B")
        with pytest.raises(UserError, match="--playlist-id"):
            init.run_auto()

    def test_run_auto_com_playlist_id_repassa_ao_flow_B(self, monkeypatch):  # noqa: N802 — ecoa nome do state (B) para legibilidade
        from maestra_ai.core import init

        captured = {}

        def fake_flow(**kw):  # noqa: N802 — ecoa nome do state (B) para legibilidade
            captured.update(kw)
            return {
                "state_before": "B",
                "action": "initial_analysis",
                "playlist_id": "abc",
                "taste_profile_updated": True,
                "rationale_path": None,
                "signals": None,
                "suggestions": [],
                "warnings": [],
            }

        monkeypatch.setattr(init, "detect_state", lambda: "B")
        monkeypatch.setattr(init, "_flow_B_analysis", fake_flow)
        report = init.run_auto(playlist_id="spotify:playlist:6c2ppkdUfGKJNWwBl0MC4w")
        # URI foi normalizada para ID puro
        assert captured["existing_playlist_id"] == "6c2ppkdUfGKJNWwBl0MC4w"
        assert report["action"] == "initial_analysis"
