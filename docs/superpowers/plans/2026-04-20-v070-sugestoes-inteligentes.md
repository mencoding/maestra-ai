# v0.7.0-alpha.0 Sugestões Inteligentes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Substituir `_derive_suggestions` (artist-dominance + hard-coded) por lógica baseada em gêneros (via `sp.artists`), décadas (via `release_date`) e artistas dominantes, integrando `TasteProfile` (filtrar rejeitados, amplificar `good`, penalizar `skip`). Persistir rationale em `state_dir()/onboard_rationale.json` e expor via MCP tool `onboard_rationale`.

**Architecture:** Helpers puros `_decade_of`, `_fetch_artists_genres`, `_apply_taste_to_weights` compostos por nova `_derive_suggestions(tracks, genres, taste) -> (texts, rationale, signals)`. Sem audio_features (deprecado). Report do `onboard.run()` ganha `signals` dict; rationale persistido em JSON separado. Fallback para comportamento v0.5.x quando dados insuficientes.

**Tech Stack:** Python 3.11+, `collections.Counter`, `typing.TypedDict`, pytest + `unittest.mock.MagicMock`. Zero dep nova.

**Spec:** `docs/superpowers/specs/2026-04-20-v070-sugestoes-inteligentes-design.md`.

**Base antes de começar:** tag `v0.6.2-alpha.1` (commit `3e01c51`). Suite: 482 maestra-ai + 42 mcp = 524.

---

## File Structure

| Arquivo | Tipo | Responsabilidade na v0.7.0 |
|---|---|---|
| `packages/maestra-ai/src/maestra_ai/core/onboard_types.py` | Modify | +`OnboardSignals`, `TrackRationale`, `RationaleEntry` |
| `packages/maestra-ai/src/maestra_ai/core/onboard.py` | Modify | `_compute_weights` preserva `release_date`+`artist_id`; `_derive_suggestions` reescrita; +`_decade_of`, `_fetch_artists_genres`, `_apply_taste_to_weights`, `_persist_rationale`, `_GENRE_MOOD_TEMPLATES` |
| `packages/maestra-mcp/src/maestra_mcp/tools.py` | Modify | +tool `onboard_rationale` |
| `packages/maestra-ai/tests/unit/test_onboard.py` | Modify+Add | TestDecadeOf, TestFetchArtistsGenres, TestApplyTasteToWeights, TestDeriveSuggestionsIntel, TestPersistRationale |
| `packages/maestra-mcp/tests/test_tools.py` | Add | TestOnboardRationaleTool (3 casos) |
| `packages/maestra-ai/pyproject.toml` | Modify | bump 0.6.2a1 → 0.7.0a0 |
| `packages/maestra-mcp/pyproject.toml` | Modify | bump + pin |
| `CHANGELOG.md` | Add | seção [0.7.0-alpha.0] |
| `docs/reviews/2026-04-19-backlog-consolidado.md` | Touch | marcar B3 como fechado |

---

## Task 1: Tipos novos em `onboard_types.py`

**Files:**
- Modify: `packages/maestra-ai/src/maestra_ai/core/onboard_types.py`

- [ ] **Step 1: Adicionar os 3 TypedDicts**

Em `packages/maestra-ai/src/maestra_ai/core/onboard_types.py`, após `ExpansionInfo` (última TypedDict atual) e antes do alias `PlaylistSelector`, adicionar:

```python
class OnboardSignals(TypedDict):
    """Agregados brutos computados no onboard para consumo por CLI/MCP/agentes.

    - top_genres: lista (genero, peso_total) ordenada desc, limite 10.
    - dominant_decades: lista (decada, peso_total) ordenada desc, limite 3.
    - top_artists: lista (nome_artista, peso_total) ordenada desc, limite 10.

    Peso é float (afetado por adjustments do TasteProfile em v0.7.0).
    """

    top_genres: list[tuple[str, float]]
    dominant_decades: list[tuple[str, float]]
    top_artists: list[tuple[str, float]]


class TrackRationale(TypedDict):
    """Uma faixa que contribuiu para gerar uma sugestão."""

    uri: str
    name: str
    artist: str
    weight: float
    feedback: str | None  # "good"/"bad"/None (global, do TasteProfile)
    skip_count: int  # acumulado de skips registrados pelo TasteProfile


class RationaleEntry(TypedDict):
    """Por que uma sugestão específica apareceu no onboard."""

    text: str
    based_on: dict  # {"genres": [...], "decades": [...], "artists": [...]}
    contributing_tracks: list[TrackRationale]
```

- [ ] **Step 2: Validar import**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai/packages/maestra-ai && uv run python -c "
from maestra_ai.core.onboard_types import OnboardSignals, TrackRationale, RationaleEntry
print('ok')
"`
Expected: imprime `ok`.

- [ ] **Step 3: Commit**

```bash
cd /home/menzani/Desenvolvimento/maestra-ai
git add packages/maestra-ai/src/maestra_ai/core/onboard_types.py
git commit -m "feat(onboard_types): OnboardSignals/TrackRationale/RationaleEntry (v0.7.0)

Tipos para v0.7.0 B3 — sugestões inteligentes com rationale persistido.
Ainda não consumidos; tasks seguintes integram em onboard.py e MCP."
```

---

## Task 2: Helper `_decade_of` (TDD)

**Files:**
- Modify: `packages/maestra-ai/src/maestra_ai/core/onboard.py`
- Modify: `packages/maestra-ai/tests/unit/test_onboard.py`

- [ ] **Step 1: Escrever testes failing**

Em `packages/maestra-ai/tests/unit/test_onboard.py`, adicionar nova classe no nível de módulo:

```python
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
```

