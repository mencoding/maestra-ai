"""Testes do TasteProfile — perfil de gosto e feedback."""
import json
import pytest
from maestra_ai.core.taste import TasteProfile


@pytest.fixture
def profile(tmp_path):
    """Cria TasteProfile com arquivo temporário."""
    path = tmp_path / "taste_profile.json"
    return TasteProfile(str(path))


@pytest.fixture
def profile_with_data(tmp_path):
    """TasteProfile pré-populado."""
    path = tmp_path / "taste_profile.json"
    data = {
        "version": 1,
        "tracks": {
            "spotify:track:good1": {
                "name": "Wolf Totem",
                "artist": "The HU",
                "added_in_context": "energia",
                "added_at": "2026-04-16T01:00:00",
                "feedback": "good",
                "skip_count": 0,
                "play_count": 5,
            },
            "spotify:track:bad1": {
                "name": "Bad Song",
                "artist": "Bad Artist",
                "added_in_context": "foco",
                "added_at": "2026-04-16T01:00:00",
                "feedback": "bad",
                "skip_count": 1,
                "play_count": 0,
            },
            "spotify:track:skipped1": {
                "name": "Skipped Song",
                "artist": "Meh Artist",
                "added_in_context": "foco",
                "added_at": "2026-04-16T01:00:00",
                "feedback": None,
                "skip_count": 3,
                "play_count": 0,
            },
            "spotify:track:neutral1": {
                "name": "Neutral Song",
                "artist": "Some Artist",
                "added_in_context": "foco",
                "added_at": "2026-04-16T01:00:00",
                "feedback": None,
                "skip_count": 1,
                "play_count": 2,
            },
        },
        "context_queries": {
            "energia": {
                "queries_used": ["power metal", "epic orchestral"],
                "success_rate": 0.8,
                "last_used": "2026-04-16",
            },
        },
        "rejected_artists": ["Bad Artist"],
        "preferred_artists": ["The HU"],
    }
    path.write_text(json.dumps(data))
    return TasteProfile(str(path))


class TestPersistence:
    def test_load_cria_perfil_vazio_se_nao_existe(self, profile):
        data = profile.data
        assert data["version"] == 2
        assert data["tracks"] == {}
        assert data["context_queries"] == {}

    def test_save_e_load_preserva_dados(self, profile):
        profile.record_feedback("spotify:track:x", "good")
        profile.save()
        reloaded = TasteProfile(profile.path)
        assert "spotify:track:x" in reloaded.data["tracks"]

    def test_save_preserva_feedback_concorrente_de_outra_instancia(self, tmp_path):
        path = tmp_path / "taste_profile.json"
        first = TasteProfile(str(path))
        second = TasteProfile(str(path))

        first.record_feedback("spotify:track:a", "good", context="foco")
        second.record_added(
            [{"uri": "spotify:track:b", "name": "B", "artist": "Artist B"}],
            context="foco",
            queries_used=["ambient study"],
        )

        reloaded = TasteProfile(str(path))
        assert "spotify:track:a" in reloaded.data["tracks"]
        assert "spotify:track:b" in reloaded.data["tracks"]
        assert reloaded.data["tracks"]["spotify:track:a"]["context_signals"][0]["signal"] == "good"

    def test_save_mescla_sinais_contextuais_concorrentes_na_mesma_faixa(self, tmp_path):
        path = tmp_path / "taste_profile.json"
        first = TasteProfile(str(path))
        second = TasteProfile(str(path))

        first.record_context_signal(
            "spotify:track:a",
            "positive",
            context="foco",
            source="listened_to_end",
            event_id="evt-1",
            weight=1,
        )
        second.record_context_signal(
            "spotify:track:a",
            "negative",
            context="foco",
            source="skip_candidate",
            event_id="evt-2",
            weight=-1,
        )

        reloaded = TasteProfile(str(path))
        signals = reloaded.data["tracks"]["spotify:track:a"]["context_signals"]
        assert {signal["event_id"] for signal in signals} == {"evt-1", "evt-2"}

    def test_load_ignora_json_corrompido(self, tmp_path):
        path = tmp_path / "taste.json"
        path.write_text("not valid json {{{")
        profile = TasteProfile(str(path))
        assert profile.data["version"] == 2
        assert profile.data["tracks"] == {}

    def test_restore_sobrescreve_sem_merge(self, tmp_path):
        path = tmp_path / "taste_profile.json"
        p = TasteProfile(str(path))
        p.record_feedback("spotify:track:novo", "good")
        p.save()

        snapshot = {
            "version": 2,
            "tracks": {
                "spotify:track:antigo": {
                    "name": "Antiga",
                    "artist": "X",
                    "feedback": "good",
                    "context_signals": [],
                }
            },
            "context_queries": {},
            "rejected_artists": [],
            "preferred_artists": [],
        }
        p.restore(snapshot)

        reloaded = TasteProfile(str(path))
        assert "spotify:track:novo" not in reloaded.data["tracks"]
        assert "spotify:track:antigo" in reloaded.data["tracks"]


