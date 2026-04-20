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


class TestFetchOwnPlaylists:
    """v0.5.3: expansão por playlists exige listar APENAS as que o
    próprio usuário criou (owner.id == me.id), não as seguidas."""

    def test_filtra_apenas_playlists_criadas_pelo_usuario(self):
        from unittest.mock import MagicMock
        sp = MagicMock()
        sp.current_user_playlists.side_effect = [
            {
                "items": [
                    {"id": "p1", "name": "Minha A", "owner": {"id": "me"},
                     "tracks": {"total": 20}},
                    {"id": "p2", "name": "Today's Top Hits",
                     "owner": {"id": "spotify"}, "tracks": {"total": 50}},
                    {"id": "p3", "name": "Minha B", "owner": {"id": "me"},
                     "tracks": {"total": 10}},
                ],
                "next": None,
            },
        ]
        result, empty_count = onboard._fetch_own_playlists(sp, me_id="me")
        ids = [p["id"] for p in result]
        assert "p1" in ids
        assert "p3" in ids
        assert "p2" not in ids  # seguida, não própria
        assert empty_count == 0

    def test_filtra_playlists_vazias_e_conta(self):
        """v0.5.5 #4 + v0.5.7 #17: filtra vazias e retorna contagem delas
        (para o CLI distinguir 'zero' de 'todas vazias')."""
        from unittest.mock import MagicMock
        sp = MagicMock()
        sp.current_user_playlists.side_effect = [
            {
                "items": [
                    {"id": "p1", "name": "Com faixas", "owner": {"id": "me"},
                     "tracks": {"total": 5}},
                    {"id": "p2", "name": "Vazia", "owner": {"id": "me"},
                     "tracks": {"total": 0}},
                    {"id": "p3", "name": "Sem tracks info", "owner": {"id": "me"},
                     "tracks": None},
                ],
                "next": None,
            },
        ]
        result, empty_count = onboard._fetch_own_playlists(sp, me_id="me")
        ids = [p["id"] for p in result]
        assert ids == ["p1"]
        assert empty_count == 2  # p2 (total=0) e p3 (tracks=None)

    def test_pagina_ate_next_null(self):
        from unittest.mock import MagicMock
        sp = MagicMock()
        sp.current_user_playlists.side_effect = [
            {"items": [{"id": "p1", "name": "A", "owner": {"id": "me"},
                        "tracks": {"total": 5}}],
             "next": "url1"},
            {"items": [{"id": "p2", "name": "B", "owner": {"id": "me"},
                        "tracks": {"total": 5}}],
             "next": None},
        ]
        result, _ = onboard._fetch_own_playlists(sp, me_id="me")
        assert len(result) == 2

    def test_guarda_contra_loop_infinito_items_vazio_com_next(self):
        """v0.5.3.1 (C2): Spotify pode retornar items=[] com next != None
        em rate-limit soft. Sem guarda, offset não avança e loop fica
        preso infinitamente. Para imediatamente quando items vazio.
        """
        from unittest.mock import MagicMock
        sp = MagicMock()
        sp.current_user_playlists.side_effect = [
            {"items": [{"id": "p1", "name": "A", "owner": {"id": "me"},
                        "tracks": {"total": 5}}],
             "next": "url1"},
            {"items": [], "next": "url2"},  # patológica
            {"items": [{"id": "p99", "name": "Z", "owner": {"id": "me"},
                        "tracks": {"total": 5}}],
             "next": None},
        ]
        result, _ = onboard._fetch_own_playlists(sp, me_id="me")
        assert len(result) == 1
        assert result[0]["id"] == "p1"
        assert sp.current_user_playlists.call_count == 2

    def test_reason_only_empty_playlists_quando_todas_vazias(
        self, tmp_path, monkeypatch,
    ):
        """v0.5.7 #17: usuário com N playlists próprias mas todas com
        track_count=0 gera reason='only_empty_playlists' (distinto de
        'no_own_playlists') e own_playlists_empty_count=N."""
        from maestra_ai.core.taste import TasteProfile
        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))

        sp = TestPlaylistExpansion()._sp_with_playlists(
            own_playlists=[
                {"id": "p1", "name": "Vazia A", "owner": {"id": "me"},
                 "tracks": {"total": 0}},
                {"id": "p2", "name": "Vazia B", "owner": {"id": "me"},
                 "tracks": {"total": 0}},
            ],
        )

        taste = TasteProfile(tmp_path / "taste.json")
        report = onboard.run(
            sp, taste, playlist_name="M", seed_count=0,
            playlist_selector=lambda pls, ctx: [],
        )
        exp = report["playlist_expansion"]
        assert exp["reason"] == "only_empty_playlists"
        assert exp["own_playlists_empty_count"] == 2
        assert exp["offered_playlists"] == 0


class TestFetchPlaylistTracks:
    def test_pagina_tracks_via_next(self):
        from unittest.mock import MagicMock
        sp = MagicMock()
        sp.playlist_items.side_effect = [
            {"items": [
                {"track": {"uri": f"spotify:track:p{i}", "name": f"T{i}",
                           "artists": [{"name": "X"}]}}
                for i in range(100)
            ], "next": "url"},
            {"items": [
                {"track": {"uri": f"spotify:track:q{i}", "name": f"U{i}",
                           "artists": [{"name": "Y"}]}}
                for i in range(50)
            ], "next": None},
        ]
        result = onboard._fetch_playlist_tracks(sp, "pl1", max_tracks=1000)
        assert len(result) == 150

    def test_respeita_max_tracks(self):
        from unittest.mock import MagicMock
        sp = MagicMock()
        sp.playlist_items.return_value = {
            "items": [
                {"track": {"uri": f"spotify:track:z{i}", "name": f"Z{i}",
                           "artists": [{"name": "Z"}]}}
                for i in range(100)
            ],
            "next": "url",
        }
        result = onboard._fetch_playlist_tracks(sp, "pl1", max_tracks=30)
        assert len(result) == 30

    def test_passa_fields_restrito_ao_api_spotify(self):
        """v0.5.5 #3: playlist_items é chamado com fields= restringindo
        payload ao mínimo necessário (uri, name, artists.name + next)."""
        from unittest.mock import MagicMock
        sp = MagicMock()
        sp.playlist_items.return_value = {"items": [], "next": None}
        onboard._fetch_playlist_tracks(sp, "pl1", max_tracks=10)
        call = sp.playlist_items.call_args
        assert call.kwargs.get("fields") == \
            "items(track(uri,name,artists(name))),next"

    def test_ignora_tracks_none(self):
        """Faixas removidas do catálogo ou locais vêm como track=None."""
        from unittest.mock import MagicMock
        sp = MagicMock()
        sp.playlist_items.side_effect = [
            {"items": [
                {"track": None},
                {"track": {"uri": "spotify:track:ok", "name": "OK",
                           "artists": [{"name": "A"}]}},
                {"track": {"uri": None}},  # track sem URI
            ], "next": None},
        ]
        result = onboard._fetch_playlist_tracks(sp, "pl1", max_tracks=10)
        assert len(result) == 1
        assert result[0]["uri"] == "spotify:track:ok"


