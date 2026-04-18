"""Testes do HistoryAnalyzer."""
from unittest.mock import MagicMock

from maestra_ai.core.history import HistoryAnalyzer


def test_analyze_agrega_historico_e_sugestoes():
    controller = MagicMock()
    controller.recently_played.return_value = [
        {"track": "Wolf Totem", "artist": "The HU", "uri": "spotify:track:a"},
        {"track": "Yuve Yuve Yu", "artist": "The HU", "uri": "spotify:track:b"},
        {"track": "EMV Charon", "artist": "Guillaume David", "uri": "spotify:track:c"},
    ]
    controller.top_tracks.side_effect = [
        [{"track": "Track S", "artist": "The HU", "uri": "spotify:track:s"}],
        [{"track": "Track M", "artist": "Max Richter", "uri": "spotify:track:m"}],
        [{"track": "Track L", "artist": "Guillaume David", "uri": "spotify:track:l"}],
    ]
    controller.top_artists.side_effect = [
        [{"name": "The HU", "uri": "spotify:artist:a", "genres": ["mongolian metal"]}],
        [{"name": "Max Richter", "uri": "spotify:artist:b", "genres": ["classical", "soundtrack"]}],
        [{"name": "Guillaume David", "uri": "spotify:artist:c", "genres": ["soundtrack"]}],
    ]

    result = HistoryAnalyzer(controller).analyze(recent_limit=10, top_limit=5)

    assert result["recent"]["top_artists"][0]["artist"] == "The HU"
    assert "The HU" in result["suggestions"]["preferred_artists_candidates"]
    assert "soundtrack" in result["suggestions"]["genre_candidates"]
    assert "soundtrack" in result["suggestions"]["context_query_candidates"]["foco"]
    controller.recently_played.assert_called_once_with(limit=10)
    assert controller.top_tracks.call_count == 3
    assert controller.top_artists.call_count == 3


def test_outside_playlist_lista_recentes_fora_da_playlist_sem_duplicar():
    controller = MagicMock()
    controller.recently_played.return_value = [
        {
            "track": "Fora",
            "artist": "Artista A",
            "uri": "spotify:track:outside",
            "played_at": "2026-04-16T10:00:00Z",
        },
        {
            "track": "Dentro",
            "artist": "Artista B",
            "uri": "spotify:track:inside",
            "played_at": "2026-04-16T09:55:00Z",
        },
        {
            "track": "Fora",
            "artist": "Artista A",
            "uri": "spotify:track:outside",
            "played_at": "2026-04-16T09:50:00Z",
        },
    ]
    controller.playlist_tracks.return_value = [
        {"track": "Dentro", "artist": "Artista B", "uri": "spotify:track:inside"}
    ]

    result = HistoryAnalyzer(controller).outside_playlist("playlist123", recent_limit=20)

    assert result["recent_count"] == 3
    assert result["playlist_count"] == 1
    assert result["outside_count"] == 1
    assert result["outside_play_events"] == 2
    assert result["top_outside_artists"] == [{"artist": "Artista A", "count": 2}]
    assert result["top_outside_tracks"] == [
        {"track": "Fora", "artist": "Artista A", "count": 2}
    ]
    assert result["tracks"][0]["uri"] == "spotify:track:outside"
    assert result["tracks"][0]["plays"] == 2
    assert result["tracks"][0]["played_at_events"] == [
        "2026-04-16T10:00:00Z",
        "2026-04-16T09:50:00Z",
    ]
    assert result["candidates"][0]["uri"] == "spotify:track:outside"
    controller.recently_played.assert_called_once_with(limit=20)
    controller.playlist_tracks.assert_called_once_with("playlist123")


def test_outside_playlist_candidatos_priorizam_repeticao_e_recencia():
    controller = MagicMock()
    controller.recently_played.return_value = [
        {
            "track": "Recente",
            "artist": "Artista B",
            "uri": "spotify:track:recent",
            "played_at": "2026-04-16T10:10:00Z",
        },
        {
            "track": "Repetida",
            "artist": "Artista A",
            "uri": "spotify:track:repeat",
            "played_at": "2026-04-16T10:00:00Z",
        },
        {
            "track": "Repetida",
            "artist": "Artista A",
            "uri": "spotify:track:repeat",
            "played_at": "2026-04-16T09:50:00Z",
        },
    ]
    controller.playlist_tracks.return_value = []

    result = HistoryAnalyzer(controller).outside_playlist("playlist123", recent_limit=20)

    assert [track["uri"] for track in result["candidates"]] == [
        "spotify:track:repeat",
        "spotify:track:recent",
    ]