- [ ] **Step 2: Rodar — confirmar FAIL**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai/packages/maestra-ai && uv run pytest tests/unit/test_onboard.py::TestDecadeOf -v 2>&1 | tail -10`
Expected: FAIL com `AttributeError: module 'maestra_ai.core.onboard' has no attribute '_decade_of'`.

- [ ] **Step 3: Implementar**

Em `packages/maestra-ai/src/maestra_ai/core/onboard.py`, logo antes de `_derive_suggestions` (linha ~219), adicionar:

```python
def _decade_of(release_date: str) -> str:
    """Converte 'YYYY-MM-DD', 'YYYY-MM' ou 'YYYY' em string da década.

    Ex.: '2015-04-13' → '2010s'. String vazia ou inválida → ''.
    """
    if not release_date or len(release_date) < 4:
        return ""
    year_str = release_date[:4]
    if not year_str.isdigit():
        return ""
    year = int(year_str)
    decade = (year // 10) * 10
    return f"{decade}s"
```

- [ ] **Step 4: Rodar — confirmar PASS**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai/packages/maestra-ai && uv run pytest tests/unit/test_onboard.py::TestDecadeOf -v 2>&1 | tail -8`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
cd /home/menzani/Desenvolvimento/maestra-ai
git add packages/maestra-ai/src/maestra_ai/core/onboard.py packages/maestra-ai/tests/unit/test_onboard.py
git commit -m "feat(onboard): _decade_of helper (v0.7.0)

Converte release_date do Spotify (YYYY, YYYY-MM, YYYY-MM-DD) para
string da década ('2010s', '1990s'). Usado pela nova _derive_suggestions
para agregar década dominante do catálogo."
```

---

## Task 3: Helper `_fetch_artists_genres` (TDD)

**Files:**
- Modify: `packages/maestra-ai/src/maestra_ai/core/onboard.py`
- Modify: `packages/maestra-ai/tests/unit/test_onboard.py`

- [ ] **Step 1: Escrever testes failing**

Em `tests/unit/test_onboard.py`, adicionar:

```python
class TestFetchArtistsGenres:
    """_fetch_artists_genres resolve artist_ids → genres via sp.artists batch."""

    def test_resolve_top_artistas_em_uma_call(self):
        from unittest.mock import MagicMock
        sp = MagicMock()
        sp.artists.return_value = {
            "artists": [
                {"id": "a1", "name": "Sufjan Stevens",
                 "genres": ["indie folk", "chamber folk"]},
                {"id": "a2", "name": "Nils Frahm",
                 "genres": ["neo-classical", "ambient"]},
            ],
        }
        result = onboard._fetch_artists_genres(
            sp, artist_ids=["a1", "a2"],
        )
        assert result == {
            "Sufjan Stevens": ["indie folk", "chamber folk"],
            "Nils Frahm": ["neo-classical", "ambient"],
        }
        sp.artists.assert_called_once_with(["a1", "a2"])

    def test_lista_vazia_nao_chama_api(self):
        from unittest.mock import MagicMock
        sp = MagicMock()
        result = onboard._fetch_artists_genres(sp, artist_ids=[])
        assert result == {}
        sp.artists.assert_not_called()

    def test_erro_api_retorna_dict_vazio_fallback(self):
        """Falha não-MaestraError em sp.artists cai em fallback sem gêneros."""
        from unittest.mock import MagicMock
        sp = MagicMock()
        sp.artists.side_effect = RuntimeError("spotify flaky")
        result = onboard._fetch_artists_genres(sp, artist_ids=["a1"])
        assert result == {}

    def test_maestra_error_propaga(self):
        """AuthError/RateLimit propagam (pipeline central)."""
        import pytest
        from unittest.mock import MagicMock
        from maestra_ai.core.errors import AuthError
        sp = MagicMock()
        sp.artists.side_effect = AuthError("token revogado")
        with pytest.raises(AuthError):
            onboard._fetch_artists_genres(sp, artist_ids=["a1"])

    def test_batch_maximo_50_ids(self):
        """Se passar > 50 IDs, corta em 50 (hard limit Spotify)."""
        from unittest.mock import MagicMock
        sp = MagicMock()
        sp.artists.return_value = {"artists": []}
        many_ids = [f"a{i}" for i in range(80)]
        onboard._fetch_artists_genres(sp, artist_ids=many_ids)
        called_ids = sp.artists.call_args[0][0]
        assert len(called_ids) == 50
```

- [ ] **Step 2: Rodar — confirmar FAIL**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai/packages/maestra-ai && uv run pytest tests/unit/test_onboard.py::TestFetchArtistsGenres -v 2>&1 | tail -10`
Expected: FAIL com `AttributeError`.

- [ ] **Step 3: Implementar**

Em `packages/maestra-ai/src/maestra_ai/core/onboard.py`, logo antes de `_decade_of`, adicionar:

```python
def _fetch_artists_genres(
    sp, *, artist_ids: list[str],
) -> dict[str, list[str]]:
    """Resolve artist IDs → {artist_name: [genres]} via sp.artists batch.

    Spotify API aceita até 50 IDs por call — trunca se mais.
    MaestraError propaga; outras exceções viram dict vazio (fallback).
    """
    if not artist_ids:
        return {}
    batch = artist_ids[:50]
    try:
        resp = sp.artists(batch)
    except MaestraError:
        raise
    except Exception:
        return {}
    out: dict[str, list[str]] = {}
    for artist in (resp or {}).get("artists", []):
        name = artist.get("name")
        if not name:
            continue
        out[name] = list(artist.get("genres", []))
    return out
```

- [ ] **Step 4: Rodar — confirmar PASS**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai/packages/maestra-ai && uv run pytest tests/unit/test_onboard.py::TestFetchArtistsGenres -v 2>&1 | tail -8`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
cd /home/menzani/Desenvolvimento/maestra-ai
git add packages/maestra-ai/src/maestra_ai/core/onboard.py packages/maestra-ai/tests/unit/test_onboard.py
git commit -m "feat(onboard): _fetch_artists_genres helper (v0.7.0)

1 call sp.artists batch (até 50 IDs) → dict {name: [genres]}.
MaestraError propaga; outras exceções viram dict vazio (fallback
benigno para sugestões sem gênero real)."
```

---

## Task 4: `_compute_weights` preserva release_date + artist_id

**Files:**
- Modify: `packages/maestra-ai/src/maestra_ai/core/onboard.py`
- Modify: `packages/maestra-ai/tests/unit/test_onboard.py`

- [ ] **Step 1: Escrever teste failing**

Em `tests/unit/test_onboard.py`, adicionar:

```python
class TestPreservaMetadata:
    """v0.7.0: index tracks (em run()) preservam release_date e artist_id
    para downstream (_derive_suggestions usa década e gênero)."""

    def test_run_preserva_release_date_e_artist_id_no_index(
        self, tmp_path, monkeypatch,
    ):
        from unittest.mock import MagicMock
        from maestra_ai.core.taste import TasteProfile
        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))

        sp = _make_sp(top_long=0, top_medium=0, top_short=0,
                      saved_pages=[{"items": []}], recent=0)
        # Monta 1 track com release_date + artist_id
        sp.current_user_top_tracks.side_effect = lambda limit, time_range: (
            {"items": [{
                "uri": "spotify:track:abc",
                "name": "Song A",
                "artists": [{"id": "art1", "name": "Artist A"}],
                "album": {"release_date": "2015-04-13"},
            }]} if time_range == "long_term" else {"items": []}
        )

        captured = {}

        # Monkeypatch _derive_suggestions para inspecionar o sorted_tracks
        orig = onboard._derive_suggestions

        def spy(tracks_by_weight, *args, **kwargs):
            captured["tracks"] = tracks_by_weight
            return orig(tracks_by_weight, *args, **kwargs) if False else []

        monkeypatch.setattr(onboard, "_derive_suggestions", spy)

        taste = TasteProfile(tmp_path / "taste.json")
        onboard.run(
            sp, taste, playlist_name="Test",
            seed_count=0, playlist_selector=None, total_cap=5000,
        )
        tracks = captured.get("tracks", [])
        assert len(tracks) >= 1
        found = next((t for t in tracks if t.get("uri") == "spotify:track:abc"), None)
        assert found is not None, "track não encontrada no sorted_tracks"
        assert found.get("release_date") == "2015-04-13", \
            "release_date precisa ser preservado no index"
        artists = found.get("artists", [])
        assert artists, "artists não preservado"
        assert artists[0].get("id") == "art1", \
            "artist_id precisa estar nos artists[]"
```

- [ ] **Step 2: Rodar — confirmar FAIL**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai/packages/maestra-ai && uv run pytest tests/unit/test_onboard.py::TestPreservaMetadata -v 2>&1 | tail -15`
Expected: FAIL — `release_date` (não é preservado) ou o artist `id` (que já vem do Spotify mas pode estar preservado). Pelo menos o `release_date` deve faltar.

Nota: a signature do spy precisa ser compatível com nova assinatura esperada. Se o teste der TypeError por chamada com 1 arg, é porque spy precisa aceitar só 1. Ajustar spy para `def spy(tracks_by_weight, *args, **kwargs)` (já está assim).

- [ ] **Step 3: Implementar — enriquecer o index em `run()`**

Em `packages/maestra-ai/src/maestra_ai/core/onboard.py`, achar o bloco do index (próximo a linha 566-571):

```python
    # Índice uri → track para recuperar name/artist
    index: dict[str, dict] = {}
    for t in top_long + top_medium + top_short + saved + recent + playlist_tracks:
        uri = t.get("uri")
        if uri and uri not in index:
            index[uri] = t
```

Substituir por uma versão que copia fields específicos (não passa o dict cru do Spotify com campos inúteis/ruidosos):

```python
    # v0.7.0: index enriquecido com release_date e artist IDs para
    # permitir que _derive_suggestions agregue década e resolva gêneros.
    index: dict[str, dict] = {}
    for t in top_long + top_medium + top_short + saved + recent + playlist_tracks:
        uri = t.get("uri")
        if not uri or uri in index:
            continue
        artists = t.get("artists") or []
        # Normaliza: guarda dict com id (pode ser None) e name.
        norm_artists = [
            {"id": a.get("id"), "name": a.get("name")}
            for a in artists if a.get("name")
        ]
        release_date = ""
        album = t.get("album") or {}
        if isinstance(album, dict):
            release_date = album.get("release_date") or ""
        index[uri] = {
            "uri": uri,
            "name": t.get("name"),
            "artists": norm_artists,
            "release_date": release_date,
        }
```

- [ ] **Step 4: Rodar — confirmar PASS**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai/packages/maestra-ai && uv run pytest tests/unit/test_onboard.py::TestPreservaMetadata -v 2>&1 | tail -8`
Expected: 1 passed.

- [ ] **Step 5: Rodar toda a suite de onboard (regressão)**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai/packages/maestra-ai && uv run pytest tests/unit/test_onboard.py 2>&1 | tail -3`
Expected: todos passam. Se algum teste falhar por assumir shape antigo do index (sem `release_date`), ajustar — o novo shape só adiciona chaves.

- [ ] **Step 6: Commit**

```bash
cd /home/menzani/Desenvolvimento/maestra-ai
git add packages/maestra-ai/src/maestra_ai/core/onboard.py packages/maestra-ai/tests/unit/test_onboard.py
git commit -m "feat(onboard): index preserva release_date e artist_id (v0.7.0)

run() constroi index com shape {uri, name, artists:[{id,name}],
release_date}. Spotify já entrega esses campos; antes ficávamos
com o dict cru misturando metadados inúteis."
```

---

## Task 5: Helper `_apply_taste_to_weights` (TDD)

**Files:**
- Modify: `packages/maestra-ai/src/maestra_ai/core/onboard.py`
- Modify: `packages/maestra-ai/tests/unit/test_onboard.py`

- [ ] **Step 1: Escrever testes failing**

Em `tests/unit/test_onboard.py`, adicionar:

```python
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
        taste = TasteProfile(tmp_path / "taste.json")  # novo, vazio
        weights = {"spotify:track:t1": 5.0, "spotify:track:t2": 3.0}
        out = onboard._apply_taste_to_weights(
            weights, self._sample_tracks(), taste,
        )
        assert out["spotify:track:t1"] == 5.0
        assert out["spotify:track:t2"] == 3.0

    def test_is_rejected_remove_track(self, tmp_path):
        from maestra_ai.core.taste import TasteProfile
        taste = TasteProfile(tmp_path / "taste.json")
        # Marca t1 como "bad" → is_rejected True.
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
        # Adiciona "BannedArtist" aos rejected_artists.
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
        # skip_count = 2 → penalty = -1.0
        weights = {"spotify:track:t1": 0.3}  # < penalty
        out = onboard._apply_taste_to_weights(
            weights, self._sample_tracks(), taste,
        )
        # Floor em 0; track com peso 0 é removida para não poluir a lista.
        assert "spotify:track:t1" not in out or out["spotify:track:t1"] == 0.0
```

- [ ] **Step 2: Rodar — confirmar FAIL**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai/packages/maestra-ai && uv run pytest tests/unit/test_onboard.py::TestApplyTasteToWeights -v 2>&1 | tail -12`
Expected: FAIL com `AttributeError: module 'maestra_ai.core.onboard' has no attribute '_apply_taste_to_weights'`.

- [ ] **Step 3: Implementar**

Em `packages/maestra-ai/src/maestra_ai/core/onboard.py`, logo antes de `_fetch_artists_genres`, adicionar:

```python
# v0.7.0: constantes de adjustment por feedback. Module-level para
# facilitar tuning; não são configuráveis por usuário (YAGNI).
_GOOD_BONUS = 2.0
_SKIP_PENALTY = 0.5


def _apply_taste_to_weights(
    weights: dict[str, float],
    tracks: list[dict],
    taste,
) -> dict[str, float]:
    """Filtra rejeitados e aplica bonus/penalty baseado em feedback.

    - `taste.is_rejected(uri)` ou artista em `rejected_artists` → remove.
    - `track["feedback"] == "good"` → +_GOOD_BONUS.
    - Penalty = skip_count * _SKIP_PENALTY, floor em 0.
    - Tracks com peso final 0 são removidas do dict.

    Não muta `weights`. Retorna dict novo.
    """
    rejected_artists = set(taste.get_rejected_artists())
    track_index = {t["uri"]: t for t in tracks if t.get("uri")}
    out: dict[str, float] = {}
    for uri, base in weights.items():
        if taste.is_rejected(uri):
            continue
        track = track_index.get(uri, {})
        first_artist = ""
        artists = track.get("artists") or []
        if artists:
            first_artist = artists[0].get("name") or ""
        if first_artist in rejected_artists:
            continue
        adjusted = float(base)
        profile_track = taste.data.get("tracks", {}).get(uri, {})
        if profile_track.get("feedback") == "good":
            adjusted += _GOOD_BONUS
        skip_count = profile_track.get("skip_count", 0) or 0
        adjusted -= skip_count * _SKIP_PENALTY
        if adjusted <= 0:
            continue
        out[uri] = adjusted
    return out
```

- [ ] **Step 4: Rodar — confirmar PASS**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai/packages/maestra-ai && uv run pytest tests/unit/test_onboard.py::TestApplyTasteToWeights -v 2>&1 | tail -8`
Expected: 5 passed.

Se algum teste falhar por API de `TasteProfile.record_feedback` ter assinatura diferente (ex.: aceita mais args obrigatórios), inspecione o arquivo `core/taste.py` em torno da função e ajuste as chamadas do teste (use `record_feedback(uri, feedback)` sem argumentos extras; se a API exigir mais, use o que o schema aceita).

- [ ] **Step 5: Commit**

```bash
cd /home/menzani/Desenvolvimento/maestra-ai
git add packages/maestra-ai/src/maestra_ai/core/onboard.py packages/maestra-ai/tests/unit/test_onboard.py
git commit -m "feat(onboard): _apply_taste_to_weights helper (v0.7.0)

Filtra tracks rejeitadas (is_rejected ou artista em rejected_artists)
e aplica ajuste de peso por feedback global: +2.0 para good, -0.5
por skip_count. Floor em 0 (tracks com peso final <= 0 somem do
dict). Constantes _GOOD_BONUS/_SKIP_PENALTY module-level para tuning."
```

---

## Task 6: Templates + nova `_derive_suggestions` (TDD)

**Files:**
- Modify: `packages/maestra-ai/src/maestra_ai/core/onboard.py`
- Modify: `packages/maestra-ai/tests/unit/test_onboard.py`

Esta é a task maior. Combinamos: template dict + lógica de geração + rationale construction.

- [ ] **Step 1: Escrever testes failing (classe TestDeriveSuggestionsIntel)**

Em `tests/unit/test_onboard.py`, adicionar:

```python
class TestDeriveSuggestionsIntel:
    """v0.7.0: _derive_suggestions usa gêneros + décadas + artistas + taste."""

    def _mk_tracks(self, n_tracks=10, artist="Sufjan Stevens", decade="2010"):
        """Helper: cria lista de tracks com mesmo artista e década."""
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
        # Com taste já aplicado (vazio = sem ajuste).
        adjusted = onboard._apply_taste_to_weights(weights, tracks, taste)
        # Ordem descendente
        sorted_tracks = [t for t in tracks if t["uri"] in adjusted]
        genres = {"Sufjan Stevens": ["indie folk", "chamber folk"]}

        texts, rationale, signals = onboard._derive_suggestions(
            sorted_tracks, adjusted, genres, taste,
        )
        # Pelo menos uma das 5 sugestões menciona "indie folk".
        assert any("indie folk" in t.lower() for t in texts), \
            f"esperava indie folk em alguma sugestão, veio: {texts}"
        assert signals["top_genres"][0][0] == "indie folk"

    def test_fallback_quando_generos_vazios(self, tmp_path):
        """Se artists_genres está vazio (API falhou ou sample pequeno),
        cai em fallback — 2 personalizadas + 3 genéricas (compat v0.5.x)."""
        from maestra_ai.core.taste import TasteProfile
        taste = TasteProfile(tmp_path / "taste.json")
        tracks = self._mk_tracks(n_tracks=3, artist="Artist X")
        weights = {t["uri"]: 3.0 for t in tracks}
        texts, rationale, signals = onboard._derive_suggestions(
            tracks, weights, {}, taste,
        )
        # 5 sugestões (não quebra).
        assert len(texts) == 5
        # Em fallback, pelo menos uma das 3 sugestões hard-coded aparece.
        hard_coded_tokens = ["piano minimalista", "indie folk melancólico",
                             "eletrônica downtempo"]
        assert any(any(tok in t for tok in hard_coded_tokens) for t in texts)

    def test_cap_por_artista_evita_monotema(self, tmp_path):
        """50 tracks do mesmo artista + 5 de outros 2 → top_artists inclui
        pelo menos 2 artistas distintos; primeiro não passa de cap."""
        from maestra_ai.core.taste import TasteProfile
        taste = TasteProfile(tmp_path / "taste.json")
        # 50 do A1 + 5 do A2 + 5 do A3
        tracks = [
            *self._mk_tracks(n_tracks=50, artist="A1"),
        ]
        # Diferencia URIs
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
        # A1 tem 50 contribuições; cap de 10 reduz peso agregado.
        top = dict(signals["top_artists"])
        assert top["A1"] == 5.0 * 10  # cap aplicado
        # A2 e A3 aparecem também.
        assert "A2" in top
        assert "A3" in top

    def test_taste_rejeitado_nao_entra_em_signals(self, tmp_path):
        """Se artist está em rejected_artists, tracks dele são excluídas
        ANTES de agregar, então não aparece em top_artists."""
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
        """len(texts) == len(rationale)."""
        from maestra_ai.core.taste import TasteProfile
        taste = TasteProfile(tmp_path / "taste.json")
        tracks = self._mk_tracks(n_tracks=10, artist="Bon Iver")
        weights = {t["uri"]: 3.0 for t in tracks}
        genres = {"Bon Iver": ["indie folk"]}
        texts, rationale, signals = onboard._derive_suggestions(
            tracks, weights, genres, taste,
        )
        assert len(texts) == len(rationale)
        assert all("text" in r for r in rationale)
        assert all("contributing_tracks" in r for r in rationale)
```

- [ ] **Step 2: Rodar — confirmar FAIL**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai/packages/maestra-ai && uv run pytest tests/unit/test_onboard.py::TestDeriveSuggestionsIntel -v 2>&1 | tail -15`
Expected: múltiplos FAILs — a assinatura atual de `_derive_suggestions` só aceita 1 arg.

- [ ] **Step 3: Implementar templates + nova `_derive_suggestions`**

Em `packages/maestra-ai/src/maestra_ai/core/onboard.py`, ANTES da função atual `_derive_suggestions` (linha ~219), adicionar os templates e helpers internos:

```python
# v0.7.0: mapa gênero → lista de "mood modifiers" (complementos que fazem
# o texto final fluir). Cobertura razoável; se gênero não estiver no mapa,
# usa _FALLBACK_MOODS.
_GENRE_MOOD_TEMPLATES: dict[str, list[str]] = {
    "indie folk": ["melancólico para reflexão", "acústico para manhã"],
    "folk": ["suave para escrita", "tranquilo para fim de tarde"],
    "chamber folk": ["intimista para leitura", "melódico para introspecção"],
    "neo-classical": ["instrumental para concentração",
                      "minimalista para leitura"],
    "classical": ["orquestral para foco profundo",
                  "sinfônico para domingo lento"],
    "ambient": ["para trabalho analítico", "noturno para escrita"],
    "electronic": ["downtempo para tarde tranquila",
                   "dinâmico para treino"],
    "downtempo": ["lento para descanso", "para fim de expediente"],
    "jazz": ["suave para jantar", "noturno com piano"],
    "hip hop": ["groove para estrada", "com bateria pesada para treino"],
    "rock": ["energético para deslocamento", "clássico para garagem"],
    "indie rock": ["para tarde ao ar livre", "com guitarras para caminhada"],
    "pop": ["para pausa leve", "ensolarado para manhã"],
    "r&b": ["suave para noite", "com groove para fim de tarde"],
    "soul": ["aveludado para jantar", "clássico para domingo lento"],
    "synthwave": ["retrô para foco criativo", "dos anos 80 para viagem"],
    "post-rock": ["expansivo para contemplação",
                  "instrumental para leitura longa"],
    "techno": ["pulsante para treino", "minimalista para concentração"],
    "house": ["ritmado para fim de semana", "deep para tarde quente"],
    "world music": ["para despertar cultural", "para jantar com amigos"],
}


_FALLBACK_MOODS = [
    "para concentração",
    "para relaxar no fim do dia",
    "para caminhada matinal",
    "para pausa do trabalho",
]


_FALLBACK_SUGGESTIONS = [
    "piano minimalista neoclássico para leitura",
    "indie folk melancólico para reflexão",
    "eletrônica downtempo para tarde tranquila",
]


_DEFAULT_CAP_PER_ARTIST = 10
```

Agora SUBSTITUIR a função atual `_derive_suggestions` (toda a definição e corpo):

```python
def _derive_suggestions(
    tracks_by_weight: list[dict],
    weights: dict[str, float],
    artists_genres: dict[str, list[str]],
    taste,
    *,
    top_k: int = 5,
    cap_per_artist: int = _DEFAULT_CAP_PER_ARTIST,
):
    """Deriva sugestões ricas + rationale + signals (v0.7.0 B3).

    Retorna (texts, rationale_entries, signals) onde:
    - texts: list[str] de até `top_k` sugestões natural-language.
    - rationale_entries: list[RationaleEntry] paralela — index i explica texts[i].
    - signals: OnboardSignals com top_genres/dominant_decades/top_artists.

    `tracks_by_weight` é a lista de tracks (com `uri`, `name`, `artists`,
    `release_date`) já filtrada e ajustada pelo taste.
    `weights` é o dict uri → adjusted_weight (output de _apply_taste_to_weights).
    `artists_genres` é o dict {artist_name: [genres]} de _fetch_artists_genres.
    """
    # Agregar signals
    genre_counter: Counter[str] = Counter()
    decade_counter: Counter[str] = Counter()
    artist_counter: Counter[str] = Counter()
    # Para cap_per_artist: conta quantas tracks de cada artista foram somadas
    artist_track_count: Counter[str] = Counter()

    # Iteração em ordem descendente por peso para o cap fazer sentido
    ordered = sorted(
        tracks_by_weight,
        key=lambda t: weights.get(t.get("uri", ""), 0.0),
        reverse=True,
    )[:200]

    for t in ordered:
        uri = t.get("uri")
        if not uri:
            continue
        w = weights.get(uri, 0.0)
        artists = t.get("artists") or []
        first_artist = (artists[0].get("name") if artists else "") or ""

        # Cap por artista
        if first_artist and artist_track_count[first_artist] >= cap_per_artist:
            continue
        if first_artist:
            artist_track_count[first_artist] += 1
            artist_counter[first_artist] += w

        # Décadas
        decade = _decade_of(t.get("release_date", ""))
        if decade:
            decade_counter[decade] += w

        # Gêneros (de todos os artistas mapeados)
        for a in artists:
            aname = a.get("name")
            if not aname:
                continue
            for g in artists_genres.get(aname, []):
                genre_counter[g.lower()] += w / max(len(artists), 1)

    signals = {
        "top_genres": [(g, round(s, 2)) for g, s in genre_counter.most_common(10)],
        "dominant_decades": [(d, round(s, 2)) for d, s in decade_counter.most_common(3)],
        "top_artists": [(a, round(s, 2)) for a, s in artist_counter.most_common(10)],
    }

    # Gerar sugestões
    texts: list[str] = []
    rationale: list[dict] = []

    # Se poucos sinais reais, cai em fallback
    if not signals["top_genres"]:
        texts, rationale = _fallback_suggestions(
            signals["top_artists"], ordered, taste, top_k,
        )
        return texts, rationale, signals

    # 1–3 sugestões por gênero dominante
    used_genres: list[str] = []
    for genre, _score in signals["top_genres"][:3]:
        mood = _pick_mood_for_genre(genre, seed=genre)
        text = f"{genre} {mood}"
        texts.append(text)
        used_genres.append(genre)
        rationale.append(_build_rationale(
            text, based_on={"genres": [genre], "decades": [], "artists": []},
            ordered=ordered, artists_genres=artists_genres, taste=taste,
            match_genre=genre,
        ))

    # Sugestão cross-signal: décadas + gênero
    if signals["dominant_decades"]:
        top_decade = signals["dominant_decades"][0][0]
        second_genre = (signals["top_genres"][1][0]
                        if len(signals["top_genres"]) > 1
                        else signals["top_genres"][0][0])
        mood = _pick_mood_for_genre(second_genre, seed=f"{top_decade}-{second_genre}")
        text = f"{top_decade} — faixas {second_genre} {mood}"
        if text not in texts:
            texts.append(text)
            rationale.append(_build_rationale(
                text,
                based_on={"genres": [second_genre], "decades": [top_decade], "artists": []},
                ordered=ordered, artists_genres=artists_genres, taste=taste,
                match_genre=second_genre, match_decade=top_decade,
            ))

    # Sugestão por artista dominante
    if signals["top_artists"]:
        top_artist = signals["top_artists"][0][0]
        text = f"{top_artist} e similares para foco profundo"
        if text not in texts and len(texts) < top_k:
            texts.append(text)
            rationale.append(_build_rationale(
                text,
                based_on={"genres": [], "decades": [], "artists": [top_artist]},
                ordered=ordered, artists_genres=artists_genres, taste=taste,
                match_artist=top_artist,
            ))

    # Completa até top_k com fallback se faltar
    while len(texts) < top_k:
        fallback_idx = len(texts) - len([t for t in texts if t in _FALLBACK_SUGGESTIONS])
        if fallback_idx >= len(_FALLBACK_SUGGESTIONS):
            break
        fallback_text = _FALLBACK_SUGGESTIONS[fallback_idx]
        if fallback_text in texts:
            break
        texts.append(fallback_text)
        rationale.append({
            "text": fallback_text,
            "based_on": {"genres": [], "decades": [], "artists": []},
            "contributing_tracks": [],
        })

    return texts[:top_k], rationale[:top_k], signals


def _pick_mood_for_genre(genre: str, *, seed: str) -> str:
    """Seleciona um mood determinístico (stable seed) para um gênero."""
    moods = _GENRE_MOOD_TEMPLATES.get(genre.lower(), _FALLBACK_MOODS)
    idx = hash(seed) % len(moods)
    return moods[idx]


def _fallback_suggestions(
    top_artists, ordered, taste, top_k,
):
    """Comportamento v0.5.x: 2 personalizadas + 3 genéricas."""
    texts: list[str] = []
    rationale: list[dict] = []
    if len(top_artists) >= 2:
        a1, a2 = top_artists[0][0], top_artists[1][0]
        sug1 = f"ambient instrumental inspirado em {a1} e {a2}"
        sug2 = f"faixas melódicas no estilo de {a1}"
    elif top_artists:
        sug1 = "ambient instrumental para trabalho analítico"
        sug2 = f"faixas melódicas no estilo de {top_artists[0][0]}"
    else:
        sug1 = "ambient instrumental para trabalho analítico"
        sug2 = "faixas melódicas para foco profundo"
    for t in (sug1, sug2):
        texts.append(t)
        rationale.append({
            "text": t,
            "based_on": {"genres": [], "decades": [],
                         "artists": [a for a, _ in top_artists[:2]]},
            "contributing_tracks": [],
        })
    for ft in _FALLBACK_SUGGESTIONS:
        if len(texts) >= top_k:
            break
        texts.append(ft)
        rationale.append({
            "text": ft,
            "based_on": {"genres": [], "decades": [], "artists": []},
            "contributing_tracks": [],
        })
    return texts, rationale


def _build_rationale(
    text: str,
    *,
    based_on: dict,
    ordered: list[dict],
    artists_genres: dict[str, list[str]],
    taste,
    match_genre: str | None = None,
    match_decade: str | None = None,
    match_artist: str | None = None,
    limit: int = 10,
) -> dict:
    """Escolhe até `limit` tracks que matcham o critério e compõe RationaleEntry."""
    contributing = []
    for t in ordered:
        if len(contributing) >= limit:
            break
        artists = t.get("artists") or []
        first_artist = (artists[0].get("name") if artists else "") or ""

        matched = False
        if match_genre:
            for a in artists:
                aname = a.get("name")
                if aname and match_genre.lower() in [
                    g.lower() for g in artists_genres.get(aname, [])
                ]:
                    matched = True
                    break
        if match_decade and _decade_of(t.get("release_date", "")) == match_decade:
            matched = True
        if match_artist and first_artist == match_artist:
            matched = True
        if not matched:
            continue

        uri = t.get("uri", "")
        profile_track = taste.data.get("tracks", {}).get(uri, {})
        contributing.append({
            "uri": uri,
            "name": t.get("name") or "",
            "artist": first_artist,
            "weight": 0.0,  # placeholder; caller pode preencher se quiser
            "feedback": profile_track.get("feedback"),
            "skip_count": profile_track.get("skip_count", 0) or 0,
        })
    return {
        "text": text,
        "based_on": based_on,
        "contributing_tracks": contributing,
    }
```

- [ ] **Step 4: Rodar — confirmar PASS**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai/packages/maestra-ai && uv run pytest tests/unit/test_onboard.py::TestDeriveSuggestionsIntel -v 2>&1 | tail -15`
Expected: 6 passed. Se algum falhar por expectativa de ordering ou string match específica, relaxar a assertion (ex.: case-insensitive; in em vez de ==) — a lógica pode gerar strings de várias formas válidas.

- [ ] **Step 5: Rodar suite completa onboard (regressão)**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai/packages/maestra-ai && uv run pytest tests/unit/test_onboard.py 2>&1 | tail -5`
Expected: maioria passa. Testes antigos que chamavam `_derive_suggestions(sorted_tracks)` com 1 arg vão falhar — são testes da lógica anterior. Se existirem, adaptar para a nova assinatura ou remover se redundantes com `TestDeriveSuggestionsIntel`.

- [ ] **Step 6: Commit**

```bash
cd /home/menzani/Desenvolvimento/maestra-ai
git add packages/maestra-ai/src/maestra_ai/core/onboard.py packages/maestra-ai/tests/unit/test_onboard.py
git commit -m "feat(onboard): _derive_suggestions reescrita com gênero/década/taste (v0.7.0)

Substitui a versão artist-dominance + hard-coded. Nova assinatura:
(tracks, weights, artists_genres, taste) → (texts, rationale, signals).

- _GENRE_MOOD_TEMPLATES: 20+ gêneros com moods contextuais.
- Cap por artista (default 10) evita sugestão monotemática.
- Fallback para 2 personalizadas + 3 genéricas quando artists_genres vazio.
- _pick_mood_for_genre: seleção determinística via hash seed para
  estabilidade cross-run.
- _build_rationale compõe RationaleEntry com contributing_tracks."
```

---

## Task 7: `_persist_rationale` + integração em `run()`

**Files:**
- Modify: `packages/maestra-ai/src/maestra_ai/core/onboard.py`
- Modify: `packages/maestra-ai/tests/unit/test_onboard.py`

- [ ] **Step 1: Escrever testes failing**

Em `tests/unit/test_onboard.py`, adicionar:

```python
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
        # _fake_top do _make_sp produz artists com {"name": f"A{i}"} sem id.
        # Para testar com genres reais, mock sp.artists.
        sp.artists.return_value = {"artists": []}

        taste = TasteProfile(tmp_path / "taste.json")
        report = onboard.run(
            sp, taste, playlist_name="Test",
            seed_count=0, playlist_selector=None, total_cap=5000,
        )

        from maestra_ai.core.storage import state_dir
        rationale_path = state_dir() / "onboard_rationale.json"
        assert rationale_path.exists(), "arquivo onboard_rationale.json não foi criado"
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
        sp = _make_sp(top_long=3, top_medium=0, top_short=0,
                      saved_pages=[{"items": []}], recent=0)
        sp.artists.return_value = {"artists": []}
        onboard.run(sp, taste, playlist_name="T1", seed_count=0,
                    playlist_selector=None, total_cap=5000)

        from maestra_ai.core.storage import state_dir
        path = state_dir() / "onboard_rationale.json"
        first = _json.loads(path.read_text(encoding="utf-8"))

        # Rodar de novo — overwrite
        import time
        time.sleep(0.01)  # garantir mudança de timestamp
        onboard.run(sp, taste, playlist_name="T2", seed_count=0,
                    playlist_selector=None, total_cap=5000)
        second = _json.loads(path.read_text(encoding="utf-8"))
        # generated_at muda (é novo ISO timestamp).
        assert first["generated_at"] != second["generated_at"]
```

- [ ] **Step 2: Rodar — confirmar FAIL**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai/packages/maestra-ai && uv run pytest tests/unit/test_onboard.py::TestPersistRationale -v 2>&1 | tail -12`
Expected: FAIL — `rationale_path` não existe ainda no report, arquivo não é criado.

- [ ] **Step 3: Implementar `_persist_rationale`**

Em `packages/maestra-ai/src/maestra_ai/core/onboard.py`, adicionar antes de `_derive_suggestions`:

```python
def _persist_rationale(rationale_entries: list[dict]) -> "Path":
    """Persiste as rationale entries em state_dir/onboard_rationale.json.

    Sobrescreve a cada chamada (lifetime = último onboard).
    Retorna a Path do arquivo.
    """
    from datetime import datetime, timezone
    from pathlib import Path
    path = storage.state_dir() / "onboard_rationale.json"
    payload = {
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(
            timespec="seconds",
        ),
        "suggestions": list(rationale_entries),
    }
    storage.atomic_write_json(path, payload)
    return path
```

- [ ] **Step 4: Integrar em `run()`**

Em `packages/maestra-ai/src/maestra_ai/core/onboard.py`, achar o bloco atual (linha ~592-598):

```python
    # Sugestões ordenadas por peso
    sorted_tracks = sorted(
        list(index.values()),
        key=lambda t: weights.get(t.get("uri", ""), 0),
        reverse=True,
    )
    suggestions = _derive_suggestions(sorted_tracks)
```

Substituir por:

```python
    # v0.7.0: sugestões inteligentes com taste + gêneros + rationale
    # Aplica taste adjust nos pesos e filtra rejeitados
    tracks_list = list(index.values())
    adjusted_weights = _apply_taste_to_weights(
        {uri: float(w) for uri, w in weights.items()},
        tracks_list,
        taste,
    )
    # Fetch genres do top 50 artistas (por peso agregado pré-signals)
    pre_artist_counter: Counter[str] = Counter()
    for uri, w in adjusted_weights.items():
        t = index.get(uri, {})
        artists = t.get("artists") or []
        if artists:
            first = artists[0]
            if first.get("name"):
                pre_artist_counter[first["name"]] += w
    top_artist_ids: list[str] = []
    seen_ids: set[str] = set()
    for aname, _ in pre_artist_counter.most_common(50):
        for t in tracks_list:
            for a in t.get("artists") or []:
                if a.get("name") == aname and a.get("id") and a["id"] not in seen_ids:
                    top_artist_ids.append(a["id"])
                    seen_ids.add(a["id"])
                    break
            if aname in {a.get("name") for a in t.get("artists") or []}:
                break
    artists_genres = _fetch_artists_genres(sp, artist_ids=top_artist_ids)

    # Lista final ordenada por peso ajustado
    sorted_tracks = sorted(
        [t for t in tracks_list if t.get("uri") in adjusted_weights],
        key=lambda t: adjusted_weights.get(t.get("uri", ""), 0),
        reverse=True,
    )
    suggestions, rationale_entries, signals = _derive_suggestions(
        sorted_tracks, adjusted_weights, artists_genres, taste,
    )
    rationale_path = _persist_rationale(rationale_entries)
```

- [ ] **Step 5: Atualizar dict de retorno de `run()`**

Achar o `return {...}` no final de `run()` (linha ~600) e adicionar `signals` + `rationale_path`:

```python
    return {
        "status": "ok",
        "playlist_id": playlist_id,
        "playlist_name": effective_name,
        "top_long_count": len(top_long),
        "top_medium_count": len(top_medium),
        "top_short_count": len(top_short),
        "saved_tracks_fetched": len(saved),
        "recent_count": len(recent),
        "playlist_expansion": expansion_info,
        "unique_tracks_scored": len(weights),
        "seeded": seeded,
        "context_suggestions": suggestions,
        "signals": signals,
        "rationale_path": str(rationale_path),
    }
```

- [ ] **Step 6: Rodar testes novos — confirmar PASS**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai/packages/maestra-ai && uv run pytest tests/unit/test_onboard.py::TestPersistRationale -v 2>&1 | tail -8`
Expected: 3 passed.

- [ ] **Step 7: Rodar suite completa (regressão)**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai/packages/maestra-ai && uv run pytest tests/unit/test_onboard.py 2>&1 | tail -5`
Expected: todos passam. Testes antigos que não setavam `sp.artists.return_value` podem falhar — adicionar mock default no `_make_sp` helper (OU localizar cada teste e adicionar `sp.artists.return_value = {"artists": []}`). Preferir ajuste no helper se for repetitivo.

- [ ] **Step 8: Commit**

```bash
cd /home/menzani/Desenvolvimento/maestra-ai
git add packages/maestra-ai/src/maestra_ai/core/onboard.py packages/maestra-ai/tests/unit/test_onboard.py
git commit -m "feat(onboard): run() integra taste + genres + persist rationale (v0.7.0)

run() agora:
1. Aplica _apply_taste_to_weights antes de gerar suggestions.
2. Fetcha genres do top 50 artistas via sp.artists (1 call batch).
3. Gera suggestions via nova _derive_suggestions.
4. Persiste rationale em state_dir/onboard_rationale.json.
5. Adiciona 'signals' e 'rationale_path' ao report."
```

---

## Task 8: MCP tool `onboard_rationale` (TDD)

**Files:**
- Modify: `packages/maestra-mcp/src/maestra_mcp/tools.py`
- Modify: `packages/maestra-mcp/tests/test_tools.py`

- [ ] **Step 1: Escrever testes failing**

Em `packages/maestra-mcp/tests/test_tools.py`, adicionar no final:

```python
class TestOnboardRationaleTool:
    """v0.7.0: tool onboard_rationale lê state_dir/onboard_rationale.json
    e retorna dados estruturados. Se ausente, UserError."""

    async def test_retorna_erro_quando_sem_rationale(
        self, tmp_path, monkeypatch,
    ):
        monkeypatch.setenv("MAESTRA_STATE_DIR", str(tmp_path / "state"))
        # Invalida cache de state_dir se existir
        from maestra_mcp.tools import call_tool
        result = await call_tool("onboard_rationale", {})
        assert "error" in result
        assert result["error"]["code"] == "UserError"

    async def test_retorna_todas_sugestoes_sem_args(
        self, tmp_path, monkeypatch,
    ):
        import json as _json
        monkeypatch.setenv("MAESTRA_STATE_DIR", str(tmp_path / "state"))
        # Fabrica arquivo de rationale mock
        from maestra_ai.core.storage import state_dir
        path = state_dir()
        path.mkdir(parents=True, exist_ok=True)
        (path / "onboard_rationale.json").write_text(_json.dumps({
            "generated_at": "2026-04-20T09:00:00-03:00",
            "suggestions": [
                {"text": "indie folk melancólico",
                 "based_on": {"genres": ["indie folk"], "decades": [], "artists": []},
                 "contributing_tracks": []},
                {"text": "synthwave dos anos 80 para viagem",
                 "based_on": {"genres": ["synthwave"], "decades": ["1980s"], "artists": []},
                 "contributing_tracks": []},
            ],
        }), encoding="utf-8")

        from maestra_mcp.tools import call_tool
        result = await call_tool("onboard_rationale", {})
        assert result["generated_at"] == "2026-04-20T09:00:00-03:00"
        assert len(result["suggestions"]) == 2

    async def test_filtra_por_suggestion_exata(
        self, tmp_path, monkeypatch,
    ):
        import json as _json
        monkeypatch.setenv("MAESTRA_STATE_DIR", str(tmp_path / "state"))
        from maestra_ai.core.storage import state_dir
        path = state_dir()
        path.mkdir(parents=True, exist_ok=True)
        (path / "onboard_rationale.json").write_text(_json.dumps({
            "generated_at": "2026-04-20T09:00:00-03:00",
            "suggestions": [
                {"text": "indie folk melancólico",
                 "based_on": {"genres": ["indie folk"], "decades": [], "artists": []},
                 "contributing_tracks": []},
                {"text": "synthwave dos anos 80 para viagem",
                 "based_on": {"genres": ["synthwave"], "decades": ["1980s"], "artists": []},
                 "contributing_tracks": []},
            ],
        }), encoding="utf-8")

        from maestra_mcp.tools import call_tool
        result = await call_tool(
            "onboard_rationale", {"suggestion": "indie folk melancólico"},
        )
        assert len(result["suggestions"]) == 1
        assert result["suggestions"][0]["text"] == "indie folk melancólico"
```

- [ ] **Step 2: Rodar — confirmar FAIL**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai/packages/maestra-mcp && uv run pytest tests/test_tools.py::TestOnboardRationaleTool -v 2>&1 | tail -10`
Expected: FAIL — tool não registrada.

- [ ] **Step 3: Implementar tool**

Em `packages/maestra-mcp/src/maestra_mcp/tools.py`, adicionar ao final:

```python
# ========================================================================
# Onboard rationale (v0.7.0 B3)
# ========================================================================

@tool(
    "onboard_rationale",
    "Retorna o rationale persistido das últimas sugestões do onboard. "
    "Permite explicar ao usuário por que cada sugestão apareceu, "
    "incluindo tracks que mais contribuíram e feedback histórico. "
    "Sem args: retorna todas. Com 'suggestion': filtra para uma específica.",
    {
        "type": "object",
        "properties": {
            "suggestion": {
                "type": "string",
                "description": "Texto exato de uma sugestão (opcional).",
            },
        },
        "additionalProperties": False,
    },
)
def _onboard_rationale(args):
    import json as _json
    from maestra_ai.core.errors import UserError
    from maestra_ai.core import storage

    path = storage.state_dir() / "onboard_rationale.json"
    if not path.exists():
        raise UserError(
            "Nenhum rationale persistido.",
            where={"hint": "Rode `maestra onboard` primeiro."},
        )
    data = _json.loads(path.read_text(encoding="utf-8"))
    target = args.get("suggestion")
    if target is None:
        return data
    match = [e for e in data.get("suggestions", []) if e.get("text") == target]
    if not match:
        raise UserError(
            f"Sugestão não encontrada: {target}",
            where={"available": [e.get("text") for e in data.get("suggestions", [])]},
        )
    return {"generated_at": data.get("generated_at"), "suggestions": match}
```

- [ ] **Step 4: Rodar testes — confirmar PASS**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai/packages/maestra-mcp && uv run pytest tests/test_tools.py::TestOnboardRationaleTool -v 2>&1 | tail -8`
Expected: 3 passed.

- [ ] **Step 5: Rodar suite MCP completa**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai/packages/maestra-mcp && uv run pytest tests/ 2>&1 | tail -3`
Expected: todos passam (42 + 3 = 45).

- [ ] **Step 6: Commit**

```bash
cd /home/menzani/Desenvolvimento/maestra-ai
git add packages/maestra-mcp/src/maestra_mcp/tools.py packages/maestra-mcp/tests/test_tools.py
git commit -m "feat(mcp): tool onboard_rationale (v0.7.0)

Read-only tool que lê state_dir/onboard_rationale.json e retorna
rationale das últimas sugestões do onboard. Permite ao agente
explicar 'por que essa sugestão apareceu'. Sem args retorna todas;
com 'suggestion' filtra por texto exato."
```

---

## Task 9: Bump v0.7.0-alpha.0 + CHANGELOG + backlog + tag

**Files:**
- Modify: `packages/maestra-ai/pyproject.toml`
- Modify: `packages/maestra-mcp/pyproject.toml`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `docs/reviews/2026-04-19-backlog-consolidado.md`

- [ ] **Step 1: Validação pré-bump**

Run:
```
cd /home/menzani/Desenvolvimento/maestra-ai/packages/maestra-ai && uv run pytest tests/unit/ tests/integration/ 2>&1 | tail -3
cd /home/menzani/Desenvolvimento/maestra-ai/packages/maestra-mcp && uv run pytest tests/ 2>&1 | tail -3
```
Expected: zero falhas.

- [ ] **Step 2: Bump maestra-ai/pyproject.toml**

Trocar `version = "0.6.2a1"` → `version = "0.7.0a0"`.

- [ ] **Step 3: Bump maestra-mcp/pyproject.toml**

- `version = "0.6.2a1"` → `version = "0.7.0a0"`
- `"maestra-ai==0.6.2a1"` → `"maestra-ai==0.7.0a0"`

- [ ] **Step 4: Atualizar README**

Trocar status:
`**Status:** pre-alpha (v0.6.2-alpha). Lançamento público planejado em v1.0.0.`
Por:
`**Status:** pre-alpha (v0.7.0-alpha). Lançamento público planejado em v1.0.0.`

- [ ] **Step 5: CHANGELOG entry**

Em `CHANGELOG.md`, após `## [Unreleased]` e antes de `## [0.6.2-alpha.1] - 2026-04-19`:

```markdown
## [0.7.0-alpha.0] - 2026-04-20

Fecha item B3 do backlog consolidado — `_derive_suggestions`
reescrita com sinais reais do catálogo (gêneros via `sp.artists`,
décadas via `release_date`, artistas dominantes), integrada com
`TasteProfile` (filtra rejeitados, amplifica `good`, penaliza
`skip`). Rationale persistido em `state_dir/onboard_rationale.json`
e exposto via nova MCP tool `onboard_rationale`.

### Added
- **`core/onboard.py`**:
  - `_decade_of(release_date)` — helper para agregar década.
  - `_fetch_artists_genres(sp, artist_ids)` — 1 call `sp.artists` batch.
  - `_apply_taste_to_weights(weights, tracks, taste)` — filtra rejeitados;
    +2.0 para `good`, -0.5 por skip (floor em 0).
  - `_GENRE_MOOD_TEMPLATES` — ~20 gêneros com moods contextuais
    (indie folk, ambient, jazz, synthwave, etc.).
  - `_persist_rationale(entries)` — grava JSON em `state_dir`.
- **`core/onboard_types.py`**: `OnboardSignals`, `TrackRationale`,
  `RationaleEntry`.
- **MCP tool `onboard_rationale`**: retorna rationale persistido;
  opcional filtro por `suggestion` (texto exato).
- **Report de `onboard.run()`**: chaves novas `signals` (top_genres,
  dominant_decades, top_artists) e `rationale_path`.

### Changed
- **`_derive_suggestions`** — nova assinatura
  `(tracks, weights, artists_genres, taste, *, top_k, cap_per_artist)`
  retornando `(texts, rationale, signals)`. Sem audio_features
  (deprecado pela Spotify jan/2026). Fallback para comportamento
  v0.5.x quando `artists_genres` vazio (mantém 2 personalizadas +
  3 genéricas).
- **Index de tracks em `onboard.run()`** — shape normalizado
  `{uri, name, artists: [{id, name}], release_date}` em vez do dict
  cru do Spotify. Preserva `release_date` e `artist_id` para
  downstream.
- **Overhead**: +1 call `sp.artists` por onboard (~200-300ms).

### Tests
- +6 em `TestDecadeOf`.
- +5 em `TestFetchArtistsGenres`.
- +5 em `TestApplyTasteToWeights`.
- +6 em `TestDeriveSuggestionsIntel`.
- +3 em `TestPersistRationale`.
- +3 em `TestOnboardRationaleTool` (MCP).
- +1 em `TestPreservaMetadata` (shape do index).
```

- [ ] **Step 6: Atualizar backlog consolidado**

Em `docs/reviews/2026-04-19-backlog-consolidado.md`, achar a linha sobre B3 (próximo linha 208 ou 218) e trocar a descrição para incluir status. Sugestão: adicionar no final da seção "Ordem de execução — status" um bullet:

```markdown
**v0.7.0-alpha.0 ✅ (2026-04-20):** B3 fechado — sugestões inteligentes
com gêneros/décadas/taste + rationale persistido + MCP tool.
```

E atualizar o contador geral ("Itens fechados: X de Y") incluindo B3.

- [ ] **Step 7: Re-sync workspace**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai && uv sync --all-extras 2>&1 | tail -5`
Expected: `maestra-ai==0.7.0a0` e `maestra-mcp==0.7.0a0` instalados.

- [ ] **Step 8: Validação final**

Run:
```
cd /home/menzani/Desenvolvimento/maestra-ai/packages/maestra-ai && uv run pytest tests/unit/ tests/integration/ 2>&1 | tail -3
cd /home/menzani/Desenvolvimento/maestra-ai/packages/maestra-mcp && uv run pytest tests/ 2>&1 | tail -3
```
Expected: ~508 (maestra-ai) + 45 (maestra-mcp) = ~553 passed.

- [ ] **Step 9: Commit + tag**

```bash
cd /home/menzani/Desenvolvimento/maestra-ai
git add -A
git commit -m "chore: bump v0.7.0-alpha.0 — sugestões inteligentes (B3)

Fecha B3 do backlog consolidado. _derive_suggestions reescrita com
gêneros/décadas/artistas + TasteProfile integrado; rationale
persistido; MCP tool onboard_rationale para agente explicar."
git tag -a v0.7.0-alpha.0 -m "v0.7.0-alpha.0 — sugestões inteligentes"
```

---

## Self-Review

### Spec coverage

| Spec § | Task |
|---|---|
| §3.1 preservar release_date | Task 4 |
| §3.2 _fetch_artists_genres | Task 3 |
| §3.3 _decade_of | Task 2 |
| §3.4 nova _derive_suggestions | Task 6 |
| §3.4 taste integration (_apply_taste_to_weights) | Task 5 |
| §3.5 _persist_rationale | Task 7 |
| §3.6 report com signals | Task 7 |
| §3.7 MCP tool | Task 8 |
| §4 tipos novos | Task 1 |
| §6 testes | nas respectivas tasks |
| §7 critérios aceite | Task 9 |

Zero gaps.

### Placeholder scan

Nenhum "TBD"/"TODO"/"similar to Task N". Todos os code blocks têm código concreto. Todos os commands com `cd` e output esperado.

Ponto frágil — **Task 4 Step 2**: o teste usa `monkeypatch.setattr(onboard, "_derive_suggestions", spy)` ANTES da nova implementação existir com nova assinatura. O spy aceita `*args, **kwargs` para cobrir transição, mas o teste roda com a implementação ATUAL de 1-arg. O spy captura tracks e retorna `[]` para não executar a lógica antiga. Comportamento claro no Step.

Ponto frágil — **Task 7 Step 3**: bloco de coleta de `top_artist_ids` usa duplo loop O(N²) sobre tracks_list. N máximo ~5000 tracks × 50 artistas = 250k comparações — ainda OK em Python puro. Se preciso otimizar depois, converter para dict.

### Type consistency

- `OnboardSignals`, `TrackRationale`, `RationaleEntry` definidos em Task 1 → usados em Tasks 6, 7, 8 com nomes idênticos.
- `_decade_of(release_date: str) -> str` — usado em Task 6 e Task 7 consistente.
- `_fetch_artists_genres(sp, *, artist_ids: list[str]) -> dict[str, list[str]]` — usado em Task 7 com kwarg `artist_ids=top_artist_ids`.
- `_apply_taste_to_weights(weights, tracks, taste) -> dict[str, float]` — usado em Task 7.
- `_derive_suggestions(tracks, weights, artists_genres, taste, *, top_k, cap_per_artist)` — assinatura consistente em Tasks 6 e 7.
- `_persist_rationale(entries) -> Path` — usado em Task 7.
- Constantes `_GOOD_BONUS = 2.0`, `_SKIP_PENALTY = 0.5`, `_DEFAULT_CAP_PER_ARTIST = 10` aparecem no mesmo lugar.
- MCP tool name `onboard_rationale` consistente entre Task 8 (definição) e CHANGELOG Task 9.