class TestPlaylistWeight:
    def test_peso_playlist_eh_2(self):
        assert onboard.WEIGHTS.get("playlist") == 2


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


class TestPlaylistExpansion:
    """v0.5.3: expansão opcional por playlists próprias quando total < cap."""

    def _sp_with_playlists(self, saved_pages=None, own_playlists=None,
                            playlist_tracks=None):
        sp = _make_sp(
            top_long=10, top_medium=10, top_short=10,
            saved_pages=saved_pages or [{"items": []}],
            recent=5,
        )
        sp.current_user.return_value = {"id": "me"}
        # Usa callable para tolerar múltiplas chamadas de clientes distintos
        # (ex: _resolve_playlist_name + _fetch_own_playlists).
        _own = list(own_playlists or [])

        def _playlists_side(limit=50, offset=0):
            if offset == 0:
                return {"items": _own, "next": None}
            return {"items": [], "next": None}

        sp.current_user_playlists.side_effect = _playlists_side
        if playlist_tracks is not None:
            # Cada chamada a playlist_items devolve tracks de uma playlist
            sp.playlist_items.side_effect = [
                {"items": [{"track": t} for t in plts], "next": None}
                for plts in playlist_tracks
            ]
        return sp

    def _playlist_dict(self, pid, name, owner="me", total=10):
        return {"id": pid, "name": name, "owner": {"id": owner},
                "tracks": {"total": total}}

    def test_expansao_pula_quando_selector_none(self, tmp_path, monkeypatch):
        from maestra_ai.core.taste import TasteProfile
        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
        sp = self._sp_with_playlists()
        taste = TasteProfile(tmp_path / "taste.json")
        report = onboard.run(sp, taste, playlist_name="M", seed_count=0,
                              playlist_selector=None)
        assert report["playlist_expansion"]["attempted"] is False
        # v0.5.6 #10: reason sempre preenchido, vocabulário fechado.
        assert report["playlist_expansion"]["reason"] == "selector_not_provided"

    def test_reason_cap_already_reached_quando_total_ja_cobre(
        self, tmp_path, monkeypatch,
    ):
        """v0.5.6 #10: usuário com biblioteca grande pode já superar o cap
        antes da oferta — agente precisa distinguir esse caso de outros."""
        from maestra_ai.core.taste import TasteProfile
        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
        sp = self._sp_with_playlists()
        selector_called = {"yes": False}

        def selector(pls, ctx):
            selector_called["yes"] = True
            return []

        taste = TasteProfile(tmp_path / "taste.json")
        # total atual = 10+10+10+5 = 35 URIs únicos; total_cap=30 (menor).
        report = onboard.run(
            sp, taste, playlist_name="M", seed_count=0,
            playlist_selector=selector, total_cap=30,
        )
        assert report["playlist_expansion"]["attempted"] is False
        assert report["playlist_expansion"]["reason"] == "cap_already_reached"
        assert selector_called["yes"] is False  # não foi chamado

    def test_reason_ok_no_caminho_feliz(self, tmp_path, monkeypatch):
        """v0.5.6 #10: reason='ok' quando tracks_added > 0."""
        from maestra_ai.core.taste import TasteProfile
        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
        sp = self._sp_with_playlists(
            own_playlists=[self._playlist_dict("p1", "A", total=2)],
            playlist_tracks=[
                [{"uri": "spotify:track:x", "name": "X",
                  "artists": [{"name": "Y"}]}],
            ],
        )
        taste = TasteProfile(tmp_path / "taste.json")
        report = onboard.run(
            sp, taste, playlist_name="M", seed_count=0,
            playlist_selector=lambda pls, ctx: ["p1"],
        )
        assert report["playlist_expansion"]["reason"] == "ok"
        assert report["playlist_expansion"]["tracks_added"] == 1

    def test_expansao_sem_playlists_proprias_reporta_motivo(self, tmp_path, monkeypatch):
        from maestra_ai.core.taste import TasteProfile
        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
        # usuário não tem playlists próprias (só seguidas de "spotify")
        sp = self._sp_with_playlists(own_playlists=[
            self._playlist_dict("p1", "Today's Top Hits", owner="spotify"),
        ])
        selector_called = {"yes": False}

        def selector(pls, ctx):
            selector_called["yes"] = True
            return []

        taste = TasteProfile(tmp_path / "taste.json")
        report = onboard.run(sp, taste, playlist_name="M", seed_count=0,
                              playlist_selector=selector)
        assert report["playlist_expansion"]["attempted"] is True
        assert report["playlist_expansion"]["offered_playlists"] == 0
        assert report["playlist_expansion"]["reason"] == "no_own_playlists"
        # selector NÃO é chamado se lista vazia (evita UX confusa "escolha entre 0 opções")
        assert selector_called["yes"] is False

    def test_reason_selector_returned_empty(self, tmp_path, monkeypatch):
        """v0.5.6 #10: 'user_skipped' virou 'selector_returned_empty' no core —
        termo de UI (CLI traduz para "dispensada")."""
        from maestra_ai.core.taste import TasteProfile
        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
        sp = self._sp_with_playlists(
            own_playlists=[self._playlist_dict("p1", "A", total=3)],
        )
        taste = TasteProfile(tmp_path / "taste.json")
        report = onboard.run(
            sp, taste, playlist_name="M", seed_count=0,
            playlist_selector=lambda pls, ctx: [],
        )
        assert report["playlist_expansion"]["reason"] == "selector_returned_empty"

    def test_expansao_com_selecao_adiciona_faixas_com_peso_2(
        self, tmp_path, monkeypatch,
    ):
        from maestra_ai.core.taste import TasteProfile
        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
        sp = self._sp_with_playlists(
            own_playlists=[
                self._playlist_dict("p1", "Minha A", total=2),
                self._playlist_dict("p2", "Minha B", total=2),
            ],
            playlist_tracks=[
                # p1: 2 tracks, uma nova uma duplicada com saved
                [{"uri": "spotify:track:new1", "name": "N1",
                  "artists": [{"name": "A"}]},
                 {"uri": "spotify:track:new2", "name": "N2",
                  "artists": [{"name": "B"}]}],
            ],
        )

        def selector(pls, ctx):
            # agente escolhe só a primeira
            return ["p1"]

        taste = TasteProfile(tmp_path / "taste.json")
        report = onboard.run(sp, taste, playlist_name="M", seed_count=0,
                              playlist_selector=selector)
        assert report["playlist_expansion"]["tracks_added"] == 2
        # v0.5.7 #19: selected_playlists guarda {id, name}.
        assert report["playlist_expansion"]["selected_playlists"] == [
            {"id": "p1", "name": "Minha A"},
        ]
        # taste.data["tracks"][uri]["global_signal"] deve ter peso 2 (playlist)
        tracks = taste.data.get("tracks", {})
        assert tracks.get("spotify:track:new1", {}).get("global_signal") == 2
        assert tracks.get("spotify:track:new2", {}).get("global_signal") == 2

    def test_falha_em_uma_playlist_registra_em_failed_playlists(
        self, tmp_path, monkeypatch,
    ):
        """v0.5.5 #6-#7: se fetch de uma playlist falha (race, timeout),
        expansion_info.failed_playlists registra o id e a razão —
        sem engolir silenciosamente nem abortar a expansão."""

        from maestra_ai.core.taste import TasteProfile

        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))

        sp = self._sp_with_playlists(
            own_playlists=[
                self._playlist_dict("p1", "Boa", total=3),
                self._playlist_dict("p2", "Deletada entre list+fetch", total=5),
                self._playlist_dict("p3", "Outra boa", total=2),
            ],
        )
        # playlist_items: p1 ok, p2 levanta (race), p3 ok
        sp.playlist_items.side_effect = [
            {"items": [{"track": {"uri": "spotify:track:a", "name": "A",
                                   "artists": [{"name": "X"}]}}], "next": None},
            Exception("404 Not Found — playlist deletada"),
            {"items": [{"track": {"uri": "spotify:track:b", "name": "B",
                                   "artists": [{"name": "Y"}]}}], "next": None},
        ]

        def selector(pls, ctx):
            return ["p1", "p2", "p3"]

        taste = TasteProfile(tmp_path / "taste.json")
        report = onboard.run(
            sp, taste, playlist_name="M", seed_count=0,
            playlist_selector=selector,
        )
        exp = report["playlist_expansion"]
        assert exp["tracks_added"] == 2  # p1 + p3
        assert len(exp["failed_playlists"]) == 1
        assert exp["failed_playlists"][0]["id"] == "p2"
        assert "404" in exp["failed_playlists"][0]["reason"]

    def test_expansao_respeita_total_cap(self, tmp_path, monkeypatch):
        from maestra_ai.core.taste import TasteProfile
        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
        sp = self._sp_with_playlists(
            own_playlists=[self._playlist_dict("p1", "Grande", total=100)],
            playlist_tracks=[
                [{"uri": f"spotify:track:big{i}", "name": f"B{i}",
                  "artists": [{"name": "X"}]} for i in range(100)],
            ],
        )

        def selector(pls, ctx):
            return ["p1"]

        taste = TasteProfile(tmp_path / "taste.json")
        # Com total_cap baixo, só adiciona o que cabe.
        # top+recent já trouxe 10+10+10+5 = 35 URIs únicos.
        report = onboard.run(
            sp, taste, playlist_name="M", seed_count=0,
            playlist_selector=selector, total_cap=40,
        )
        # total_cap=40 - 35 já vistos = 5 vagas
        assert report["playlist_expansion"]["tracks_added"] == 5


