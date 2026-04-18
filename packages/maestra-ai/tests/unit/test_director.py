"""Testes do MusicDirector."""
import json
from unittest.mock import MagicMock

from maestra_ai.core.director import MusicDirector


def make_director(tmp_path):
    controller = MagicMock()
    curator = MagicMock()
    taste = MagicMock()
    context_state = MagicMock()
    history_analyzer = MagicMock()
    director = MusicDirector(
        controller,
        curator,
        taste,
        context_state,
        str(tmp_path / "director_decisions.jsonl"),
        "playlist123",
        history_analyzer=history_analyzer,
    )
    return director, controller, curator, taste, context_state, history_analyzer


def test_hold_quando_playback_indisponivel(tmp_path):
    director, controller, curator, taste, context_state, _history_analyzer = make_director(tmp_path)
    context_state.show.return_value = {"context": "foco"}
    controller.now.return_value = None

    result = director.run_once()

    assert result["action"] == "hold"
    assert result["reason"] == "playback_unavailable"
    controller.playlist_tracks.assert_not_called()
    curator.curate.assert_not_called()
    taste.record_added.assert_not_called()


def test_hold_quando_pausado_no_meio_da_faixa(tmp_path):
    director, controller, curator, taste, context_state, _history_analyzer = make_director(tmp_path)
    context_state.show.return_value = {"context": "foco"}
    controller.now.return_value = {
        "track": "Track A",
        "artist": "Artist A",
        "uri": "spotify:track:a",
        "is_playing": False,
        "progress_ms": 12000,
    }

    result = director.run_once()

    assert result["action"] == "hold"
    assert result["reason"] == "paused_intentionally"
    controller.playlist_tracks.assert_not_called()
    curator.curate.assert_not_called()


def test_hold_quando_buffer_de_contexto_suficiente(tmp_path):
    director, controller, curator, taste, context_state, _history_analyzer = make_director(tmp_path)
    context_state.show.return_value = {"context": "foco"}
    taste.data = {
        "tracks": {
            "spotify:track:b": {"added_in_context": "foco"},
            "spotify:track:c": {"added_in_context": "foco"},
        }
    }
    controller.now.return_value = {
        "track": "Track A",
        "artist": "Artist A",
        "uri": "spotify:track:a",
        "is_playing": True,
        "progress_ms": 1000,
    }
    controller.playlist_tracks.return_value = [
        {"track": "Track B", "artist": "Artist B", "uri": "spotify:track:b"},
        {"track": "Track C", "artist": "Artist C", "uri": "spotify:track:c"},
    ]

    result = director.run_once(target=2)

    assert result["action"] == "hold"
    assert result["reason"] == "context_buffer_sufficient"
    curator.curate.assert_not_called()
    controller.playlist_add.assert_not_called()


def test_adiciona_a_playlist_quando_buffer_de_contexto_esta_baixo(tmp_path):
    director, controller, curator, taste, context_state, _history_analyzer = make_director(tmp_path)
    context_state.show.return_value = {"context": "foco"}
    taste.data = {"tracks": {}}
    controller.now.return_value = {
        "track": "Track A",
        "artist": "Artist A",
        "uri": "spotify:track:a",
        "is_playing": True,
        "progress_ms": 1000,
    }
    controller.playlist_tracks.return_value = []
    curator.curate.return_value = (
        [
            {"track": "Track B", "artist": "Artist B", "uri": "spotify:track:b"},
            {"track": "Track C", "artist": "Artist C", "uri": "spotify:track:c"},
        ],
        ["ambient study"],
    )

    result = director.run_once(target=2, add_count=2)

    assert result["action"] == "playlist_add"
    assert result["added"] == 2
    controller.playlist_add.assert_called_once_with(
        "playlist123",
        ["spotify:track:b", "spotify:track:c"],
    )
    taste.record_added.assert_called_once()
    curator.curate.assert_called_once_with(
        "foco",
        count=2,
        exclude_uris={"spotify:track:a"},
        exclude_artists=[],
        max_per_artist=1,
    )


def test_dry_run_nao_altera_playlist_nem_gosto(tmp_path):
    director, controller, curator, taste, context_state, _history_analyzer = make_director(tmp_path)
    context_state.show.return_value = None
    taste.data = {"tracks": {}}
    controller.now.return_value = {
        "track": "Track A",
        "artist": "Artist A",
        "uri": "spotify:track:a",
        "is_playing": True,
        "progress_ms": 1000,
    }
    controller.playlist_tracks.return_value = []
    curator.curate.return_value = (
        [{"track": "Track B", "artist": "Artist B", "uri": "spotify:track:b"}],
        ["lo-fi instrumental"],
    )

    result = director.run_once(target=1, add_count=1, dry_run=True)

    assert result["action"] == "playlist_add"
    assert result["context"] == "foco"
    assert result["context_source"] == "default"
    assert result["dry_run"] is True
    controller.playlist_add.assert_not_called()
    taste.record_added.assert_not_called()


