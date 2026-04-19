"""Testes do subcomando `maestra onboard` — modo interativo + non-interactive.

v0.4.5 parte 2: CLI aceita --playlist-id para apontar playlist existente
e modo interativo (TTY) com escolha entre criar nova ou apontar.
"""
from __future__ import annotations

import argparse

import pytest

from maestra_ai.cli import onboard as cli_onboard

_ID = "ABCDEFGHIJKLMNOPQRSTUV"  # 22 chars base62


def _ns(**kwargs):
    ns = argparse.Namespace(
        human=False,
        json=False,
        playlist_name="Maestra",
        seed_playlist=0,
        dry_run=True,
        yes=True,
        non_interactive=False,
        playlist_id=None,
        # v0.5.3: novos args de expansão
        total_cap=5000,
        no_expand=False,
        expand_playlists=None,
    )
    for k, v in kwargs.items():
        setattr(ns, k, v)
    return ns


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("MAESTRA_STATE_DIR", str(tmp_path / "state"))
    yield


class _FakeController:
    def __init__(self):
        self.sp = object()


def _fake_run_capture(captured: dict):
    def _fake(sp, taste, **kwargs):
        captured.update(kwargs)
        return {
            "status": "ok",
            "playlist_id": kwargs.get("existing_playlist_id") or "pl_new",
            "playlist_name": kwargs.get("playlist_name") or "PL",
            "top_long_count": 0, "top_medium_count": 0, "top_short_count": 0,
            "saved_tracks_fetched": 0, "recent_count": 0,
            "unique_tracks_scored": 0, "seeded": 0,
            "context_suggestions": ["a", "b", "c", "d", "e"],
        }
    return _fake


class TestInteractiveSelectorFluxoReal:
    """v0.5.6 #24: cobertura real do _interactive_selector além de
    'é callable' — mocka questionary no nível do módulo e exerce o
    caminho confirm→checkbox→retorno."""

    def _patch_questionary(self, monkeypatch, confirm_return, checkbox_return):
        """Substitui questionary no sys.modules para testes interativos."""
        import sys

        class FakeResp:
            def __init__(self, v):
                self._v = v
            def ask(self):
                return self._v

        def fake_confirm(message, default=True):
            return FakeResp(confirm_return)

        def fake_checkbox(message, choices):
            return FakeResp(checkbox_return)

        fake_q = type("FQ", (), {
            "confirm": staticmethod(fake_confirm),
            "checkbox": staticmethod(fake_checkbox),
            "Choice": lambda title, value: {"title": title, "value": value},
        })
        monkeypatch.setitem(sys.modules, "questionary", fake_q)

    def test_confirma_e_escolhe_dois_ids(self, monkeypatch):
        self._patch_questionary(
            monkeypatch, confirm_return=True, checkbox_return=["p1", "p3"],
        )
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        args = _ns(non_interactive=False)
        sel = cli_onboard._build_playlist_selector(args, progress=None)

        playlists = [
            {"id": "p1", "name": "A", "track_count": 20},
            {"id": "p2", "name": "B", "track_count": 5},
            {"id": "p3", "name": "C", "track_count": 100},
        ]
        result = sel(playlists)
        assert result == ["p1", "p3"]

    def test_confirm_negado_retorna_vazio(self, monkeypatch):
        self._patch_questionary(
            monkeypatch, confirm_return=False, checkbox_return=["whatever"],
        )
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        args = _ns(non_interactive=False)
        sel = cli_onboard._build_playlist_selector(args, progress=None)
        result = sel([{"id": "p1", "name": "A", "track_count": 10}])
        assert result == []

    def test_checkbox_nenhum_marcado_retorna_vazio(self, monkeypatch):
        self._patch_questionary(
            monkeypatch, confirm_return=True, checkbox_return=[],
        )
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        args = _ns(non_interactive=False)
        sel = cli_onboard._build_playlist_selector(args, progress=None)
        result = sel([{"id": "p1", "name": "A", "track_count": 10}])
        assert result == []

    def test_lista_vazia_retorna_sem_imprimir(self, monkeypatch, capsys):
        """v0.5.7 #17: selector não imprime mais mensagem humana em lista
        vazia — responsabilidade moveu para _print_report que tem acesso
        ao own_playlists_empty_count para distinguir os casos."""
        self._patch_questionary(
            monkeypatch, confirm_return=True, checkbox_return=["p1"],
        )
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        args = _ns(non_interactive=False)
        sel = cli_onboard._build_playlist_selector(args, progress=None)
        result = sel([])
        assert result == []

    def test_humanized_message_distingue_zero_de_todas_vazias(self, capsys):
        """v0.5.7 #17: mensagem muda conforme empty_count."""
        cli_onboard._humanized_no_playlists_message(empty_count=0)
        out1 = capsys.readouterr().out
        assert "ainda não criou" in out1

        cli_onboard._humanized_no_playlists_message(empty_count=3)
        out2 = capsys.readouterr().out
        assert "3" in out2
        assert "vazias" in out2