class TestExpansionPropagaAuthError:
    """M2 v0.6.2: AuthError em _fetch_own_playlists propaga;
    não vira 'no_own_playlists' silencioso."""

    def test_auth_error_durante_fetch_playlists_nao_eh_silenciado(
        self, tmp_path, monkeypatch,
    ):
        import pytest

        from maestra_ai.core.errors import AuthError
        from maestra_ai.core.taste import TasteProfile

        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))

        sp = TestPlaylistExpansion()._sp_with_playlists()
        # _resolve_playlist_name chama current_user_playlists antes de
        # _fetch_own_playlists. Primeira chamada devolve lista vazia (sem colisão
        # de nome); segunda chamada (dentro de _fetch_own_playlists) levanta
        # AuthError — esse é o cenário que queremos testar.
        sp.current_user_playlists.side_effect = [
            {"items": [], "next": None},   # _resolve_playlist_name — ok
            AuthError("revoked"),           # _fetch_own_playlists — deve propagar
        ]

        taste = TasteProfile(tmp_path / "taste.json")
        with pytest.raises(AuthError, match="revoked"):
            onboard.run(
                sp, taste, playlist_name="M", seed_count=0,
                playlist_selector=lambda pls, ctx: [],
                total_cap=5000,
            )


class TestExpansionEdgeCases:
    """v0.5.6 #25: edge cases do contrato do selector."""

    def test_selector_que_levanta_excecao_propaga(self, tmp_path, monkeypatch):
        """Selector é código do CLI/agente. Se levanta, não queremos
        swallow silencioso — deixa subir para diagnóstico."""
        from maestra_ai.core.taste import TasteProfile
        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))

        sp = TestPlaylistExpansion()._sp_with_playlists(
            own_playlists=[
                {"id": "p1", "name": "A", "owner": {"id": "me"},
                 "tracks": {"total": 5}},
            ],
        )

        def buggy_selector(_pls, _ctx):
            raise ValueError("selector com bug")

        taste = TasteProfile(tmp_path / "taste.json")
        import pytest
        with pytest.raises(ValueError, match="selector com bug"):
            onboard.run(
                sp, taste, playlist_name="M", seed_count=0,
                playlist_selector=buggy_selector,
            )

    def test_selector_retorna_ids_fora_da_lista_fetcher_registra_falha(
        self, tmp_path, monkeypatch,
    ):
        """Agente pode passar IDs que não estão na lista oferecida
        (via cache antigo, typo). Fetch falha por ID inválido ou
        permissão; failed_playlists registra."""
        from maestra_ai.core.taste import TasteProfile
        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))

        sp = TestPlaylistExpansion()._sp_with_playlists(
            own_playlists=[
                {"id": "p1", "name": "A", "owner": {"id": "me"},
                 "tracks": {"total": 5}},
            ],
        )
        sp.playlist_items.side_effect = Exception(
            "404 — playlist não pertence ao usuário",
        )

        def selector(_pls, _ctx):
            return ["id_que_nao_esta_na_lista"]

        taste = TasteProfile(tmp_path / "taste.json")
        report = onboard.run(
            sp, taste, playlist_name="M", seed_count=0,
            playlist_selector=selector,
        )
        exp = report["playlist_expansion"]
        assert exp["tracks_added"] == 0
        assert len(exp["failed_playlists"]) == 1
        assert exp["failed_playlists"][0]["id"] == "id_que_nao_esta_na_lista"


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
        # noqa N818: nome replica o nome real da exceção do spotipy
        # (SpotifyException, sem sufixo Error), mantido para simular fielmente.
        class FakeSpotifyException(Exception):  # noqa: N818
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