class TestMigration:
    def test_migra_v1_para_v2_preservando_campos_legados(self, profile_with_data):
        assert profile_with_data.data["version"] == 2
        track = profile_with_data.data["tracks"]["spotify:track:good1"]
        assert track["feedback"] == "good"
        assert track["skip_count"] == 0
        assert track["play_count"] == 5
        assert track["context_signals"] == []

    def test_migra_perfil_sem_listas_de_artistas(self, tmp_path):
        path = tmp_path / "taste_profile.json"
        path.write_text(json.dumps({"version": 1, "tracks": {}, "context_queries": {}}))

        profile = TasteProfile(str(path))

        assert profile.data["version"] == 2
        assert profile.data["rejected_artists"] == []
        assert profile.data["preferred_artists"] == []


class TestRecordAdded:
    def test_registra_faixas_adicionadas(self, profile):
        tracks_info = [
            {"uri": "spotify:track:a", "name": "Track A", "artist": "Artist A"},
            {"uri": "spotify:track:b", "name": "Track B", "artist": "Artist B"},
        ]
        profile.record_added(tracks_info, context="foco", queries_used=["lo-fi instrumental"])

        assert "spotify:track:a" in profile.data["tracks"]
        assert profile.data["tracks"]["spotify:track:a"]["added_in_context"] == "foco"
        assert "foco" in profile.data["context_queries"]

    def test_nao_sobrescreve_faixa_existente(self, profile_with_data):
        tracks_info = [
            {"uri": "spotify:track:good1", "name": "Wolf Totem", "artist": "The HU"},
        ]
        profile_with_data.record_added(tracks_info, context="relaxar", queries_used=["chill"])
        assert profile_with_data.data["tracks"]["spotify:track:good1"]["added_in_context"] == "energia"


class TestFeedback:
    def test_record_feedback_good(self, profile_with_data):
        profile_with_data.record_feedback("spotify:track:neutral1", "good")
        assert profile_with_data.data["tracks"]["spotify:track:neutral1"]["feedback"] == "good"

    def test_record_feedback_bad(self, profile_with_data):
        profile_with_data.record_feedback("spotify:track:neutral1", "bad")
        assert profile_with_data.data["tracks"]["spotify:track:neutral1"]["feedback"] == "bad"
        # Feedback "bad" NÃO propaga para rejected_artists automaticamente
        # (listas de artistas serão gerenciadas pelo modelo contextual na v2)
        assert "Some Artist" not in profile_with_data.data["rejected_artists"]

    def test_record_feedback_skip_incrementa_contador(self, profile_with_data):
        profile_with_data.record_feedback("spotify:track:neutral1", "skip")
        assert profile_with_data.data["tracks"]["spotify:track:neutral1"]["skip_count"] == 2

    def test_record_feedback_uri_desconhecida_cria_entrada(self, profile):
        profile.record_feedback("spotify:track:new", "good")
        assert "spotify:track:new" in profile.data["tracks"]