class TestPromptExpansionConfirmDinamico:
    """v0.5.5 #9: mensagem do prompt reflete --total-cap real,
    não o literal '5000'."""

    def test_usa_total_cap_passado(self, monkeypatch):
        captured = {}

        class FakeQ:
            def ask(self):
                return True

        def fake_confirm(message, default):
            captured["msg"] = message
            return FakeQ()

        fake_questionary = type("FQ", (), {"confirm": staticmethod(fake_confirm)})
        monkeypatch.setattr(
            "maestra_ai.cli.onboard.sys.modules",
            {**__import__("sys").modules, "questionary": fake_questionary},
        )

        cli_onboard._prompt_expansion_confirm(current_total=0, total_cap=1000)
        assert "1000" in captured["msg"]
        assert "5000" not in captured["msg"]

    def test_mostra_gap_quando_current_total_conhecido(self, monkeypatch):
        captured = {}

        class FakeQ:
            def ask(self):
                return True

        def fake_confirm(message, default):
            captured["msg"] = message
            return FakeQ()

        fake_questionary = type("FQ", (), {"confirm": staticmethod(fake_confirm)})
        monkeypatch.setattr(
            "maestra_ai.cli.onboard.sys.modules",
            {**__import__("sys").modules, "questionary": fake_questionary},
        )

        cli_onboard._prompt_expansion_confirm(current_total=700, total_cap=1000)
        # Prompt deve citar 700 (atual) e 300 (gap).
        assert "700" in captured["msg"]
        assert "300" in captured["msg"]