class TestExpansionContextShape:
    """v0.6.0: core constrói ExpansionContext corretamente e passa ao
    selector. Contrato novo (2-arg), hard break do antigo."""

    def test_ctx_tem_total_cap_igual_ao_configurado(self, tmp_path, monkeypatch):
        from maestra_ai.core.taste import TasteProfile
        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))

        sp = TestPlaylistExpansion()._sp_with_playlists(
            own_playlists=[
                {"id": "p1", "name": "A", "owner": {"id": "me"},
                 "tracks": {"total": 3}},
            ],
        )
        captured = {}

        def spy_selector(pls, ctx):
            captured["ctx"] = dict(ctx)
            return []

        taste = TasteProfile(tmp_path / "taste.json")
        onboard.run(
            sp, taste, playlist_name="M", seed_count=0,
            playlist_selector=spy_selector, total_cap=777,
        )
        assert captured["ctx"]["total_cap"] == 777

    def test_ctx_current_total_eh_uniao_de_fontes(self, tmp_path, monkeypatch):
        """current_total = |top_long + top_medium + top_short + saved + recent|."""
        from maestra_ai.core.taste import TasteProfile
        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))

        # _sp_with_playlists() chama _make_sp(top_long=10, top_medium=10,
        # top_short=10, recent=5, saved=0) internamente — produz 35 URIs
        # únicos (prefixos distintos).
        sp = TestPlaylistExpansion()._sp_with_playlists(
            own_playlists=[
                {"id": "p1", "name": "A", "owner": {"id": "me"},
                 "tracks": {"total": 3}},
            ],
        )
        captured = {}

        def spy_selector(pls, ctx):
            captured["ctx"] = dict(ctx)
            return []

        taste = TasteProfile(tmp_path / "taste.json")
        onboard.run(
            sp, taste, playlist_name="M", seed_count=0,
            playlist_selector=spy_selector, total_cap=5000,
        )
        assert captured["ctx"]["current_total"] == 35

    def test_ctx_remaining_eh_diferenca(self, tmp_path, monkeypatch):
        from maestra_ai.core.taste import TasteProfile
        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))

        sp = TestPlaylistExpansion()._sp_with_playlists(
            own_playlists=[
                {"id": "p1", "name": "A", "owner": {"id": "me"},
                 "tracks": {"total": 3}},
            ],
        )
        captured = {}

        def spy_selector(pls, ctx):
            captured["ctx"] = dict(ctx)
            return []

        taste = TasteProfile(tmp_path / "taste.json")
        onboard.run(
            sp, taste, playlist_name="M", seed_count=0,
            playlist_selector=spy_selector, total_cap=100,
        )
        # current_total=35, total_cap=100 → remaining=65
        assert captured["ctx"]["remaining"] == 65

    def test_selector_com_assinatura_antiga_1arg_levanta_type_error(
        self, tmp_path, monkeypatch,
    ):
        """v0.6.0 hard break: selector com assinatura antiga (1 arg)
        levanta TypeError quando core o chama com 2 args. Confirma
        que a quebra é intencional e observável."""
        import pytest

        from maestra_ai.core.taste import TasteProfile
        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))

        sp = TestPlaylistExpansion()._sp_with_playlists(
            own_playlists=[
                {"id": "p1", "name": "A", "owner": {"id": "me"},
                 "tracks": {"total": 3}},
            ],
        )

        # Assinatura antiga — só 1 arg.
        old_selector = lambda pls: []  # noqa: E731

        taste = TasteProfile(tmp_path / "taste.json")
        with pytest.raises(TypeError, match="positional argument"):
            onboard.run(
                sp, taste, playlist_name="M", seed_count=0,
                playlist_selector=old_selector,
            )


class TestResolvePlaylistName:
    """M1 v0.6.2: _resolve_playlist_name propaga MaestraError em vez
    de engolir; fallback só para shape inesperado."""

    def test_propaga_auth_error_e_nao_silencia(self):
        from unittest.mock import MagicMock

        import pytest

        from maestra_ai.core.errors import AuthError

        sp = MagicMock()
        sp.current_user_playlists.side_effect = AuthError("token revogado")

        with pytest.raises(AuthError, match="token revogado"):
            onboard._resolve_playlist_name(sp, "Maestra")

    def test_propaga_rate_limit_error(self):
        from unittest.mock import MagicMock

        import pytest

        from maestra_ai.core.errors import RateLimitError

        sp = MagicMock()
        sp.current_user_playlists.side_effect = RateLimitError(
            "429", retry_after=30,
        )
        with pytest.raises(RateLimitError):
            onboard._resolve_playlist_name(sp, "Maestra")

    def test_retorna_desired_quando_shape_inesperada(self):
        """AttributeError/TypeError em resp.get(...) → fallback benigno."""
        from unittest.mock import MagicMock

        sp = MagicMock()
        sp.current_user_playlists.return_value = object()
        assert onboard._resolve_playlist_name(sp, "Maestra") == "Maestra"