def test_director_bloqueia_artista_dominante_na_curadoria(tmp_path):
    director, controller, curator, taste, context_state, _history_analyzer = make_director(tmp_path)
    context_state.show.return_value = {"context": "foco"}
    taste.data = {"tracks": {}}
    controller.now.return_value = {
        "track": "Track A",
        "artist": "Artist Atual",
        "uri": "spotify:track:current",
        "is_playing": True,
        "progress_ms": 1000,
    }
    controller.playlist_tracks.return_value = [
        {"track": "Dom 1", "artist": "Dominante", "uri": "spotify:track:d1"},
        {"track": "Dom 2", "artist": "Dominante", "uri": "spotify:track:d2"},
        {"track": "Outra", "artist": "Outra", "uri": "spotify:track:o1"},
    ]
    curator.curate.return_value = (
        [{"track": "Nova", "artist": "Nova", "uri": "spotify:track:n"}],
        ["ambient study"],
    )

    result = director.run_once(target=10, add_count=1, max_artist_share=0.5)

    assert result["dominant_artists"] == ["Dominante"]
    curator.curate.assert_called_once_with(
        "foco",
        count=1,
        exclude_uris={
            "spotify:track:current",
            "spotify:track:d1",
            "spotify:track:d2",
            "spotify:track:o1",
        },
        exclude_artists=["Dominante"],
        max_per_artist=1,
    )


def test_importa_fora_da_playlist_em_modo_seguro(tmp_path):
    director, controller, curator, taste, context_state, history_analyzer = make_director(tmp_path)
    context_state.show.return_value = {"context": "foco"}
    taste.data = {"tracks": {}}
    taste.context_score.return_value = 0
    taste.record_context_signal.return_value = True
    controller.now.return_value = {
        "track": "Track A",
        "artist": "Artist A",
        "uri": "spotify:track:a",
        "is_playing": True,
        "progress_ms": 1000,
    }
    controller.playlist_tracks.return_value = []
    history_analyzer.import_outside.return_value = {
        "dry_run": False,
        "context": "foco",
        "candidates": [
            {
                "track": "Track Fora",
                "artist": "Artist Fora",
                "uri": "spotify:track:outside",
                "plays": 2,
            }
        ],
        "imported": 1,
        "snapshot_id": "snap-1",
        "uris_imported": ["spotify:track:outside"],
    }

    result = director.run_once(target=10, import_outside="safe")

    assert result["action"] == "outside_playlist_import"
    assert result["added"] == 1
    # playlist_add agora é feito dentro de HistoryAnalyzer.import_outside
    history_analyzer.import_outside.assert_called_once()
    taste.record_added.assert_called_once()
    curator.curate.assert_not_called()


def test_import_outside_dry_run_nao_altera_playlist_ou_gosto(tmp_path):
    director, controller, _curator, taste, context_state, history_analyzer = make_director(tmp_path)
    context_state.show.return_value = {"context": "foco"}
    taste.data = {"tracks": {}}
    taste.context_score.return_value = 0
    controller.now.return_value = {
        "track": "Track A",
        "artist": "Artist A",
        "uri": "spotify:track:a",
        "is_playing": True,
        "progress_ms": 1000,
    }
    controller.playlist_tracks.return_value = []
    history_analyzer.import_outside.return_value = {
        "dry_run": True,
        "context": "foco",
        "candidates": [
            {
                "track": "Track Fora",
                "artist": "Artist Fora",
                "uri": "spotify:track:outside",
                "plays": 2,
            }
        ],
        "total_candidates": 1,
        "imported": 0,
    }

    result = director.run_once(target=10, import_outside="safe", dry_run=True)

    assert result["action"] == "outside_playlist_import"
    assert result["dry_run"] is True
    controller.playlist_add.assert_not_called()
    taste.record_added.assert_not_called()
    taste.record_context_signal.assert_not_called()


def test_import_outside_seguro_ignora_sinal_contextual_negativo(tmp_path):
    director, controller, curator, taste, context_state, history_analyzer = make_director(tmp_path)
    context_state.show.return_value = {"context": "foco"}
    taste.data = {"tracks": {}}
    taste.context_score.return_value = -1
    controller.now.return_value = {
        "track": "Track A",
        "artist": "Artist A",
        "uri": "spotify:track:a",
        "is_playing": True,
        "progress_ms": 1000,
    }
    controller.playlist_tracks.return_value = []
    # HistoryAnalyzer.import_outside já filtra sinais contextuais negativos
    # internamente — simulamos resultado vazio para cair no fluxo do curator.
    history_analyzer.import_outside.return_value = {
        "dry_run": False,
        "context": "foco",
        "candidates": [],
        "imported": 0,
        "snapshot_id": "snap-x",
        "uris_imported": [],
    }
    curator.curate.return_value = (
        [{"track": "Track B", "artist": "Artist B", "uri": "spotify:track:b"}],
        ["ambient study"],
    )

    result = director.run_once(target=10, add_count=1, import_outside="safe")

    assert result["action"] == "playlist_add"
    controller.playlist_add.assert_called_once_with("playlist123", ["spotify:track:b"])


def test_registra_decisao_em_jsonl(tmp_path):
    director, controller, _curator, _taste, context_state, _history_analyzer = make_director(tmp_path)
    context_state.show.return_value = {"context": "foco"}
    controller.now.return_value = None

    result = director.run_once()

    lines = (tmp_path / "director_decisions.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    saved = json.loads(lines[0])
    assert saved["action"] == result["action"]
    assert saved["component"] == "maestra-director"