class TestPlaylistSelector:
    """v0.5.3: _build_playlist_selector retorna callback conforme flags."""

    def test_no_expand_retorna_none(self):
        args = _ns(no_expand=True)
        sel = cli_onboard._build_playlist_selector(args, progress=None)
        assert sel is None

    def test_expand_playlists_fixo_retorna_ids(self):
        # v0.5.5 #8: IDs devem ter formato válido (22 chars base62).
        valid_ids = "ABCDEFGHIJKLMNOPQRSTUV,123456789012345678901X"
        args = _ns(expand_playlists=valid_ids)
        sel = cli_onboard._build_playlist_selector(args, progress=None)
        ids = sel([{"id": "xxx", "name": "Ignorada", "track_count": 5}])
        assert ids == ["ABCDEFGHIJKLMNOPQRSTUV", "123456789012345678901X"]

    def test_expand_playlists_aceita_url_e_uri(self):
        """normalize_playlist_id extrai o ID de 22 chars de qualquer forma."""
        preset = (
            "spotify:playlist:ABCDEFGHIJKLMNOPQRSTUV,"
            "https://open.spotify.com/playlist/123456789012345678901X?si=abc"
        )
        args = _ns(expand_playlists=preset)
        sel = cli_onboard._build_playlist_selector(args, progress=None)
        ids = sel([])
        assert ids == ["ABCDEFGHIJKLMNOPQRSTUV", "123456789012345678901X"]

    def test_expand_playlists_id_invalido_levanta_user_error(self):
        """v0.5.5 #8: ID malformado vira UserError com mensagem clara —
        antes caía no except Exception: continue do core silenciosamente."""
        from maestra_ai.core.errors import UserError
        args = _ns(expand_playlists="valido_22_caracteres_1,blabla")
        with pytest.raises(UserError, match="inválido"):
            cli_onboard._build_playlist_selector(args, progress=None)

    def test_non_interactive_sem_preset_retorna_none(self):
        args = _ns(non_interactive=True)
        sel = cli_onboard._build_playlist_selector(args, progress=None)
        assert sel is None

    def test_sem_tty_retorna_none(self, monkeypatch):
        args = _ns(non_interactive=False)
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)
        sel = cli_onboard._build_playlist_selector(args, progress=None)
        assert sel is None

    def test_tty_retorna_callback(self, monkeypatch):
        args = _ns(non_interactive=False)
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        sel = cli_onboard._build_playlist_selector(args, progress=None)
        assert callable(sel)

    def test_keyboard_interrupt_no_confirm_degrada_para_lista_vazia(
        self, monkeypatch,
    ):
        """v0.5.3.1 (C1): Ctrl+C durante _prompt_expansion_confirm não pode
        abortar o onboard — deve degradar para [] e deixar o core continuar
        persistindo top/saved/recent já coletados.
        """
        args = _ns(non_interactive=False)
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)

        def _raise(*_, **__):
            raise KeyboardInterrupt()

        monkeypatch.setattr(cli_onboard, "_prompt_expansion_confirm", _raise)
        sel = cli_onboard._build_playlist_selector(args, progress=None)
        # selector deve engolir KeyboardInterrupt e retornar [].
        result = sel([{"id": "p1", "name": "A", "track_count": 10}])
        assert result == []

    def test_keyboard_interrupt_no_checkbox_degrada_para_lista_vazia(
        self, monkeypatch,
    ):
        args = _ns(non_interactive=False)
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        monkeypatch.setattr(cli_onboard, "_prompt_expansion_confirm",
                             lambda **_: True)

        def _raise(*_, **__):
            raise KeyboardInterrupt()

        monkeypatch.setattr(cli_onboard, "_prompt_playlists_checkbox", _raise)
        sel = cli_onboard._build_playlist_selector(args, progress=None)
        result = sel([{"id": "p1", "name": "A", "track_count": 10}])
        assert result == []


def test_seed_maior_que_50_emite_warning_em_json(monkeypatch, capsys):
    """v0.5.2 (bug 4): report JSON inclui campo warnings quando
    --seed-playlist > 50 (Spotify clampa top_short em 50)."""
    import json
    captured = {}
    monkeypatch.setattr(
        "maestra_ai.core.onboard.run", _fake_run_capture(captured)
    )
    args = _ns(
        playlist_name="Maestra", non_interactive=True, yes=True,
        seed_playlist=100, json=True, dry_run=False,
    )
    rc = cli_onboard._handle(args, _FakeController(), taste=None)
    assert rc == 0
    out = capsys.readouterr().out
    report = json.loads(out)
    assert "warnings" in report
    assert any("50" in w and "clampeado" in w for w in report["warnings"])


def test_seed_50_ou_menos_nao_emite_warning(monkeypatch, capsys):
    import json
    captured = {}
    monkeypatch.setattr(
        "maestra_ai.core.onboard.run", _fake_run_capture(captured)
    )
    args = _ns(
        playlist_name="Maestra", non_interactive=True, yes=True,
        seed_playlist=50, json=True, dry_run=False,
    )
    rc = cli_onboard._handle(args, _FakeController(), taste=None)
    assert rc == 0
    report = json.loads(capsys.readouterr().out)
    assert "warnings" not in report


def test_onboard_cli_non_interactive_com_name(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "maestra_ai.core.onboard.run", _fake_run_capture(captured)
    )
    args = _ns(playlist_name="TesteNome", non_interactive=True, yes=True)
    rc = cli_onboard._handle(args, _FakeController(), taste=None)
    assert rc == 0
    assert captured.get("playlist_name") == "TesteNome"
    assert captured.get("existing_playlist_id") is None