class TestFetchOwnPlaylistsCap:
    """M6 v0.6.2: _fetch_own_playlists tem cap de 200 páginas contra
    loop infinito (bug de servidor, mock quebrado, Spotify retornando
    `next` indefinidamente)."""

    def test_para_em_200_paginas_mesmo_com_next_infinito(self):
        from unittest.mock import MagicMock
        sp = MagicMock()
        call_count = {"n": 0}

        def _pages(limit, offset):
            call_count["n"] += 1
            return {
                "items": [
                    {
                        "id": f"p{offset}",
                        "name": f"pl{offset}",
                        "owner": {"id": "me"},
                        "tracks": {"total": 3},
                    },
                ],
                "next": "https://api.spotify.com/next-page-fake",  # nunca None
            }

        sp.current_user_playlists.side_effect = _pages

        collected, _empty = onboard._fetch_own_playlists(sp, me_id="me")
        assert call_count["n"] <= 200
        assert len(collected) == 200




class TestDecadeOf:
    """_decade_of converte release_date em década legível."""

    def test_formato_yyyy_mm_dd(self):
        assert onboard._decade_of("2015-04-13") == "2010s"

    def test_formato_yyyy(self):
        assert onboard._decade_of("1995") == "1990s"

    def test_formato_yyyy_mm(self):
        assert onboard._decade_of("2023-07") == "2020s"

    def test_string_vazia_retorna_vazia(self):
        assert onboard._decade_of("") == ""

    def test_string_invalida_retorna_vazia(self):
        assert onboard._decade_of("abcd") == ""

    def test_decada_de_virada_de_seculo(self):
        assert onboard._decade_of("2000-01-01") == "2000s"
        assert onboard._decade_of("1999-12-31") == "1990s"


class TestPreservaMetadata:
    """v0.7.0: index tracks (em run()) preservam release_date e artist_id
    para downstream (_derive_suggestions usa década e gênero)."""

    def test_run_preserva_release_date_e_artist_id_no_index(
        self, tmp_path, monkeypatch,
    ):
        from maestra_ai.core.taste import TasteProfile
        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
        monkeypatch.setenv("MAESTRA_STATE_DIR", str(tmp_path / "state"))

        sp = _make_sp(top_long=0, top_medium=0, top_short=0,
                      saved_pages=[{"items": []}], recent=0)
        sp.current_user_top_tracks.side_effect = lambda limit, time_range: (
            {"items": [{
                "uri": "spotify:track:abc",
                "name": "Song A",
                "artists": [{"id": "art1", "name": "Artist A"}],
                "album": {"release_date": "2015-04-13"},
            }]} if time_range == "long_term" else {"items": []}
        )
        sp.artists.return_value = {"artists": []}

        captured = {}

        def spy(tracks_by_weight, *args, **kwargs):
            captured["tracks"] = tracks_by_weight
            # Retorna tupla (texts, rationale_entries, signals) esperada por run()
            return [], [], {"top_genres": [], "dominant_decades": [], "top_artists": []}

        monkeypatch.setattr(onboard, "_derive_suggestions", spy)

        taste = TasteProfile(tmp_path / "taste.json")
        onboard.run(
            sp, taste, playlist_name="Test",
            seed_count=0, playlist_selector=None, total_cap=5000,
        )
        tracks = captured.get("tracks", [])
        assert len(tracks) >= 1, "no tracks captured"
        found = next((t for t in tracks if t.get("uri") == "spotify:track:abc"), None)
        assert found is not None, "track não encontrada no sorted_tracks"
        assert found.get("release_date") == "2015-04-13", \
            "release_date precisa ser preservado no index"
        artists = found.get("artists", [])
        assert artists, "artists não preservado"
        assert artists[0].get("id") == "art1", \
            "artist_id precisa estar nos artists[]"


