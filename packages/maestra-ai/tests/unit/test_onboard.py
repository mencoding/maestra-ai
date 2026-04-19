"""Testes do onboard — 6 etapas ponderadas, paginação defensiva.

Baseado no plano original com adaptações do spec v0.3.0:
- sp injetado via DI (não via client.get_client inexistente).
- taste passado explicitamente.
- playlist com sufixo se nome já existe.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from maestra_ai.core import onboard


def _fake_saved(n):
    return {"items": [
        {"track": {"uri": f"spotify:track:s{i}", "name": f"S{i}", "artists": [{"name": f"As{i}"}]}}
        for i in range(n)
    ]}


def _fake_top(n, prefix="t"):
    return {"items": [
        {"uri": f"spotify:track:{prefix}{i}", "name": f"T{prefix}{i}", "artists": [{"name": f"A{i}"}]}
        for i in range(n)
    ]}


def _fake_recent(n):
    return {"items": [
        {"track": {"uri": f"spotify:track:r{i}", "name": f"R{i}", "artists": [{"name": f"Ar{i}"}]}}
        for i in range(n)
    ]}


def _make_sp(top_long=0, top_medium=0, top_short=0, saved_pages=(), recent=0, user_id="u"):
    sp = MagicMock()

    def top_tracks(limit, time_range):
        mapping = {"long_term": top_long, "medium_term": top_medium, "short_term": top_short}
        return _fake_top(mapping.get(time_range, 0), prefix=time_range[0])

    sp.current_user_top_tracks.side_effect = top_tracks
    sp.current_user_saved_tracks.side_effect = list(saved_pages)
    sp.current_user_recently_played.return_value = _fake_recent(recent)
    sp.current_user.return_value = {"id": user_id}
    sp.user_playlist_create.return_value = {"id": "pl_new"}
    sp.current_user_playlists.return_value = {"items": []}
    return sp


class TestComputeWeights:
    def test_pesos_do_plano_original(self):
        w = onboard._compute_weights(
            top_long=[{"uri": "spotify:track:1"}],
            top_medium=[{"uri": "spotify:track:1"}],
            top_short=[{"uri": "spotify:track:2"}],
            saved=[{"uri": "spotify:track:3"}],
            recent=[{"uri": "spotify:track:2"}],
        )
        assert w["spotify:track:1"] == onboard.WEIGHTS["long_term"] + onboard.WEIGHTS["medium_term"]
        assert w["spotify:track:2"] == onboard.WEIGHTS["short_term"] + onboard.WEIGHTS["recent"]
        assert w["spotify:track:3"] == onboard.WEIGHTS["saved"]


def _fake_saved_with_next(n, has_next=True):
    """Página com campo `next` (Spotify manda URL da próxima página ou null)."""
    return {
        "items": [
            {"track": {"uri": f"spotify:track:s{i}", "name": f"S{i}", "artists": [{"name": f"As{i}"}]}}
            for i in range(n)
        ],
        "next": "https://api.spotify.com/v1/me/tracks?offset=50&limit=50" if has_next else None,
    }


class TestFetchSaved:
    def test_cap_em_max_saved(self, monkeypatch):
        sp = MagicMock()
        # 101 páginas de 50 com next → 5050 items, mas cap em _MAX_SAVED
        pages = [_fake_saved_with_next(50, has_next=True)] * 100 + \
                [_fake_saved_with_next(50, has_next=False)]
        sp.current_user_saved_tracks.side_effect = pages
        result = onboard._fetch_saved(sp)
        assert len(result) <= onboard._MAX_SAVED

    def test_para_quando_next_e_null(self):
        """v0.5.2: heurística real de fim é next=null, NÃO len(items) < 50."""
        sp = MagicMock()
        sp.current_user_saved_tracks.side_effect = [
            _fake_saved_with_next(50, has_next=True),
            _fake_saved_with_next(50, has_next=True),
            _fake_saved_with_next(50, has_next=False),  # última página, mesmo com 50 items
        ]
        result = onboard._fetch_saved(sp)
        assert len(result) == 150

    def test_pagina_intermediaria_parcial_nao_interrompe(self):
        """v0.5.2 (bug 3): antes, len(items) < 50 parava paginação prematura
        se Spotify mandasse página parcial no meio (rate limit soft,
        inconsistência). Agora só para em next=null."""
        sp = MagicMock()
        sp.current_user_saved_tracks.side_effect = [
            _fake_saved_with_next(50, has_next=True),
            _fake_saved_with_next(30, has_next=True),   # parcial mas há mais
            _fake_saved_with_next(50, has_next=True),
            _fake_saved_with_next(20, has_next=False),  # fim real
        ]
        result = onboard._fetch_saved(sp)
        # Antes reportaria 80 (parou em len<50 na segunda página).
        # Agora reporta os 150 reais.
        assert len(result) == 150

    def test_compat_para_sem_campo_next(self):
        """Spotify às vezes omite `next` em respostas antigas/mocks. Fallback
        para heurística de tamanho se campo ausente."""
        sp = MagicMock()
        sp.current_user_saved_tracks.side_effect = [
            {"items": [
                {"track": {"uri": f"spotify:track:a{i}", "name": f"A{i}",
                           "artists": [{"name": "X"}]}}
                for i in range(50)
            ]},
            {"items": []},
        ]
        result = onboard._fetch_saved(sp)
        assert len(result) == 50


class TestPlaylistRename:
    """v0.5.2 (bug 5): --playlist-id + --playlist-name renomeia a
    playlist no Spotify se nome atual diferir."""

    def test_rename_quando_nome_difere(self, tmp_path, monkeypatch):
        from maestra_ai.core.taste import TasteProfile

        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))

        sp = _make_sp(top_long=1, saved_pages=[{"items": []}])
        sp.playlist.return_value = {"name": "My Playlist #7"}

        taste = TasteProfile(tmp_path / "taste.json")
        report = onboard.run(
            sp, taste,
            playlist_name="Maestra",
            existing_playlist_id="pl_existing",
            seed_count=0,
        )

        sp.playlist_change_details.assert_called_once_with(
            "pl_existing", name="Maestra"
        )
        assert report["playlist_name"] == "Maestra"

    def test_nao_renomeia_se_nome_igual(self, tmp_path, monkeypatch):
        from maestra_ai.core.taste import TasteProfile

        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))

        sp = _make_sp(top_long=1, saved_pages=[{"items": []}])
        sp.playlist.return_value = {"name": "Maestra"}

        taste = TasteProfile(tmp_path / "taste.json")
        onboard.run(
            sp, taste,
            playlist_name="Maestra",
            existing_playlist_id="pl_existing",
            seed_count=0,
        )

        sp.playlist_change_details.assert_not_called()

    def test_rename_falhando_nao_bloqueia_onboard(self, tmp_path, monkeypatch):
        from maestra_ai.core.taste import TasteProfile

        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))

        sp = _make_sp(top_long=1, saved_pages=[{"items": []}])
        sp.playlist.return_value = {"name": "My Playlist #7"}
        sp.playlist_change_details.side_effect = RuntimeError("403 forbidden")

        taste = TasteProfile(tmp_path / "taste.json")
        report = onboard.run(
            sp, taste,
            playlist_name="Maestra",
            existing_playlist_id="pl_existing",
            seed_count=0,
        )
        # Mantém nome atual quando rename falha, onboard segue normalmente.
        assert report["playlist_name"] == "My Playlist #7"
        assert report["status"] == "ok"


class TestPlaylistCreate403:
    """v0.5.2: 403 ao criar playlist vira PlaylistCreateForbiddenError
    com probable_causes acionáveis (Development Mode, User Management,
    propagação, Premium), não stack trace cru."""

    def test_403_vira_playlist_create_forbidden_error(self, tmp_path, monkeypatch):
        import pytest

        from maestra_ai.core.errors import PlaylistCreateForbiddenError
        from maestra_ai.core.taste import TasteProfile

        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))

        # spotipy.SpotifyException tem http_status e a string contém "403".
        class FakeSpotifyException(Exception):
            def __init__(self):
                super().__init__("http status: 403 - Forbidden")
                self.http_status = 403

        sp = _make_sp(top_long=5, top_short=5, saved_pages=[{"items": []}], recent=3)
        sp.current_user.return_value = {
            "id": "user_x",
            "email": "x@example.com",
            "country": "BR",
            "product": "premium",
        }
        sp.user_playlist_create.side_effect = FakeSpotifyException()

        taste = TasteProfile(tmp_path / "taste.json")
        with pytest.raises(PlaylistCreateForbiddenError) as exc:
            onboard.run(sp, taste, playlist_name="Maestra")

        err = exc.value.to_human_dict()
        # Título específico, não genérico.
        assert "403" in err["title"]
        # Causes devem citar Development Mode e User Management.
        joined = " ".join(err["probable_causes"]).lower()
        assert "development mode" in joined
        assert "user management" in joined
        # Action sugerida inclui contorno via --playlist-id.
        actions = " ".join(a["command"] for a in err["suggested_actions"])
        assert "--playlist-id" in actions
        # where preserva contexto para debug.
        assert err["where"]["user_id"] == "user_x"
        assert err["where"]["product"] == "premium"

    def test_outros_erros_continuam_subindo(self, tmp_path, monkeypatch):
        """Não deve engolir 500/rede/timeout — só o 403 é tratado."""
        import pytest

        from maestra_ai.core.taste import TasteProfile

        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))

        sp = _make_sp(top_long=5, top_short=5, saved_pages=[{"items": []}], recent=3)
        sp.user_playlist_create.side_effect = RuntimeError("network timeout")

        taste = TasteProfile(tmp_path / "taste.json")
        with pytest.raises(RuntimeError, match="network timeout"):
            onboard.run(sp, taste, playlist_name="Maestra")


class TestRun:
    def test_dry_run_nao_cria_playlist(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
        sp = _make_sp(top_long=5, top_short=5, saved_pages=[{"items": []}], recent=3)

        from maestra_ai.core.taste import TasteProfile
        taste = TasteProfile(str(tmp_path / "taste.json"))

        report = onboard.run(sp, taste, playlist_name="X", seed_count=0, dry_run=True)

        sp.user_playlist_create.assert_not_called()
        sp.playlist_add_items.assert_not_called()
        assert report["status"] == "ok"

    def test_biblioteca_vazia_retorna_zeros(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
        sp = _make_sp(saved_pages=[{"items": []}])

        from maestra_ai.core.taste import TasteProfile
        taste = TasteProfile(str(tmp_path / "taste.json"))

        report = onboard.run(sp, taste, playlist_name="X", seed_count=0, dry_run=True)
        assert report["saved_tracks_fetched"] == 0
        assert report["top_long_count"] == 0
        assert report["recent_count"] == 0

    def test_popula_taste_profile_com_sinais_globais(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
        sp = _make_sp(top_long=3, top_short=2, saved_pages=[{"items": []}], recent=1)

        from maestra_ai.core.taste import TasteProfile
        taste = TasteProfile(str(tmp_path / "taste.json"))

        # dry_run=False para registrar sinais no taste
        onboard.run(sp, taste, playlist_name="X", seed_count=0, dry_run=False)

        tracks_with_signal = [
            t for t in taste.data["tracks"].values()
            if (t.get("global_signal") or 0) > 0
        ]
        assert len(tracks_with_signal) >= 3

    def test_cria_playlist_com_sufixo_se_nome_existe(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
        sp = _make_sp(saved_pages=[{"items": []}])
        sp.current_user_playlists.return_value = {
            "items": [{"name": "Maestra", "id": "pl_old"}],
        }

        from maestra_ai.core.taste import TasteProfile
        taste = TasteProfile(str(tmp_path / "taste.json"))

        onboard.run(sp, taste, playlist_name="Maestra", seed_count=0, dry_run=False)

        call_args = sp.user_playlist_create.call_args
        assert call_args is not None
        created_name = call_args.kwargs.get("name") or call_args.args[1]
        assert created_name == "Maestra (2)"

    def test_progress_callback_recebe_todas_etapas(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
        sp = _make_sp(saved_pages=[{"items": []}])

        from maestra_ai.core.taste import TasteProfile
        taste = TasteProfile(str(tmp_path / "taste.json"))

        steps = []
        onboard.run(
            sp, taste,
            playlist_name="X", seed_count=0, dry_run=True,
            progress_cb=lambda ev: steps.append(ev),
        )
        step_numbers = {s.get("step") for s in steps if "step" in s}
        assert step_numbers >= {1, 2, 3, 4, 5, 6}

    def test_derive_suggestions_retorna_5_strings(self):
        tracks = [
            {"uri": f"u{i}", "artists": [{"name": f"Ar{i%3}"}]} for i in range(50)
        ]
        suggestions = onboard._derive_suggestions(tracks)
        assert len(suggestions) == 5
        for s in suggestions:
            assert isinstance(s, str) and len(s) > 0

    def test_seed_playlist_usa_top_short(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
        sp = _make_sp(top_short=10, saved_pages=[{"items": []}])

        from maestra_ai.core.taste import TasteProfile
        taste = TasteProfile(str(tmp_path / "taste.json"))

        report = onboard.run(sp, taste, playlist_name="X", seed_count=5, dry_run=False)

        sp.playlist_add_items.assert_called_once()
        uris_arg = sp.playlist_add_items.call_args.args[1]
        assert len(uris_arg) == 5
        assert report["seeded"] == 5

    def test_playlist_id_salvo_em_config(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
        sp = _make_sp(saved_pages=[{"items": []}])

        from maestra_ai.core import storage
        from maestra_ai.core.taste import TasteProfile
        taste = TasteProfile(str(tmp_path / "taste.json"))

        onboard.run(sp, taste, playlist_name="X", seed_count=0, dry_run=False)

        cfg = storage.read_config()
        assert cfg.get("playlist_id") == "pl_new"
        assert cfg.get("playlist_name") == "X"


class TestTasteRecordGlobalPositive:
    def test_cria_entrada_se_uri_nova(self, tmp_path):
        from maestra_ai.core.taste import TasteProfile
        t = TasteProfile(str(tmp_path / "taste.json"))
        t.record_global_positive("spotify:track:a", name="Track A", artist="Artist A", weight=3)
        assert t.data["tracks"]["spotify:track:a"]["global_signal"] == 3
        assert t.data["tracks"]["spotify:track:a"]["name"] == "Track A"

    def test_soma_ao_existente(self, tmp_path):
        from maestra_ai.core.taste import TasteProfile
        t = TasteProfile(str(tmp_path / "taste.json"))
        t.record_global_positive("spotify:track:a", weight=2)
        t.record_global_positive("spotify:track:a", weight=3)
        assert t.data["tracks"]["spotify:track:a"]["global_signal"] == 5


class TestSavedRepesoEcap:
    """v0.4.5: Liked Songs ganha peso 3 (igual ao top_long_term) e cap 5000."""

    def test_saved_tem_peso_3(self):
        assert onboard.WEIGHTS["saved"] == 3

    def test_saved_cap_padrao_5000(self):
        assert onboard._MAX_SAVED == 5000

    def test_saved_cap_parametro_sobrescreve(self):
        # max_tracks=100 limita o fetch mesmo com muitas páginas disponíveis.
        sp = MagicMock()
        sp.current_user_saved_tracks.side_effect = [_fake_saved(50)] * 10 + [{"items": []}]
        result = onboard._fetch_saved(sp, max_tracks=100)
        assert len(result) == 100

    def test_compute_weights_usa_novo_peso_saved(self):
        w = onboard._compute_weights(
            top_long=[], top_medium=[], top_short=[],
            saved=[{"uri": "spotify:track:only_saved"}],
            recent=[],
        )
        assert w["spotify:track:only_saved"] == 3

    def test_run_com_saved_cap_customizado(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
        sp = _make_sp(saved_pages=[_fake_saved(50)] * 4 + [{"items": []}])

        from maestra_ai.core.taste import TasteProfile
        taste = TasteProfile(str(tmp_path / "taste.json"))

        report = onboard.run(
            sp, taste, playlist_name="X", seed_count=0, dry_run=True,
            saved_cap=75,
        )
        assert report["saved_tracks_fetched"] == 75


class TestRunComExistingPlaylistId:
    """v0.4.5 parte 2: onboard aceita playlist pré-existente via existing_playlist_id."""

    def test_run_com_existing_playlist_id_nao_cria(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
        sp = _make_sp(saved_pages=[{"items": []}])
        sp.playlist.return_value = {"name": "Playlist Existente"}

        from maestra_ai.core.taste import TasteProfile
        taste = TasteProfile(str(tmp_path / "taste.json"))

        # v0.5.2: passando playlist_name vazio ou igual ao atual evita rename.
        report = onboard.run(
            sp, taste, playlist_name="Playlist Existente", seed_count=0,
            dry_run=False, existing_playlist_id="pl_X",
        )

        sp.user_playlist_create.assert_not_called()
        sp.playlist.assert_called()
        sp.playlist_change_details.assert_not_called()
        assert report["playlist_id"] == "pl_X"
        assert report["playlist_name"] == "Playlist Existente"

        from maestra_ai.core import storage
        cfg = storage.read_config()
        assert cfg.get("playlist_id") == "pl_X"
        assert cfg.get("playlist_name") == "Playlist Existente"

    def test_run_com_existing_playlist_id_semeia_nele(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
        sp = _make_sp(top_short=10, saved_pages=[{"items": []}])
        sp.playlist.return_value = {"name": "PL"}

        from maestra_ai.core.taste import TasteProfile
        taste = TasteProfile(str(tmp_path / "taste.json"))

        onboard.run(
            sp, taste, playlist_name="ignorado", seed_count=10,
            dry_run=False, existing_playlist_id="pl_X",
        )

        sp.playlist_add_items.assert_called_once()
        args = sp.playlist_add_items.call_args.args
        assert args[0] == "pl_X"


class TestOnboardToleraTrackNone:
    """CRITICAL-4: _fetch_saved / _fetch_recent devem ignorar items com track=None."""

    def test_fetch_saved_ignora_track_none(self):
        from maestra_ai.core import onboard as onboard_mod
        sp = MagicMock()
        sp.current_user_saved_tracks.return_value = {
            "items": [
                {"track": None},
                {"track": {"uri": "spotify:track:ok", "name": "OK"}},
            ],
        }
        result = onboard_mod._fetch_saved(sp)
        # Só o track não-nulo
        assert all(t is not None and t.get("uri") for t in result)
        assert len(result) == 1

    def test_fetch_recent_ignora_track_none(self):
        from maestra_ai.core import onboard as onboard_mod
        sp = MagicMock()
        sp.current_user_recently_played.return_value = {
            "items": [
                {"track": None},
                {"track": {"uri": "spotify:track:a", "name": "A"}},
            ],
        }
        result = onboard_mod._fetch_recent(sp)
        assert len(result) == 1
        assert result[0]["uri"] == "spotify:track:a"