class TestHistoryImportOutside:
    """Testes do novo método import_outside extraído do Director."""

    def test_import_outside_dry_run_retorna_candidatos(self):
        """Sem confirm: retorna candidatos sem alterar playlist."""
        controller = MagicMock()
        controller.recently_played.return_value = [
            {"uri": "spotify:track:x", "track": "X", "artist": "ArtX", "played_at": "2026-04-17T10:00:00Z"},
            {"uri": "spotify:track:y", "track": "Y", "artist": "ArtY", "played_at": "2026-04-17T10:05:00Z"},
        ]
        controller.playlist_tracks.return_value = []

        analyzer = HistoryAnalyzer(controller)
        result = analyzer.import_outside(
            playlist_id="pl_123",
            context="foco",
            confirm=False,
            count=5,
            min_plays=1,
        )

        assert result["dry_run"] is True
        assert result["imported"] == 0
        assert len(result["candidates"]) >= 1
        controller.playlist_add.assert_not_called()

    def test_import_outside_confirm_adiciona_a_playlist(self, tmp_path, monkeypatch):
        """Com confirm=True: cria snapshot, adiciona à playlist e grava sinais."""
        from maestra_ai.core.taste import TasteProfile

        monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))

        controller = MagicMock()
        controller.recently_played.return_value = [
            {"uri": "spotify:track:z", "track": "Z", "artist": "ArtZ", "played_at": "t"},
        ]
        controller.playlist_tracks.return_value = []

        taste = TasteProfile(str(tmp_path / "taste.json"))
        analyzer = HistoryAnalyzer(controller)
        result = analyzer.import_outside(
            playlist_id="pl_abc",
            context="foco",
            confirm=True,
            count=1,
            min_plays=1,
            taste=taste,
        )

        assert result["dry_run"] is False
        assert result["imported"] >= 1
        controller.playlist_add.assert_called_once()
        assert result["snapshot_id"]

    def test_import_outside_respeita_signal_bad(self, tmp_path, monkeypatch):
        """Com signal='bad': registra sinal contextual negativo em taste."""
        monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))

        controller = MagicMock()
        controller.recently_played.return_value = [
            {"uri": "spotify:track:z", "track": "Z", "artist": "ArtZ", "played_at": "t"},
        ]
        controller.playlist_tracks.return_value = []

        taste = MagicMock()
        taste.context_score.return_value = 0
        taste.record_context_signal.return_value = True

        analyzer = HistoryAnalyzer(controller)
        result = analyzer.import_outside(
            playlist_id="pl_abc",
            context="foco",
            confirm=True,
            count=1,
            min_plays=1,
            taste=taste,
            signal="bad",
        )

        assert result["dry_run"] is False
        assert result["imported"] == 1
        taste.record_context_signal.assert_called_once()
        kwargs = taste.record_context_signal.call_args.kwargs
        args_pos = taste.record_context_signal.call_args.args
        # segundo argumento posicional é o signal
        assert args_pos[1] == "bad"
        # weight alinhado com _signal_weight('bad') == -1
        assert kwargs.get("weight") == -1

    def test_import_outside_rejeita_signal_invalido(self):
        """Signal fora de {good, bad, skip} levanta ValueError."""
        import pytest

        controller = MagicMock()
        analyzer = HistoryAnalyzer(controller)
        with pytest.raises(ValueError, match="signal"):
            analyzer.import_outside(
                playlist_id="pl_abc",
                context="foco",
                confirm=False,
                signal="invalido",
            )

    def test_import_outside_signal_default_good(self, tmp_path, monkeypatch):
        """Sem passar signal: usa 'good' (retrocompatível)."""
        monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))

        controller = MagicMock()
        controller.recently_played.return_value = [
            {"uri": "spotify:track:z", "track": "Z", "artist": "ArtZ", "played_at": "t"},
        ]
        controller.playlist_tracks.return_value = []

        taste = MagicMock()
        taste.context_score.return_value = 0

        analyzer = HistoryAnalyzer(controller)
        analyzer.import_outside(
            playlist_id="pl_abc",
            context="foco",
            confirm=True,
            count=1,
            min_plays=1,
            taste=taste,
        )

        args_pos = taste.record_context_signal.call_args.args
        assert args_pos[1] == "good"