class TestDeriveSuggestionsIntel:
    """v0.7.0: _derive_suggestions usa gêneros + décadas + artistas + taste."""

    def _mk_tracks(self, n_tracks=10, artist="Sufjan Stevens", decade="2010"):
        return [
            {
                "uri": f"spotify:track:t{i}",
                "name": f"Song {i}",
                "artists": [{"id": f"a_{artist}", "name": artist}],
                "release_date": f"{decade}-01-01",
            }
            for i in range(n_tracks)
        ]

    def test_sugestao_usa_genero_dominante_quando_disponivel(self, tmp_path):
        from maestra_ai.core.taste import TasteProfile
        taste = TasteProfile(tmp_path / "taste.json")
        tracks = self._mk_tracks(n_tracks=20, artist="Sufjan Stevens")
        weights = {t["uri"]: 5.0 for t in tracks}
        adjusted = onboard._apply_taste_to_weights(weights, tracks, taste)
        sorted_tracks = [t for t in tracks if t["uri"] in adjusted]
        # Dict chaveado por artist_id (shape de _fetch_artists_genres
        # desde v0.8.0-alpha.4). _mk_tracks usa id = f"a_{artist}".
        genres = {"a_Sufjan Stevens": ["indie folk", "chamber folk"]}

        texts, rationale, signals = onboard._derive_suggestions(
            sorted_tracks, adjusted, genres, taste,
        )
        assert any("indie folk" in t.lower() for t in texts), \
            f"esperava indie folk em alguma sugestão, veio: {texts}"
        assert signals["top_genres"][0][0] == "indie folk"

    def test_fallback_quando_generos_vazios(self, tmp_path):
        """Se artists_genres está vazio, cai em fallback."""
        from maestra_ai.core.taste import TasteProfile
        taste = TasteProfile(tmp_path / "taste.json")
        tracks = self._mk_tracks(n_tracks=3, artist="Artist X")
        weights = {t["uri"]: 3.0 for t in tracks}
        texts, rationale, signals = onboard._derive_suggestions(
            tracks, weights, {}, taste,
        )
        assert len(texts) == 5
        hard_coded_tokens = ["piano minimalista", "indie folk melancólico",
                             "eletrônica downtempo"]
        assert any(any(tok in t for tok in hard_coded_tokens) for t in texts)

    def test_cap_por_artista_evita_monotema(self, tmp_path):
        from maestra_ai.core.taste import TasteProfile
        taste = TasteProfile(tmp_path / "taste.json")
        tracks = self._mk_tracks(n_tracks=50, artist="A1")
        for i, t in enumerate(tracks):
            t["uri"] = f"spotify:track:a1_{i}"
        for i in range(5):
            tracks.append({
                "uri": f"spotify:track:a2_{i}",
                "name": f"S2{i}",
                "artists": [{"id": "a2", "name": "A2"}],
                "release_date": "2018-01-01",
            })
        for i in range(5):
            tracks.append({
                "uri": f"spotify:track:a3_{i}",
                "name": f"S3{i}",
                "artists": [{"id": "a3", "name": "A3"}],
                "release_date": "2019-01-01",
            })
        weights = {t["uri"]: 5.0 for t in tracks}
        texts, rationale, signals = onboard._derive_suggestions(
            tracks, weights, {}, taste, cap_per_artist=10,
        )
        top = dict(signals["top_artists"])
        assert top["A1"] == 5.0 * 10  # cap aplicado
        assert "A2" in top
        assert "A3" in top

    def test_taste_rejeitado_nao_entra_em_signals(self, tmp_path):
        from maestra_ai.core.taste import TasteProfile
        taste = TasteProfile(tmp_path / "taste.json")
        tracks_a = self._mk_tracks(n_tracks=5, artist="KeepMe")
        tracks_b = self._mk_tracks(n_tracks=5, artist="BannedArtist")
        for i, t in enumerate(tracks_b):
            t["uri"] = f"spotify:track:b_{i}"
        taste.data.setdefault("rejected_artists", []).append("BannedArtist")
        taste.save()
        all_tracks = tracks_a + tracks_b
        weights = {t["uri"]: 5.0 for t in all_tracks}
        adjusted = onboard._apply_taste_to_weights(
            weights, all_tracks, taste,
        )
        sorted_tracks = [t for t in all_tracks if t["uri"] in adjusted]
        texts, rationale, signals = onboard._derive_suggestions(
            sorted_tracks, adjusted, {}, taste,
        )
        top = dict(signals["top_artists"])
        assert "BannedArtist" not in top
        assert "KeepMe" in top

    def test_decade_agregada_nos_signals(self, tmp_path):
        from maestra_ai.core.taste import TasteProfile
        taste = TasteProfile(tmp_path / "taste.json")
        tracks = []
        for i in range(10):
            tracks.append({
                "uri": f"spotify:track:t{i}",
                "name": f"T{i}",
                "artists": [{"id": "a", "name": "A"}],
                "release_date": "2015-03-01",
            })
        for i in range(5):
            tracks.append({
                "uri": f"spotify:track:old{i}",
                "name": f"O{i}",
                "artists": [{"id": "a", "name": "A"}],
                "release_date": "1985-07-01",
            })
        weights = {t["uri"]: 3.0 for t in tracks}
        texts, rationale, signals = onboard._derive_suggestions(
            tracks, weights, {}, taste,
        )
        decades = dict(signals["dominant_decades"])
        assert decades.get("2010s", 0) > decades.get("1980s", 0)

    def test_rationale_paralelo_as_texts(self, tmp_path):
        from maestra_ai.core.taste import TasteProfile
        taste = TasteProfile(tmp_path / "taste.json")
        tracks = self._mk_tracks(n_tracks=10, artist="Bon Iver")
        weights = {t["uri"]: 3.0 for t in tracks}
        genres = {"a_Bon Iver": ["indie folk"]}
        texts, rationale, signals = onboard._derive_suggestions(
            tracks, weights, genres, taste,
        )
        assert len(texts) == len(rationale)
        assert all("text" in r for r in rationale)
        assert all("contributing_tracks" in r for r in rationale)

    def test_derive_suggestions_usa_artist_id_para_lookup_generos(self, tmp_path):
        """Regressão v0.8.0-alpha.4: _derive_suggestions deve fazer lookup
        por artist_id (não name) em artists_genres, pois _fetch_artists_genres
        passou a chavear o dict por id do artista."""
        from maestra_ai.core.taste import TasteProfile
        taste = TasteProfile(tmp_path / "taste.json")
        tracks = [
            {
                "uri": "spotify:track:t1",
                "name": "Song 1",
                "artists": [{"id": "artist-abc", "name": "Artist ABC"}],
                "release_date": "2020-01-01",
            },
        ]
        weights = {"spotify:track:t1": 3.0}
        # Dict chaveado por ID — shape retornado por _fetch_artists_genres
        # desde v0.8.0-alpha.4.
        artists_genres = {"artist-abc": ["indie folk", "ambient"]}

        texts, rationale, signals = onboard._derive_suggestions(
            tracks, weights, artists_genres, taste,
        )

        genres_found = [g for g, _ in signals.get("top_genres", [])]
        assert "indie folk" in genres_found or "ambient" in genres_found, (
            f"Esperado gêneros enriquecidos, recebi signals={signals}"
        )