class TestContextualFeedback:
    def test_record_feedback_contextual_nao_altera_feedback_global(self, profile_with_data):
        profile_with_data.record_feedback(
            "spotify:track:neutral1",
            "good",
            context="foco profundo",
        )

        track = profile_with_data.data["tracks"]["spotify:track:neutral1"]
        assert track["feedback"] is None
        assert track["context_signals"][0]["context"] == "foco profundo"
        assert track["context_signals"][0]["signal"] == "good"
        assert track["context_signals"][0]["source"] == "explicit"

    def test_record_feedback_global_explicitamente_altera_feedback_global(self, profile_with_data):
        profile_with_data.record_feedback(
            "spotify:track:neutral1",
            "bad",
            context="foco",
            global_feedback=True,
        )

        track = profile_with_data.data["tracks"]["spotify:track:neutral1"]
        assert track["feedback"] == "bad"
        assert track["context_signals"] == []

    def test_skip_contextual_nao_incrementa_skip_global(self, profile_with_data):
        profile_with_data.record_feedback(
            "spotify:track:neutral1",
            "skip",
            context="energia",
        )

        track = profile_with_data.data["tracks"]["spotify:track:neutral1"]
        assert track["skip_count"] == 1
        assert track["context_signals"][0]["signal"] == "skip"

    def test_get_context_signals_filtra_por_contexto(self, profile_with_data):
        profile_with_data.record_feedback("spotify:track:neutral1", "good", context="foco")
        profile_with_data.record_feedback("spotify:track:neutral1", "skip", context="energia")

        foco = profile_with_data.get_context_signals("spotify:track:neutral1", context="foco")

        assert len(foco) == 1
        assert foco[0]["signal"] == "good"

    def test_record_context_signal_deduplica_por_event_id(self, profile_with_data):
        first = profile_with_data.record_context_signal(
            "spotify:track:neutral1",
            "positive",
            context="foco",
            source="listened_to_end",
            event_id="evt-1",
        )
        second = profile_with_data.record_context_signal(
            "spotify:track:neutral1",
            "positive",
            context="foco",
            source="listened_to_end",
            event_id="evt-1",
        )

        signals = profile_with_data.get_context_signals("spotify:track:neutral1")
        assert first is True
        assert second is False
        assert len(signals) == 1
        assert signals[0]["event_id"] == "evt-1"

    def test_context_score_soma_pesos_do_contexto(self, profile_with_data):
        profile_with_data.record_context_signal(
            "spotify:track:neutral1",
            "positive",
            context="foco",
            source="listened_to_end",
            weight=1,
        )
        profile_with_data.record_context_signal(
            "spotify:track:neutral1",
            "negative",
            context="energia",
            source="skip_candidate",
            weight=-1,
        )

        assert profile_with_data.context_score("spotify:track:neutral1", "foco") == 1
        assert profile_with_data.context_score("spotify:track:neutral1", "energia") == -1
        assert profile_with_data.context_score("spotify:track:neutral1", "relaxar") == 0

    def test_context_score_fallback_para_signal_sem_weight(self, profile_with_data):
        profile_with_data.record_feedback("spotify:track:neutral1", "good", context="foco")
        profile_with_data.record_feedback("spotify:track:neutral1", "skip", context="foco")

        assert profile_with_data.context_score("spotify:track:neutral1", "foco") == 0


class TestFilter:
    def test_remove_faixas_rejeitadas(self, profile_with_data):
        uris = ["spotify:track:good1", "spotify:track:bad1", "spotify:track:new"]
        filtered = profile_with_data.filter(uris)
        assert "spotify:track:good1" in filtered
        assert "spotify:track:bad1" not in filtered
        assert "spotify:track:new" in filtered

    def test_remove_faixas_de_artista_rejeitado(self, profile_with_data):
        uris_with_info = [
            {"uri": "spotify:track:new_bad", "artist": "Bad Artist"},
            {"uri": "spotify:track:new_good", "artist": "Good Artist"},
        ]
        filtered = profile_with_data.filter_with_artist_info(uris_with_info)
        assert len(filtered) == 1
        assert filtered[0]["uri"] == "spotify:track:new_good"


class TestShouldRemove:
    def test_remove_faixa_com_feedback_bad(self, profile_with_data):
        assert profile_with_data.should_remove("spotify:track:bad1") is True

    def test_nao_remove_faixa_skipada(self, profile_with_data):
        # Skips não removem — podem ser por contexto, não rejeição
        assert profile_with_data.should_remove("spotify:track:skipped1") is False

    def test_nao_remove_faixa_com_feedback_good(self, profile_with_data):
        assert profile_with_data.should_remove("spotify:track:good1") is False

    def test_nao_remove_faixa_neutra_com_plays(self, profile_with_data):
        assert profile_with_data.should_remove("spotify:track:neutral1") is False

    def test_nao_remove_faixa_desconhecida(self, profile_with_data):
        assert profile_with_data.should_remove("spotify:track:unknown") is False


class TestContextQueries:
    def test_get_successful_queries(self, profile_with_data):
        queries = profile_with_data.get_successful_queries("energia")
        assert queries == ["power metal", "epic orchestral"]

    def test_retorna_vazio_pra_contexto_desconhecido(self, profile_with_data):
        queries = profile_with_data.get_successful_queries("inexistente")
        assert queries == []


class TestSuccessRate:
    def test_success_rate_atualiza_com_feedback(self, profile):
        tracks_info = [
            {"uri": "spotify:track:a", "name": "A", "artist": "X"},
            {"uri": "spotify:track:b", "name": "B", "artist": "Y"},
        ]
        profile.record_added(tracks_info, context="foco", queries_used=["lo-fi"])

        # Nenhum feedback ainda → 0.0
        assert profile.data["context_queries"]["foco"]["success_rate"] == 0.0

        # 1 de 2 com good → 0.5
        profile.record_feedback("spotify:track:a", "good")
        assert profile.data["context_queries"]["foco"]["success_rate"] == 0.5

        # 2 de 2 com good → 1.0
        profile.record_feedback("spotify:track:b", "good")
        assert profile.data["context_queries"]["foco"]["success_rate"] == 1.0