def test_onboard_cli_non_interactive_com_playlist_id_normaliza(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "maestra_ai.core.onboard.run", _fake_run_capture(captured)
    )
    args = _ns(
        playlist_id=f"spotify:playlist:{_ID}",
        non_interactive=True, yes=True,
    )
    rc = cli_onboard._handle(args, _FakeController(), taste=None)
    assert rc == 0
    assert captured.get("existing_playlist_id") == _ID


def test_onboard_cli_non_interactive_sem_flags_erra(monkeypatch, capsys):
    # --non-interactive sem --name (default "Maestra" ainda existe, mas o
    # usuário precisa confirmar uma das duas flags explicitamente).
    # Regra: se non_interactive e não há --playlist-id e playlist_name é
    # o default placeholder => erra. Usamos playlist_name=None para sinalizar
    # ausência explícita.
    args = _ns(
        playlist_name=None,
        playlist_id=None,
        non_interactive=True,
        yes=True,
    )
    rc = cli_onboard._handle(args, _FakeController(), taste=None)
    assert rc != 0


def test_onboard_cli_interativo_escolha_1_cria(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "maestra_ai.core.onboard.run", _fake_run_capture(captured)
    )
    # Força TTY
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)

    inputs = iter(["1", "Nome Teste"])
    monkeypatch.setattr("builtins.input", lambda *a, **kw: next(inputs))

    args = _ns(
        playlist_name=None, playlist_id=None,
        non_interactive=False, yes=True,
    )
    rc = cli_onboard._handle(args, _FakeController(), taste=None)
    assert rc == 0
    assert captured.get("playlist_name") == "Nome Teste"
    assert captured.get("existing_playlist_id") is None


def test_onboard_cli_interativo_escolha_2_por_numero(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "maestra_ai.core.onboard.run", _fake_run_capture(captured)
    )
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)

    class _Ctrl:
        def __init__(self):
            self.sp = self
        def current_user_playlists(self, limit=20):
            return {"items": [
                {"id": "pl_a", "name": "A", "tracks": {"total": 10}},
                {"id": "pl_b", "name": "B", "tracks": {"total": 20}},
                {"id": "pl_c", "name": "C", "tracks": {"total": 30}},
            ]}

    inputs = iter(["2", "2"])
    monkeypatch.setattr("builtins.input", lambda *a, **kw: next(inputs))

    args = _ns(
        playlist_name=None, playlist_id=None,
        non_interactive=False, yes=True,
    )
    rc = cli_onboard._handle(args, _Ctrl(), taste=None)
    assert rc == 0
    assert captured.get("existing_playlist_id") == "pl_b"


def test_onboard_cli_interativo_escolha_2_paste_url(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "maestra_ai.core.onboard.run", _fake_run_capture(captured)
    )
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)

    class _Ctrl:
        def __init__(self):
            self.sp = self
        def current_user_playlists(self, limit=20):
            return {"items": [
                {"id": "pl_a", "name": "A", "tracks": {"total": 10}},
            ]}

    url = f"https://open.spotify.com/playlist/{_ID}?si=xyz"
    inputs = iter(["2", url])
    monkeypatch.setattr("builtins.input", lambda *a, **kw: next(inputs))

    args = _ns(
        playlist_name=None, playlist_id=None,
        non_interactive=False, yes=True,
    )
    rc = cli_onboard._handle(args, _Ctrl(), taste=None)
    assert rc == 0
    assert captured.get("existing_playlist_id") == _ID


def test_onboard_cli_interativo_input_invalido_3x_aborta(monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)

    class _Ctrl:
        def __init__(self):
            self.sp = self
        def current_user_playlists(self, limit=20):
            return {"items": [
                {"id": "pl_a", "name": "A", "tracks": {"total": 10}},
            ]}

    # "2" para apontar, depois 3 inputs inválidos
    inputs = iter(["2", "xxx", "yyy", "zzz"])
    monkeypatch.setattr("builtins.input", lambda *a, **kw: next(inputs))

    args = _ns(
        playlist_name=None, playlist_id=None,
        non_interactive=False, yes=True,
    )
    rc = cli_onboard._handle(args, _Ctrl(), taste=None)
    assert rc != 0