class TestApplyTasteToWeights:
    """_apply_taste_to_weights filtra rejeitados + adjusta pesos com feedback."""

    def _sample_tracks(self):
        return [
            {"uri": "spotify:track:t1", "name": "T1",
             "artists": [{"id": "a1", "name": "A1"}], "release_date": "2020"},
            {"uri": "spotify:track:t2", "name": "T2",
             "artists": [{"id": "a2", "name": "A2"}], "release_date": "2018"},
            {"uri": "spotify:track:t3", "name": "T3",
             "artists": [{"id": "a3", "name": "BannedArtist"}],
             "release_date": "2019"},
        ]

    def test_sem_taste_data_pesos_inalterados(self, tmp_path):
        from maestra_ai.core.taste import TasteProfile
        taste = TasteProfile(tmp_path / "taste.json")
        weights = {"spotify:track:t1": 5.0, "spotify:track:t2": 3.0}
        out = onboard._apply_taste_to_weights(
            weights, self._sample_tracks(), taste,
        )
        assert out["spotify:track:t1"] == 5.0
        assert out["spotify:track:t2"] == 3.0

    def test_is_rejected_remove_track(self, tmp_path):
        from maestra_ai.core.taste import TasteProfile
        taste = TasteProfile(tmp_path / "taste.json")
        taste.record_feedback("spotify:track:t1", "bad")
        weights = {"spotify:track:t1": 5.0, "spotify:track:t2": 3.0}
        out = onboard._apply_taste_to_weights(
            weights, self._sample_tracks(), taste,
        )
        assert "spotify:track:t1" not in out
        assert out["spotify:track:t2"] == 3.0

    def test_rejected_artist_remove_todas_tracks_do_artista(self, tmp_path):
        from maestra_ai.core.taste import TasteProfile
        taste = TasteProfile(tmp_path / "taste.json")
        taste.data.setdefault("rejected_artists", []).append("BannedArtist")
        taste.save()
        weights = {"spotify:track:t3": 5.0}
        out = onboard._apply_taste_to_weights(
            weights, self._sample_tracks(), taste,
        )
        assert "spotify:track:t3" not in out

    def test_good_feedback_amplifica_peso(self, tmp_path):
        from maestra_ai.core.taste import TasteProfile
        taste = TasteProfile(tmp_path / "taste.json")
        taste.record_feedback("spotify:track:t2", "good")
        weights = {"spotify:track:t1": 3.0, "spotify:track:t2": 3.0}
        out = onboard._apply_taste_to_weights(
            weights, self._sample_tracks(), taste,
        )
        assert out["spotify:track:t2"] == 5.0  # 3.0 + 2.0 good_bonus
        assert out["spotify:track:t1"] == 3.0

    def test_skip_count_penaliza_com_floor_em_zero(self, tmp_path):
        from maestra_ai.core.taste import TasteProfile
        taste = TasteProfile(tmp_path / "taste.json")
        taste.record_feedback("spotify:track:t1", "skip")
        taste.record_feedback("spotify:track:t1", "skip")
        weights = {"spotify:track:t1": 0.3}
        out = onboard._apply_taste_to_weights(
            weights, self._sample_tracks(), taste,
        )
        assert "spotify:track:t1" not in out or out["spotify:track:t1"] == 0.0


class TestPersistRationale:
    """v0.7.0: onboard.run() persiste rationale em state_dir/onboard_rationale.json
    e adiciona signals ao report."""

    def test_persist_cria_arquivo_com_schema_correto(
        self, tmp_path, monkeypatch,
    ):
        import json as _json

        from maestra_ai.core.taste import TasteProfile
        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
        monkeypatch.setenv("MAESTRA_STATE_DIR", str(tmp_path / "state"))

        sp = _make_sp(top_long=3, top_medium=0, top_short=0,
                      saved_pages=[{"items": []}], recent=0)
        sp.artists.return_value = {"artists": []}

        taste = TasteProfile(tmp_path / "taste.json")
        onboard.run(
            sp, taste, playlist_name="Test",
            seed_count=0, playlist_selector=None, total_cap=5000,
        )

        from maestra_ai.core.storage import state_dir
        rationale_path = state_dir() / "onboard_rationale.json"
        assert rationale_path.exists(), \
            "arquivo onboard_rationale.json não foi criado"
        data = _json.loads(rationale_path.read_text(encoding="utf-8"))
        assert "generated_at" in data
        assert "suggestions" in data
        assert isinstance(data["suggestions"], list)

    def test_report_contem_signals_e_rationale_path(
        self, tmp_path, monkeypatch,
    ):
        from maestra_ai.core.taste import TasteProfile
        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
        monkeypatch.setenv("MAESTRA_STATE_DIR", str(tmp_path / "state"))

        sp = _make_sp(top_long=5, top_medium=0, top_short=0,
                      saved_pages=[{"items": []}], recent=0)
        sp.artists.return_value = {"artists": []}

        taste = TasteProfile(tmp_path / "taste.json")
        report = onboard.run(
            sp, taste, playlist_name="Test",
            seed_count=0, playlist_selector=None, total_cap=5000,
        )
        assert "signals" in report
        assert "top_genres" in report["signals"]
        assert "dominant_decades" in report["signals"]
        assert "top_artists" in report["signals"]
        assert "rationale_path" in report

    def test_persist_sobrescreve_onboard_anterior(
        self, tmp_path, monkeypatch,
    ):
        import json as _json

        from maestra_ai.core.taste import TasteProfile
        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
        monkeypatch.setenv("MAESTRA_STATE_DIR", str(tmp_path / "state"))

        taste = TasteProfile(tmp_path / "taste.json")

        def _make_fresh_sp():
            sp = _make_sp(top_long=3, top_medium=0, top_short=0,
                          saved_pages=[{"items": []}], recent=0)
            sp.artists.return_value = {"artists": []}
            return sp

        onboard.run(_make_fresh_sp(), taste, playlist_name="T1", seed_count=0,
                    playlist_selector=None, total_cap=5000)

        from maestra_ai.core.storage import state_dir
        path = state_dir() / "onboard_rationale.json"
        first = _json.loads(path.read_text(encoding="utf-8"))

        import time
        time.sleep(1.01)  # garante mudança no timestamp (resolução segundos)
        onboard.run(_make_fresh_sp(), taste, playlist_name="T2", seed_count=0,
                    playlist_selector=None, total_cap=5000)
        second = _json.loads(path.read_text(encoding="utf-8"))
        assert first["generated_at"] != second["generated_at"]


class TestSkipKwargs:
    """v0.8.0: kwargs skip_* em onboard.run para fluxo C (update).

    Permitem pular etapas específicas do pipeline sem tocar no spotipy:
    - skip_library → pula _fetch_saved (current_user_saved_tracks)
    - skip_long_term → pula top_tracks long_term
    - skip_medium_term → pula top_tracks medium_term
    - skip_playlist_creation → pula criação/resolução de playlist
    """

    def test_skip_library_nao_chama_current_user_saved_tracks(
        self, tmp_path, monkeypatch,
    ):
        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
        sp = _make_sp(top_long=2, top_short=2, saved_pages=[{"items": []}], recent=1)

        from maestra_ai.core.taste import TasteProfile
        taste = TasteProfile(str(tmp_path / "taste.json"))

        report = onboard.run(
            sp, taste, playlist_name="X", seed_count=0, dry_run=True,
            skip_library=True,
        )

        sp.current_user_saved_tracks.assert_not_called()
        assert report["saved_tracks_fetched"] == 0

    def test_skip_long_term_nao_pede_long_term(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
        sp = _make_sp(top_long=5, top_medium=3, top_short=2,
                      saved_pages=[{"items": []}], recent=1)

        from maestra_ai.core.taste import TasteProfile
        taste = TasteProfile(str(tmp_path / "taste.json"))

        report = onboard.run(
            sp, taste, playlist_name="X", seed_count=0, dry_run=True,
            skip_long_term=True,
        )

        # Verifica que current_user_top_tracks NÃO foi chamado com long_term
        time_ranges_chamados = [
            c.kwargs.get("time_range") or (c.args[1] if len(c.args) > 1 else None)
            for c in sp.current_user_top_tracks.call_args_list
        ]
        assert "long_term" not in time_ranges_chamados
        assert report["top_long_count"] == 0

    def test_skip_medium_term_nao_pede_medium_term(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
        sp = _make_sp(top_long=3, top_medium=3, top_short=2,
                      saved_pages=[{"items": []}], recent=1)

        from maestra_ai.core.taste import TasteProfile
        taste = TasteProfile(str(tmp_path / "taste.json"))

        report = onboard.run(
            sp, taste, playlist_name="X", seed_count=0, dry_run=True,
            skip_medium_term=True,
        )

        time_ranges_chamados = [
            c.kwargs.get("time_range") or (c.args[1] if len(c.args) > 1 else None)
            for c in sp.current_user_top_tracks.call_args_list
        ]
        assert "medium_term" not in time_ranges_chamados
        assert report["top_medium_count"] == 0

    def test_skip_playlist_creation_nao_cria_playlist(self, tmp_path, monkeypatch):
        """skip_playlist_creation=True pula user_playlist_create e retorna
        playlist_id=None mesmo com dry_run=False."""
        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
        sp = _make_sp(top_long=2, top_short=2,
                      saved_pages=[{"items": []}], recent=1)

        from maestra_ai.core.taste import TasteProfile
        taste = TasteProfile(str(tmp_path / "taste.json"))

        report = onboard.run(
            sp, taste, playlist_name="X", seed_count=5, dry_run=False,
            skip_playlist_creation=True,
        )

        sp.user_playlist_create.assert_not_called()
        sp.playlist_add_items.assert_not_called()
        assert report["playlist_id"] is None
        # seed_count>0 sem playlist → não semeou nada
        assert report["seeded"] == 0

    def test_skip_combinado_recent_mood_so_chama_short_e_recent(
        self, tmp_path, monkeypatch,
    ):
        """Cenário do _flow_C_update(mode='recent_mood'):
        skip_library + skip_long_term + skip_medium_term +
        skip_playlist_creation. Só top_short + recent são fetchados.
        """
        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
        sp = _make_sp(top_long=5, top_medium=5, top_short=3,
                      saved_pages=[{"items": []}], recent=2)

        from maestra_ai.core.taste import TasteProfile
        taste = TasteProfile(str(tmp_path / "taste.json"))

        report = onboard.run(
            sp, taste, playlist_name="X", seed_count=0, dry_run=False,
            skip_library=True, skip_long_term=True, skip_medium_term=True,
            skip_playlist_creation=True,
        )

        sp.current_user_saved_tracks.assert_not_called()
        sp.user_playlist_create.assert_not_called()
        time_ranges = [
            c.kwargs.get("time_range") or (c.args[1] if len(c.args) > 1 else None)
            for c in sp.current_user_top_tracks.call_args_list
        ]
        assert "long_term" not in time_ranges
        assert "medium_term" not in time_ranges
        assert "short_term" in time_ranges
        assert report["top_long_count"] == 0
        assert report["top_medium_count"] == 0
        assert report["saved_tracks_fetched"] == 0
        assert report["playlist_id"] is None
        assert report["status"] == "ok"


class TestDeriveMoodFromTags:
    def test_vazio_retorna_none(self):
        from maestra_ai.core.onboard import _derive_mood_from_tags
        assert _derive_mood_from_tags([], seed="x") is None

    def test_sem_match_retorna_none(self):
        from maestra_ai.core.onboard import _derive_mood_from_tags
        assert _derive_mood_from_tags(["british", "70s", "seen live"], seed="x") is None

    def test_match_aggressive_gera_mood_de_treino(self):
        from maestra_ai.core.onboard import _derive_mood_from_tags
        result = _derive_mood_from_tags(["aggressive", "metal"], seed="x")
        assert result is not None
        assert any(w in result for w in ("treino", "energia"))

    def test_match_dark_gera_mood_noturno_ou_foco(self):
        from maestra_ai.core.onboard import _derive_mood_from_tags
        result = _derive_mood_from_tags(["dark ambient", "heavy"], seed="x")
        assert result is not None

    def test_deterministico_com_mesmo_seed(self):
        from maestra_ai.core.onboard import _derive_mood_from_tags
        tags = ["aggressive", "dark", "heavy"]
        assert _derive_mood_from_tags(tags, seed="abc") == _derive_mood_from_tags(tags, seed="abc")


class TestSelectMood:
    def test_genre_no_mapa_usa_mapa_curado(self):
        from maestra_ai.core.onboard import _select_mood
        result = _select_mood(
            "ambient", seed="ambient",
            artists_tags=None,
            genre_to_top_artist_id={},
        )
        # ambient está no _GENRE_MOOD_TEMPLATES
        assert any(w in result for w in ("trabalho", "escrita", "noturno"))

    def test_genre_fora_do_mapa_usa_tags(self):
        from maestra_ai.core.onboard import _select_mood
        result = _select_mood(
            "metal", seed="metal",
            artists_tags={"artist-1": ["aggressive", "heavy", "intense"]},
            genre_to_top_artist_id={"metal": "artist-1"},
        )
        # Deve vir do _MOOD_CONTEXT (aggressive/heavy/intense), não do fallback genérico.
        assert any(w in result for w in ("treino", "garagem", "direção", "energia", "foco"))

    def test_genre_fora_do_mapa_sem_tags_cai_em_fallback(self):
        from maestra_ai.core.onboard import _select_mood
        result = _select_mood(
            "unknown-genre", seed="x",
            artists_tags=None,
            genre_to_top_artist_id={},
        )
        # Cai no _FALLBACK_MOODS
        assert any(w in result for w in ("concentração", "relaxar", "caminhada", "pausa"))


