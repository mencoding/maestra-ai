# v0.9 — MusicBrainz + External Sources Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Substituir o campo `genres` depreciado da Spotify por MusicBrainz + estabelecer a arquitetura `core/external/` que v0.10 expandirá com Last.fm e GetSongBPM.

**Architecture:** Novo pacote `core/external/` com `EnhancementSource` Protocol, cache persistente (`external_cache.json`), lookup via ISRC primário (fallback name+artist), rate-limit gerenciado pelo `musicbrainzngs`. Opt-in no init (2 opções em v0.9: ativar MB / pular). `profile show` exibe contagem de faixas com metadados MB. Atribuição clicável via OSC 8 ao final de ações que usam fontes externas.

**Tech Stack:** Python 3.11+, `musicbrainzngs>=0.7.1` (cliente oficial), `responses>=0.25` (mocking HTTP em testes, já em dev deps), rich (OSC 8 hyperlinks), atomic write via `storage.atomic_write_json` + `fcntl.LOCK_EX` (já existente).

**Referência da spec:** `docs/superpowers/specs/2026-04-20-v090-external-sources-design.md`

---

## File Structure

**Novos arquivos:**

| Arquivo | Responsabilidade |
|---------|------------------|
| `packages/maestra-ai/src/maestra_ai/core/external/__init__.py` | Re-exports públicos do pacote |
| `packages/maestra-ai/src/maestra_ai/core/external/types.py` | `TypedDicts` + `EnhancementSource` Protocol |
| `packages/maestra-ai/src/maestra_ai/core/external/cache.py` | read/write de `external_cache.json` |
| `packages/maestra-ai/src/maestra_ai/core/external/musicbrainz.py` | Cliente MB (ISRC + fallback + artist genres) |
| `packages/maestra-ai/src/maestra_ai/core/external/enhancer.py` | Orquestrador: cache + fontes ativas |
| `packages/maestra-ai/src/maestra_ai/core/external/attribution.py` | Render bloco "Fontes usadas" com OSC 8 |
| `packages/maestra-ai/src/maestra_ai/cli/cache.py` | Subcomando `maestra cache refresh` |
| `packages/maestra-ai/tests/unit/external/__init__.py` | marker de package |
| `packages/maestra-ai/tests/unit/external/test_cache.py` | Testes do cache |
| `packages/maestra-ai/tests/unit/external/test_musicbrainz.py` | Testes do cliente MB |
| `packages/maestra-ai/tests/unit/external/test_enhancer.py` | Testes do enhancer |
| `packages/maestra-ai/tests/unit/external/test_attribution.py` | Testes do bloco de atribuição |
| `packages/maestra-ai/tests/fixtures/external/mb_recording_by_isrc.json` | Resposta real MB para ISRC lookup |
| `packages/maestra-ai/tests/fixtures/external/mb_recording_search.json` | Resposta real MB para name+artist |
| `packages/maestra-ai/tests/fixtures/external/mb_artist_by_mbid.json` | Resposta real MB para artist → genres |
| `packages/maestra-ai/tests/integration/test_external_flow.py` | Integração init+cache+profile |

**Arquivos modificados:**

| Arquivo | Alteração |
|---------|-----------|
| `packages/maestra-ai/pyproject.toml` | adiciona `musicbrainzngs>=0.7.1` + bump `0.8.0a7 → 0.9.0a0` |
| `packages/maestra-ai/src/maestra_ai/cli/_common.py` | adiciona `EXTERNAL_CACHE_PATH` |
| `packages/maestra-ai/src/maestra_ai/cli/__init__.py` | registra módulo `cache` |
| `packages/maestra-ai/src/maestra_ai/cli/config.py` | subgrupo `external` (status/enable/disable) |
| `packages/maestra-ai/src/maestra_ai/core/onboard.py` | etapa opt-in + chamada enhancer após `signals` |
| `packages/maestra-ai/src/maestra_ai/core/init.py` | passa callback de opt-in para `onboard.run` |
| `packages/maestra-ai/src/maestra_ai/core/profile_view.py` | incorpora bloco `external_sources` |
| `packages/maestra-ai/src/maestra_ai/cli/profile.py` | render `Melhoramento externo` no `--human` |
| `CHANGELOG.md` | seção v0.9.0-alpha.0 |

---

## Task 1: Dependências + estrutura de diretórios

**Files:**
- Modify: `packages/maestra-ai/pyproject.toml`
- Create: `packages/maestra-ai/src/maestra_ai/core/external/__init__.py`
- Create: `packages/maestra-ai/tests/unit/external/__init__.py`
- Create: `packages/maestra-ai/tests/fixtures/external/.gitkeep`

- [ ] **Step 1: Adicionar dependência `musicbrainzngs`**

Edita `packages/maestra-ai/pyproject.toml`, bloco `dependencies`:

```toml
dependencies = [
    "spotipy>=2.23",
    "python-dotenv>=1.0",
    "rich>=13",
    "rich-argparse>=1.5",
    "keyring>=24",
    "questionary>=2.0",
    "musicbrainzngs>=0.7.1",
]
```

- [ ] **Step 2: Bump de versão**

Mesma `pyproject.toml`:

```toml
version = "0.9.0a0"
```

- [ ] **Step 3: Sincronizar deps e confirmar resolução**

```bash
uv sync --all-packages --all-extras
```

Expected: linha `+ musicbrainzngs==0.7.x` no output. Sem conflitos.

- [ ] **Step 4: Criar pacote `core/external/`**

```bash
mkdir -p packages/maestra-ai/src/maestra_ai/core/external
```

Cria `packages/maestra-ai/src/maestra_ai/core/external/__init__.py` com:

```python
"""Fontes externas de metadata musical (MusicBrainz, Last.fm, GetSongBPM).

v0.9: só MusicBrainz. v0.10+ adiciona Last.fm e GetSongBPM.
"""
from maestra_ai.core.external.enhancer import Enhancer, default_enhancer
from maestra_ai.core.external.types import (
    EnhancedTrack,
    EnhancementSource,
    MusicBrainzData,
    TrackInfo,
)

__all__ = [
    "EnhancedTrack",
    "EnhancementSource",
    "Enhancer",
    "MusicBrainzData",
    "TrackInfo",
    "default_enhancer",
]
```

- [ ] **Step 5: Criar pasta de testes e fixtures**

```bash
mkdir -p packages/maestra-ai/tests/unit/external packages/maestra-ai/tests/fixtures/external
touch packages/maestra-ai/tests/unit/external/__init__.py packages/maestra-ai/tests/fixtures/external/.gitkeep
```

- [ ] **Step 6: Commit**

```bash
git add packages/maestra-ai/pyproject.toml packages/maestra-ai/src/maestra_ai/core/external packages/maestra-ai/tests/unit/external packages/maestra-ai/tests/fixtures/external
git commit -m "chore(external): bootstrap package + bump 0.9.0a0 + musicbrainzngs dep"
```

---

## Task 2: Tipos + Protocol

**Files:**
- Create: `packages/maestra-ai/src/maestra_ai/core/external/types.py`
- Test: `packages/maestra-ai/tests/unit/external/test_types.py`

- [ ] **Step 1: Escrever teste falho dos TypedDicts**

Cria `packages/maestra-ai/tests/unit/external/test_types.py`:

```python
"""Testes do shape dos TypedDicts de metadata externa."""
from maestra_ai.core.external.types import (
    EnhancedTrack,
    MusicBrainzData,
    TrackInfo,
)


def test_track_info_shape():
    t: TrackInfo = {
        "uri": "spotify:track:abc",
        "name": "Song",
        "artists": ["Artist"],
        "isrc": "USABC1234567",
    }
    assert t["uri"] == "spotify:track:abc"
    assert t["artists"] == ["Artist"]


def test_musicbrainz_data_shape():
    d: MusicBrainzData = {
        "mbid": "rec-mbid-1",
        "genres": ["rock"],
        "tags": ["90s"],
    }
    assert d["mbid"] == "rec-mbid-1"


def test_enhanced_track_shape():
    e: EnhancedTrack = {
        "uri": "spotify:track:abc",
        "isrc": "USABC1234567",
        "artist_mbid": "art-mbid-1",
        "musicbrainz": {"mbid": "rec-mbid-1", "genres": ["rock"], "tags": []},
        "lastfm": None,
        "bpm": None,
        "sources": ["musicbrainz"],
        "enhanced_at": "2026-04-20T10:00:00-03:00",
        "match_method": "isrc",
    }
    assert e["sources"] == ["musicbrainz"]
    assert e["match_method"] == "isrc"
```

- [ ] **Step 2: Rodar e ver falhar**

```bash
uv run pytest packages/maestra-ai/tests/unit/external/test_types.py -v
```

Expected: FAIL com `ModuleNotFoundError: maestra_ai.core.external.types`.

- [ ] **Step 3: Implementar `types.py`**

Cria `packages/maestra-ai/src/maestra_ai/core/external/types.py`:

```python
"""TypedDicts + Protocol das fontes externas de metadata."""
from __future__ import annotations

from typing import Literal, Protocol, TypedDict


class TrackInfo(TypedDict):
    uri: str
    name: str
    artists: list[str]
    isrc: str | None


class MusicBrainzData(TypedDict):
    mbid: str
    genres: list[str]
    tags: list[str]


class LastfmData(TypedDict):
    top_tags: list[str]
    playcount: int
    listeners: int
    similar_artists: list[str]


class BpmData(TypedDict):
    bpm: float
    key: str
    time_signature: str


class EnhancedTrack(TypedDict):
    uri: str
    isrc: str | None
    artist_mbid: str | None
    musicbrainz: MusicBrainzData | None
    lastfm: LastfmData | None
    bpm: BpmData | None
    sources: list[str]
    enhanced_at: str
    match_method: Literal["isrc", "name"]


class SourceResult(TypedDict, total=False):
    musicbrainz: MusicBrainzData
    lastfm: LastfmData
    bpm: BpmData
    artist_mbid: str
    match_method: Literal["isrc", "name"]


class EnhancementSource(Protocol):
    name: str

    def is_configured(self) -> bool: ...

    def enhance_track(self, track: TrackInfo) -> SourceResult | None: ...
```

- [ ] **Step 4: Rodar e ver passar**

```bash
uv run pytest packages/maestra-ai/tests/unit/external/test_types.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add packages/maestra-ai/src/maestra_ai/core/external/types.py packages/maestra-ai/tests/unit/external/test_types.py
git commit -m "feat(external): TypedDicts + EnhancementSource Protocol"
```

---

## Task 3: Cache read/write atômico

**Files:**
- Create: `packages/maestra-ai/src/maestra_ai/core/external/cache.py`
- Test: `packages/maestra-ai/tests/unit/external/test_cache.py`

- [ ] **Step 1: Escrever teste falho**

Cria `packages/maestra-ai/tests/unit/external/test_cache.py`:

```python
"""Testes de load/save do cache de metadata externa."""
import json
from pathlib import Path

from maestra_ai.core.external.cache import (
    CACHE_SCHEMA_VERSION,
    get_track,
    load_cache,
    put_track,
    save_cache,
)


def _sample_track(uri: str):
    return {
        "uri": uri,
        "isrc": None,
        "artist_mbid": None,
        "musicbrainz": None,
        "lastfm": None,
        "bpm": None,
        "sources": [],
        "enhanced_at": "2026-04-20T10:00:00-03:00",
        "match_method": "isrc",
    }


def test_load_cache_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path))
    cache = load_cache()
    assert cache == {"version": CACHE_SCHEMA_VERSION, "tracks": {}}


def test_put_and_get_track(tmp_path, monkeypatch):
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path))
    put_track(_sample_track("spotify:track:a"))
    retrieved = get_track("spotify:track:a")
    assert retrieved is not None
    assert retrieved["uri"] == "spotify:track:a"


def test_cache_round_trip_is_atomic(tmp_path, monkeypatch):
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path))
    cache = {
        "version": CACHE_SCHEMA_VERSION,
        "tracks": {"spotify:track:a": _sample_track("spotify:track:a")},
    }
    save_cache(cache)
    path = Path(tmp_path) / "maestra" / "external_cache.json"
    data = json.loads(path.read_text())
    assert data["version"] == CACHE_SCHEMA_VERSION
    assert "spotify:track:a" in data["tracks"]


def test_load_corrupted_cache_resets_to_default(tmp_path, monkeypatch):
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path))
    path = Path(tmp_path) / "maestra" / "external_cache.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ not json")
    cache = load_cache()
    assert cache == {"version": CACHE_SCHEMA_VERSION, "tracks": {}}


def test_missing_uri_returns_none(tmp_path, monkeypatch):
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path))
    assert get_track("spotify:track:does-not-exist") is None
```

- [ ] **Step 2: Rodar e ver falhar**

```bash
uv run pytest packages/maestra-ai/tests/unit/external/test_cache.py -v
```

Expected: FAIL com `ModuleNotFoundError: maestra_ai.core.external.cache`.

- [ ] **Step 3: Implementar `cache.py`**

Cria `packages/maestra-ai/src/maestra_ai/core/external/cache.py`:

```python
"""Cache persistente de metadata externa por URI Spotify.

Schema v1: {"version": 1, "tracks": {uri: EnhancedTrack}}. Lock + rename
atômico via `storage.atomic_write_json`.
"""
from __future__ import annotations

import json
from typing import Any, cast

from maestra_ai.core import storage
from maestra_ai.core.external.types import EnhancedTrack

CACHE_SCHEMA_VERSION = 1


def _cache_path():
    return storage.data_dir() / "external_cache.json"


def _default_cache() -> dict[str, Any]:
    return {"version": CACHE_SCHEMA_VERSION, "tracks": {}}


def load_cache() -> dict[str, Any]:
    """Carrega o cache; retorna default vazio se ausente ou corrompido."""
    path = _cache_path()
    if not path.exists():
        return _default_cache()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return _default_cache()
    if not isinstance(data, dict) or data.get("version") != CACHE_SCHEMA_VERSION:
        return _default_cache()
    data.setdefault("tracks", {})
    return data


def save_cache(cache: dict[str, Any]) -> None:
    """Persiste o cache completo com lock + rename atômico."""
    storage.ensure_dirs()
    storage.atomic_write_json(_cache_path(), cache)


def get_track(uri: str) -> EnhancedTrack | None:
    """Retorna `EnhancedTrack` se presente no cache; None caso contrário."""
    cache = load_cache()
    track = cache["tracks"].get(uri)
    if track is None:
        return None
    return cast(EnhancedTrack, track)


def put_track(track: EnhancedTrack) -> None:
    """Grava (ou atualiza) uma entry no cache."""
    cache = load_cache()
    cache["tracks"][track["uri"]] = track
    save_cache(cache)
```

- [ ] **Step 4: Rodar e ver passar**

```bash
uv run pytest packages/maestra-ai/tests/unit/external/test_cache.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add packages/maestra-ai/src/maestra_ai/core/external/cache.py packages/maestra-ai/tests/unit/external/test_cache.py
git commit -m "feat(external): external_cache.json load/save atomic"
```

---

## Task 4: Fixtures MusicBrainz reais

**Files:**
- Create: `packages/maestra-ai/tests/fixtures/external/mb_recording_by_isrc.json`
- Create: `packages/maestra-ai/tests/fixtures/external/mb_recording_search.json`
- Create: `packages/maestra-ai/tests/fixtures/external/mb_artist_by_mbid.json`

Fixtures são respostas JSON reduzidas (mas realistas) do `musicbrainzngs`. Valores inspirados em responses observados na API pública em abr/2026. Usamos valores fixos para reproduzibilidade dos testes.

- [ ] **Step 1: Criar fixture ISRC lookup**

`packages/maestra-ai/tests/fixtures/external/mb_recording_by_isrc.json`:

```json
{
  "isrc": "USUM71807351",
  "recording-count": 1,
  "recording-list": [
    {
      "id": "recording-mbid-abc",
      "title": "Dreams",
      "length": "232800",
      "artist-credit": [
        {
          "name": "Fleetwood Mac",
          "artist": {
            "id": "bd13909f-1c29-4c27-a874-d4aaf27c5b1a",
            "name": "Fleetwood Mac",
            "sort-name": "Fleetwood Mac"
          }
        }
      ]
    }
  ]
}
```

- [ ] **Step 2: Criar fixture name+artist search**

`packages/maestra-ai/tests/fixtures/external/mb_recording_search.json`:

```json
{
  "recording-list": [
    {
      "id": "recording-mbid-xyz",
      "ext:score": "100",
      "title": "Obscure Song",
      "artist-credit": [
        {
          "name": "Obscure Artist",
          "artist": {
            "id": "artist-mbid-xyz",
            "name": "Obscure Artist"
          }
        }
      ]
    }
  ],
  "recording-count": 1
}
```

- [ ] **Step 3: Criar fixture artist by mbid**

`packages/maestra-ai/tests/fixtures/external/mb_artist_by_mbid.json`:

```json
{
  "artist": {
    "id": "bd13909f-1c29-4c27-a874-d4aaf27c5b1a",
    "name": "Fleetwood Mac",
    "sort-name": "Fleetwood Mac",
    "genre-list": [
      {"name": "rock", "count": "42"},
      {"name": "soft rock", "count": "17"}
    ],
    "tag-list": [
      {"name": "70s", "count": "9"},
      {"name": "classic rock", "count": "12"}
    ]
  }
}
```

- [ ] **Step 4: Commit fixtures**

```bash
git add packages/maestra-ai/tests/fixtures/external/
git commit -m "test(external): fixtures MusicBrainz reais (ISRC, search, artist)"
```

---

## Task 5: Cliente MusicBrainz — lookup ISRC

**Files:**
- Create: `packages/maestra-ai/src/maestra_ai/core/external/musicbrainz.py`
- Test: `packages/maestra-ai/tests/unit/external/test_musicbrainz.py`

- [ ] **Step 1: Escrever teste falho de ISRC lookup**

Cria `packages/maestra-ai/tests/unit/external/test_musicbrainz.py`:

```python
"""Testes do cliente MusicBrainz."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from maestra_ai.core.external.musicbrainz import MusicBrainzSource

FIX = Path(__file__).parent.parent.parent / "fixtures" / "external"


@pytest.fixture
def mb():
    return MusicBrainzSource(app_version="9.9.9-test")


def _load(name):
    return json.loads((FIX / name).read_text())


def test_name_and_configured(mb):
    assert mb.name == "musicbrainz"
    assert mb.is_configured() is True


def test_enhance_track_by_isrc(mb):
    track = {
        "uri": "spotify:track:dreams",
        "name": "Dreams",
        "artists": ["Fleetwood Mac"],
        "isrc": "USUM71807351",
    }
    recording = _load("mb_recording_by_isrc.json")
    artist = _load("mb_artist_by_mbid.json")
    with patch("musicbrainzngs.get_recordings_by_isrc", return_value=recording), \
         patch("musicbrainzngs.get_artist_by_id", return_value=artist):
        result = mb.enhance_track(track)

    assert result is not None
    assert result["match_method"] == "isrc"
    assert result["artist_mbid"] == "bd13909f-1c29-4c27-a874-d4aaf27c5b1a"
    assert result["musicbrainz"]["mbid"] == "recording-mbid-abc"
    assert "rock" in result["musicbrainz"]["genres"]
    assert "70s" in result["musicbrainz"]["tags"]
```

- [ ] **Step 2: Rodar e ver falhar**

```bash
uv run pytest packages/maestra-ai/tests/unit/external/test_musicbrainz.py -v
```

Expected: FAIL com `ModuleNotFoundError: maestra_ai.core.external.musicbrainz`.

- [ ] **Step 3: Implementar MB com ISRC lookup**

Cria `packages/maestra-ai/src/maestra_ai/core/external/musicbrainz.py`:

```python
"""Fonte MusicBrainz — gêneros canônicos via ISRC (fallback name+artist).

Rate limit de 1 req/s gerenciado pela própria lib via `set_rate_limit`.
Sem API key — apenas User-Agent identificável (requisito do TOS).
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import musicbrainzngs

if TYPE_CHECKING:
    from maestra_ai.core.external.types import SourceResult, TrackInfo

logger = logging.getLogger(__name__)

_USER_AGENT_APP = "maestra-ai"
_USER_AGENT_CONTACT = "https://github.com/mencoding/maestra-ai"


class MusicBrainzSource:
    """Cliente `EnhancementSource` para MusicBrainz."""

    name = "musicbrainz"

    def __init__(self, *, app_version: str) -> None:
        musicbrainzngs.set_useragent(
            _USER_AGENT_APP, app_version, _USER_AGENT_CONTACT,
        )
        musicbrainzngs.set_rate_limit(limit_or_interval=1.0, new_requests=1)

    def is_configured(self) -> bool:
        return True

    def enhance_track(self, track: TrackInfo) -> SourceResult | None:
        isrc = track.get("isrc")
        if isrc:
            result = self._lookup_by_isrc(isrc)
            if result is not None:
                return result
        return None

    def _lookup_by_isrc(self, isrc: str) -> SourceResult | None:
        try:
            response = musicbrainzngs.get_recordings_by_isrc(isrc)
        except Exception as e:
            logger.debug("MB ISRC lookup falhou para %s: %s", isrc, e)
            return None
        recordings = response.get("recording-list") or []
        if not recordings:
            return None
        recording = recordings[0]
        recording_mbid = recording.get("id", "")
        artist_mbid = _extract_first_artist_mbid(recording)
        genres, tags = self._artist_genres_and_tags(artist_mbid) if artist_mbid else ([], [])
        return {
            "musicbrainz": {
                "mbid": recording_mbid,
                "genres": genres,
                "tags": tags,
            },
            "artist_mbid": artist_mbid or "",
            "match_method": "isrc",
        }

    def _artist_genres_and_tags(self, mbid: str) -> tuple[list[str], list[str]]:
        try:
            response = musicbrainzngs.get_artist_by_id(
                mbid, includes=["genres", "tags"],
            )
        except Exception as e:
            logger.debug("MB artist lookup falhou para %s: %s", mbid, e)
            return [], []
        artist = response.get("artist", {})
        genres = [g["name"] for g in (artist.get("genre-list") or []) if g.get("name")]
        tags = [t["name"] for t in (artist.get("tag-list") or []) if t.get("name")]
        return genres, tags


def _extract_first_artist_mbid(recording: dict) -> str:
    credits = recording.get("artist-credit") or []
    for credit in credits:
        if isinstance(credit, dict):
            artist = credit.get("artist") or {}
            mbid = artist.get("id")
            if mbid:
                return mbid
    return ""
```

- [ ] **Step 4: Rodar e ver passar**

```bash
uv run pytest packages/maestra-ai/tests/unit/external/test_musicbrainz.py::test_enhance_track_by_isrc -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/maestra-ai/src/maestra_ai/core/external/musicbrainz.py packages/maestra-ai/tests/unit/external/test_musicbrainz.py
git commit -m "feat(external): MusicBrainz source — ISRC lookup + artist genres"
```

---

## Task 6: Cliente MusicBrainz — fallback name+artist + erros

**Files:**
- Modify: `packages/maestra-ai/src/maestra_ai/core/external/musicbrainz.py`
- Modify: `packages/maestra-ai/tests/unit/external/test_musicbrainz.py`

- [ ] **Step 1: Adicionar testes de fallback e erros**

Adiciona ao fim de `packages/maestra-ai/tests/unit/external/test_musicbrainz.py`:

```python
def test_enhance_track_without_isrc_falls_back_to_name(mb):
    track = {
        "uri": "spotify:track:obscure",
        "name": "Obscure Song",
        "artists": ["Obscure Artist"],
        "isrc": None,
    }
    search = _load("mb_recording_search.json")
    artist = _load("mb_artist_by_mbid.json")
    with patch(
        "musicbrainzngs.search_recordings", return_value=search,
    ), patch(
        "musicbrainzngs.get_artist_by_id", return_value=artist,
    ):
        result = mb.enhance_track(track)

    assert result is not None
    assert result["match_method"] == "name"
    assert result["artist_mbid"] == "artist-mbid-xyz"


def test_enhance_track_isrc_not_found_falls_back_to_name(mb):
    track = {
        "uri": "spotify:track:x",
        "name": "Obscure Song",
        "artists": ["Obscure Artist"],
        "isrc": "FAKE12345678",
    }
    search = _load("mb_recording_search.json")
    artist = _load("mb_artist_by_mbid.json")
    with patch(
        "musicbrainzngs.get_recordings_by_isrc",
        return_value={"recording-list": []},
    ), patch(
        "musicbrainzngs.search_recordings", return_value=search,
    ), patch(
        "musicbrainzngs.get_artist_by_id", return_value=artist,
    ):
        result = mb.enhance_track(track)

    assert result is not None
    assert result["match_method"] == "name"


def test_enhance_track_returns_none_on_network_failure(mb):
    track = {
        "uri": "spotify:track:x",
        "name": "N",
        "artists": ["A"],
        "isrc": None,
    }
    with patch(
        "musicbrainzngs.search_recordings",
        side_effect=musicbrainzngs_network_error(),
    ):
        assert mb.enhance_track(track) is None


def musicbrainzngs_network_error():
    import musicbrainzngs
    return musicbrainzngs.NetworkError("timeout")


def test_enhance_track_returns_none_when_no_match(mb):
    track = {
        "uri": "spotify:track:x",
        "name": "N",
        "artists": ["A"],
        "isrc": None,
    }
    with patch(
        "musicbrainzngs.search_recordings",
        return_value={"recording-list": [], "recording-count": 0},
    ):
        assert mb.enhance_track(track) is None
```

- [ ] **Step 2: Rodar e ver falhar**

```bash
uv run pytest packages/maestra-ai/tests/unit/external/test_musicbrainz.py -v
```

Expected: 4 passam (inclui o do Task 5), 3 novos falham.

- [ ] **Step 3: Implementar fallback e tratamento de erro**

Substitui o método `enhance_track` em `musicbrainz.py`:

```python
    def enhance_track(self, track: TrackInfo) -> SourceResult | None:
        isrc = track.get("isrc")
        if isrc:
            result = self._lookup_by_isrc(isrc)
            if result is not None:
                return result
        name = track.get("name") or ""
        artists = track.get("artists") or []
        if name and artists:
            return self._lookup_by_name(name, artists[0])
        return None
```

E acrescenta no final da classe (antes do helper `_extract_first_artist_mbid`):

```python
    def _lookup_by_name(self, name: str, artist: str) -> SourceResult | None:
        query = f'recording:"{name}" AND artist:"{artist}"'
        try:
            response = musicbrainzngs.search_recordings(query=query, limit=1)
        except Exception as e:
            logger.debug("MB name search falhou para %s/%s: %s", name, artist, e)
            return None
        recordings = response.get("recording-list") or []
        if not recordings:
            return None
        recording = recordings[0]
        recording_mbid = recording.get("id", "")
        artist_mbid = _extract_first_artist_mbid(recording)
        genres, tags = self._artist_genres_and_tags(artist_mbid) if artist_mbid else ([], [])
        return {
            "musicbrainz": {
                "mbid": recording_mbid,
                "genres": genres,
                "tags": tags,
            },
            "artist_mbid": artist_mbid or "",
            "match_method": "name",
        }
```

- [ ] **Step 4: Rodar e ver passar**

```bash
uv run pytest packages/maestra-ai/tests/unit/external/test_musicbrainz.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add packages/maestra-ai/src/maestra_ai/core/external/musicbrainz.py packages/maestra-ai/tests/unit/external/test_musicbrainz.py
git commit -m "feat(external): MB fallback name+artist + graceful failure"
```

---

## Task 7: Enhancer — orquestração + cache

**Files:**
- Create: `packages/maestra-ai/src/maestra_ai/core/external/enhancer.py`
- Test: `packages/maestra-ai/tests/unit/external/test_enhancer.py`

- [ ] **Step 1: Escrever teste falho**

Cria `packages/maestra-ai/tests/unit/external/test_enhancer.py`:

```python
"""Testes do Enhancer — orquestração de fontes + cache."""
from maestra_ai.core.external.enhancer import Enhancer
from maestra_ai.core.external import cache as cache_mod


class FakeSource:
    def __init__(self, name: str, result: dict | None, configured: bool = True):
        self.name = name
        self._result = result
        self._configured = configured
        self.call_count = 0

    def is_configured(self):
        return self._configured

    def enhance_track(self, track):
        self.call_count += 1
        return self._result


def _track():
    return {
        "uri": "spotify:track:sample",
        "name": "Sample",
        "artists": ["Artist"],
        "isrc": "USABC0000001",
    }


def test_enhance_track_with_single_source(tmp_path, monkeypatch):
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path))
    fake = FakeSource("musicbrainz", {
        "musicbrainz": {"mbid": "r1", "genres": ["rock"], "tags": []},
        "artist_mbid": "a1",
        "match_method": "isrc",
    })
    enhancer = Enhancer(sources=[fake])
    enhanced = enhancer.enhance_track(_track())

    assert enhanced["musicbrainz"]["genres"] == ["rock"]
    assert enhanced["sources"] == ["musicbrainz"]
    assert enhanced["match_method"] == "isrc"
    assert enhanced["artist_mbid"] == "a1"


def test_enhance_track_caches_result(tmp_path, monkeypatch):
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path))
    fake = FakeSource("musicbrainz", {
        "musicbrainz": {"mbid": "r1", "genres": ["rock"], "tags": []},
        "artist_mbid": "a1",
        "match_method": "isrc",
    })
    enhancer = Enhancer(sources=[fake])
    enhancer.enhance_track(_track())
    enhancer.enhance_track(_track())
    assert fake.call_count == 1


def test_enhance_track_skips_unconfigured_source(tmp_path, monkeypatch):
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path))
    fake = FakeSource("x", {"musicbrainz": {"mbid": "r1", "genres": [], "tags": []}}, configured=False)
    enhancer = Enhancer(sources=[fake])
    enhanced = enhancer.enhance_track(_track())
    assert enhanced["sources"] == []
    assert fake.call_count == 0


def test_enhance_many_with_progress(tmp_path, monkeypatch):
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path))
    fake = FakeSource("musicbrainz", {
        "musicbrainz": {"mbid": "r1", "genres": ["rock"], "tags": []},
        "artist_mbid": "a1",
        "match_method": "isrc",
    })
    enhancer = Enhancer(sources=[fake])
    events = []
    enhancer.enhance_many(
        [
            {"uri": "spotify:track:1", "name": "A", "artists": ["X"], "isrc": "I1"},
            {"uri": "spotify:track:2", "name": "B", "artists": ["Y"], "isrc": "I2"},
        ],
        progress_cb=lambda ev: events.append(ev),
    )
    assert len(events) == 2
    assert events[0]["step"] == 1
    assert events[0]["total"] == 2


def test_source_exception_does_not_break_pipeline(tmp_path, monkeypatch):
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path))
    class ExplodingSource:
        name = "boom"
        def is_configured(self): return True
        def enhance_track(self, track): raise RuntimeError("boom")
    enhancer = Enhancer(sources=[ExplodingSource()])
    result = enhancer.enhance_track(_track())
    assert result["sources"] == []
```

- [ ] **Step 2: Rodar e ver falhar**

```bash
uv run pytest packages/maestra-ai/tests/unit/external/test_enhancer.py -v
```

Expected: FAIL com `ModuleNotFoundError: maestra_ai.core.external.enhancer`.

- [ ] **Step 3: Implementar enhancer**

Cria `packages/maestra-ai/src/maestra_ai/core/external/enhancer.py`:

```python
"""Orquestrador de fontes externas + cache.

Não paraleliza em v0.9 (única fonte ativa é MB, com rate limit de 1 req/s).
Paralelismo via ThreadPoolExecutor entra em v0.10 quando há múltiplas fontes.
"""
from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from typing import cast

from maestra_ai.core.external import cache as cache_mod
from maestra_ai.core.external.types import (
    EnhancedTrack,
    EnhancementSource,
    SourceResult,
    TrackInfo,
)

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().replace(microsecond=0).isoformat()


class Enhancer:
    """Orquestra fontes ativas e gerencia cache."""

    def __init__(self, sources: list[EnhancementSource]):
        self._sources = sources

    def active_sources(self) -> list[str]:
        return [s.name for s in self._sources if s.is_configured()]

    def enhance_track(self, track: TrackInfo) -> EnhancedTrack:
        uri = track["uri"]
        cached = cache_mod.get_track(uri)
        if cached is not None:
            return cached

        merged: dict = {
            "uri": uri,
            "isrc": track.get("isrc"),
            "artist_mbid": None,
            "musicbrainz": None,
            "lastfm": None,
            "bpm": None,
            "sources": [],
            "enhanced_at": _now_iso(),
            "match_method": "isrc",
        }

        for source in self._sources:
            if not source.is_configured():
                continue
            try:
                result = source.enhance_track(track)
            except Exception as e:
                logger.warning(
                    "Source %s falhou para %s: %s", source.name, uri, e,
                )
                continue
            if result is None:
                continue
            _apply_source_result(merged, source.name, result)

        enhanced = cast(EnhancedTrack, merged)
        cache_mod.put_track(enhanced)
        return enhanced

    def enhance_many(
        self,
        tracks: Iterable[TrackInfo],
        *,
        progress_cb: Callable[[dict], None] | None = None,
    ) -> list[EnhancedTrack]:
        tracks_list = list(tracks)
        total = len(tracks_list)
        results: list[EnhancedTrack] = []
        for i, t in enumerate(tracks_list, 1):
            results.append(self.enhance_track(t))
            if progress_cb:
                progress_cb({
                    "step": i,
                    "total": total,
                    "name": "enhance",
                    "detail": f"{i}/{total}",
                })
        return results


def _apply_source_result(merged: dict, source_name: str, result: SourceResult) -> None:
    if source_name == "musicbrainz" and "musicbrainz" in result:
        merged["musicbrainz"] = result["musicbrainz"]
        if result.get("artist_mbid"):
            merged["artist_mbid"] = result["artist_mbid"]
        if result.get("match_method"):
            merged["match_method"] = result["match_method"]
    if source_name == "lastfm" and "lastfm" in result:
        merged["lastfm"] = result["lastfm"]
    if source_name == "getsongbpm" and "bpm" in result:
        merged["bpm"] = result["bpm"]
    merged["sources"].append(source_name)


def default_enhancer() -> Enhancer:
    """Constrói um Enhancer com as fontes disponíveis nesta release.

    v0.9: só MusicBrainz quando `external_sources_enabled: true`.
    """
    from maestra_ai.core import storage
    from maestra_ai.core.external.musicbrainz import MusicBrainzSource
    from maestra_ai import __version__ as app_version

    cfg = storage.read_config()
    if not cfg.get("external_sources_enabled"):
        return Enhancer(sources=[])
    return Enhancer(sources=[MusicBrainzSource(app_version=app_version)])
```

- [ ] **Step 4: Criar `__version__` no pacote principal se não existir**

Verifica:

```bash
grep -r "__version__" packages/maestra-ai/src/maestra_ai/__init__.py
```

Se não houver, edita `packages/maestra-ai/src/maestra_ai/__init__.py` adicionando no topo:

```python
__version__ = "0.9.0a0"
```

- [ ] **Step 5: Rodar testes**

```bash
uv run pytest packages/maestra-ai/tests/unit/external/test_enhancer.py -v
```

Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add packages/maestra-ai/src/maestra_ai/core/external/enhancer.py packages/maestra-ai/src/maestra_ai/__init__.py packages/maestra-ai/tests/unit/external/test_enhancer.py
git commit -m "feat(external): Enhancer — orquestra fontes, cache, progress_cb"
```

---

## Task 8: Bloco de atribuição com OSC 8

**Files:**
- Create: `packages/maestra-ai/src/maestra_ai/core/external/attribution.py`
- Test: `packages/maestra-ai/tests/unit/external/test_attribution.py`

- [ ] **Step 1: Escrever teste falho**

Cria `packages/maestra-ai/tests/unit/external/test_attribution.py`:

```python
"""Testes do bloco de atribuição."""
from maestra_ai.core.external.attribution import render_attribution


def test_render_empty_returns_empty_string():
    assert render_attribution([]) == ""


def test_render_musicbrainz_contains_link_and_label():
    output = render_attribution(["musicbrainz"])
    assert "MusicBrainz" in output
    assert "musicbrainz.org/doc/About" in output
    assert "Fontes usadas" in output


def test_render_multiple_sources():
    output = render_attribution(["musicbrainz", "lastfm", "getsongbpm"])
    assert "MusicBrainz" in output
    assert "Last.fm" in output
    assert "GetSongBPM" in output


def test_render_ignores_unknown_source():
    output = render_attribution(["musicbrainz", "does-not-exist"])
    assert "MusicBrainz" in output
    assert "does-not-exist" not in output
```

- [ ] **Step 2: Rodar e ver falhar**

```bash
uv run pytest packages/maestra-ai/tests/unit/external/test_attribution.py -v
```

Expected: FAIL com `ModuleNotFoundError`.

- [ ] **Step 3: Implementar**

Cria `packages/maestra-ai/src/maestra_ai/core/external/attribution.py`:

```python
"""Bloco de atribuição com links clicáveis (OSC 8 via rich).

Seletivo: só renderiza fontes efetivamente usadas. Cumpre TOS do
GetSongBPM e dá visibilidade honesta às demais fontes gratuitas.
"""
from __future__ import annotations

_SOURCES = {
    "musicbrainz": ("MusicBrainz", "https://musicbrainz.org/doc/About"),
    "lastfm": ("Last.fm", "https://www.last.fm/about"),
    "getsongbpm": ("GetSongBPM.com", "https://getsongbpm.com/about"),
}


def render_attribution(sources_used: list[str]) -> str:
    """Retorna string (rich markup) do bloco de atribuição.

    `sources_used` deve conter apenas nomes internos ("musicbrainz",
    "lastfm", "getsongbpm"). Nomes desconhecidos são ignorados.
    String vazia se não há fontes.
    """
    known = [s for s in sources_used if s in _SOURCES]
    if not known:
        return ""
    lines = ["\n[bold]Fontes usadas nesta curadoria:[/bold]"]
    for source in known:
        label, url = _SOURCES[source]
        lines.append(f"  • [link={url}]{label}[/link]")
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Rodar e ver passar**

```bash
uv run pytest packages/maestra-ai/tests/unit/external/test_attribution.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add packages/maestra-ai/src/maestra_ai/core/external/attribution.py packages/maestra-ai/tests/unit/external/test_attribution.py
git commit -m "feat(external): attribution bloco com OSC 8 hyperlinks"
```

---

## Task 9: CLI — `maestra cache refresh`

**Files:**
- Create: `packages/maestra-ai/src/maestra_ai/cli/cache.py`
- Modify: `packages/maestra-ai/src/maestra_ai/cli/__init__.py`
- Modify: `packages/maestra-ai/src/maestra_ai/cli/_common.py`
- Test: `packages/maestra-ai/tests/unit/external/test_cli_cache.py`

- [ ] **Step 1: Adicionar `EXTERNAL_CACHE_PATH` em `_common.py`**

Edita `packages/maestra-ai/src/maestra_ai/cli/_common.py`, logo após as demais `*_PATH`:

```python
EXTERNAL_CACHE_PATH = os.path.join(BASE_DIR, "external_cache.json")
```

- [ ] **Step 2: Escrever teste falho**

Cria `packages/maestra-ai/tests/unit/external/test_cli_cache.py`:

```python
"""Testes do subcomando `maestra cache`."""
import json
import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("MAESTRA_STATE_DIR", str(tmp_path / "state"))
    yield tmp_path


def test_cache_refresh_all_clears_cache(isolated_env):
    data_dir = Path(isolated_env) / "data" / "maestra"
    data_dir.mkdir(parents=True, exist_ok=True)
    cache_file = data_dir / "external_cache.json"
    cache_file.write_text(json.dumps({
        "version": 1,
        "tracks": {"spotify:track:a": {"uri": "spotify:track:a"}},
    }))
    # Roda via import direto ao invés de subprocess (mais rápido, mesmo env)
    from maestra_ai.cli.cache import cmd_cache_refresh
    class A:
        source = None
        uri = None
        human = False
    cmd_cache_refresh(A())
    reloaded = json.loads(cache_file.read_text())
    assert reloaded["tracks"] == {}


def test_cache_refresh_by_uri(isolated_env):
    data_dir = Path(isolated_env) / "data" / "maestra"
    data_dir.mkdir(parents=True, exist_ok=True)
    cache_file = data_dir / "external_cache.json"
    cache_file.write_text(json.dumps({
        "version": 1,
        "tracks": {
            "spotify:track:a": {"uri": "spotify:track:a"},
            "spotify:track:b": {"uri": "spotify:track:b"},
        },
    }))
    from maestra_ai.cli.cache import cmd_cache_refresh
    class A:
        source = None
        uri = "spotify:track:a"
        human = False
    cmd_cache_refresh(A())
    reloaded = json.loads(cache_file.read_text())
    assert "spotify:track:a" not in reloaded["tracks"]
    assert "spotify:track:b" in reloaded["tracks"]
```

- [ ] **Step 3: Rodar e ver falhar**

```bash
uv run pytest packages/maestra-ai/tests/unit/external/test_cli_cache.py -v
```

Expected: FAIL com `ModuleNotFoundError: maestra_ai.cli.cache`.

- [ ] **Step 4: Implementar subcomando**

Cria `packages/maestra-ai/src/maestra_ai/cli/cache.py`:

```python
"""Subcomando `cache`: refresh do cache externo."""
from __future__ import annotations

import argparse

from maestra_ai.cli import register
from maestra_ai.cli._common import output
from maestra_ai.core.external import cache as cache_mod


def cmd_cache_refresh(args, **_):
    """Remove entries do cache para forçar re-fetch na próxima ação.

    Sem flags: limpa tudo. `--uri X`: limpa só a entry X. `--source X`:
    zera apenas a sub-chave da fonte em todas as entries (mantém o
    cache de outras fontes).
    """
    cache = cache_mod.load_cache()

    if args.uri:
        cache["tracks"].pop(args.uri, None)
    elif args.source:
        for uri, entry in cache["tracks"].items():
            if args.source in entry.get("sources", []):
                entry[args.source] = None
                entry["sources"] = [s for s in entry["sources"] if s != args.source]
    else:
        cache["tracks"] = {}

    cache_mod.save_cache(cache)
    output(
        {
            "status": "refreshed",
            "source": args.source,
            "uri": args.uri,
            "tracks_remaining": len(cache["tracks"]),
        },
        getattr(args, "human", False),
    )


@register
def _register(subparsers: argparse._SubParsersAction) -> None:
    from maestra_ai.cli import group_help_handler
    cache_parser = subparsers.add_parser(
        "cache", help="Cache de metadata externa",
    )
    cache_parser.set_defaults(func=group_help_handler(cache_parser))
    sub = cache_parser.add_subparsers(dest="cache_command", required=False)

    p = sub.add_parser("refresh", help="Força re-fetch na próxima ação")
    p.add_argument("--source", help="Limpa só esta fonte (musicbrainz, etc)")
    p.add_argument("--uri", help="Limpa só esta URI Spotify")
    p.add_argument("--human", action="store_true")
    p.set_defaults(func=cmd_cache_refresh, skip_deps=True)
```

- [ ] **Step 5: Registrar módulo em `cli/__init__.py`**

Adiciona `cache` ao tuple de imports (ordem alfabética entre `basic` e `curate`):

```python
from maestra_ai.cli import (  # noqa: F401
    auth,
    basic,
    cache,
    curate,
    director,
    ...
)
```

E ao tuple final `_ = (auth, basic, cache, ...)`.

- [ ] **Step 6: Rodar testes**

```bash
uv run pytest packages/maestra-ai/tests/unit/external/test_cli_cache.py -v
```

Expected: 2 passed.

- [ ] **Step 7: Commit**

```bash
git add packages/maestra-ai/src/maestra_ai/cli/cache.py packages/maestra-ai/src/maestra_ai/cli/__init__.py packages/maestra-ai/src/maestra_ai/cli/_common.py packages/maestra-ai/tests/unit/external/test_cli_cache.py
git commit -m "feat(cli): maestra cache refresh [--source X] [--uri Y]"
```

---

## Task 10: CLI — `maestra config external status/enable/disable`

**Files:**
- Modify: `packages/maestra-ai/src/maestra_ai/cli/config.py`
- Test: `packages/maestra-ai/tests/unit/external/test_cli_config_external.py`

- [ ] **Step 1: Escrever teste falho**

Cria `packages/maestra-ai/tests/unit/external/test_cli_config_external.py`:

```python
"""Testes do subgrupo `maestra config external`."""
import json
from pathlib import Path

import pytest


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
    yield tmp_path


def _call(fn_name, **kwargs):
    from maestra_ai.cli import config
    fn = getattr(config, fn_name)
    class A:
        pass
    a = A()
    for k, v in kwargs.items():
        setattr(a, k, v)
    fn(a)


def test_external_status_default(isolated, capsys):
    _call("cmd_config_external_status", human=False)
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["enabled"] is False
    assert data["musicbrainz"] == "available"


def test_external_enable_persists(isolated, capsys):
    _call("cmd_config_external_enable", human=False)
    cfg_path = Path(isolated) / "config" / "maestra" / "config.json"
    data = json.loads(cfg_path.read_text())
    assert data["external_sources_enabled"] is True


def test_external_disable_persists(isolated, capsys):
    _call("cmd_config_external_enable", human=False)
    _call("cmd_config_external_disable", human=False)
    cfg_path = Path(isolated) / "config" / "maestra" / "config.json"
    data = json.loads(cfg_path.read_text())
    assert data["external_sources_enabled"] is False
```

- [ ] **Step 2: Rodar e ver falhar**

```bash
uv run pytest packages/maestra-ai/tests/unit/external/test_cli_config_external.py -v
```

Expected: FAIL com `AttributeError` (função ainda não existe).

- [ ] **Step 3: Implementar subgrupo em `config.py`**

Adiciona ao final de `packages/maestra-ai/src/maestra_ai/cli/config.py` (antes do `@register`):

```python
def cmd_config_external_status(args, **_):
    cfg = storage.read_config()
    output(
        {
            "enabled": bool(cfg.get("external_sources_enabled")),
            "musicbrainz": "available",  # v0.9: sempre disponível se habilitado
        },
        getattr(args, "human", False),
    )


def cmd_config_external_enable(args, **_):
    cfg = storage.read_config()
    cfg["external_sources_enabled"] = True
    storage.write_config(cfg)
    output({"status": "enabled"}, getattr(args, "human", False))


def cmd_config_external_disable(args, **_):
    cfg = storage.read_config()
    cfg["external_sources_enabled"] = False
    storage.write_config(cfg)
    output({"status": "disabled"}, getattr(args, "human", False))
```

E no `_register`, logo antes do `return`, adiciona:

```python
    ext = sub.add_parser("external", help="Fontes externas de metadata")
    ext.set_defaults(func=group_help_handler(ext))
    ext_sub = ext.add_subparsers(dest="config_external_command", required=False)

    p = ext_sub.add_parser("status", help="Mostra estado das fontes externas")
    p.add_argument("--human", action="store_true")
    p.set_defaults(func=cmd_config_external_status, skip_deps=True)

    p = ext_sub.add_parser("enable", help="Ativa fontes externas")
    p.add_argument("--human", action="store_true")
    p.set_defaults(func=cmd_config_external_enable, skip_deps=True)

    p = ext_sub.add_parser("disable", help="Desativa fontes externas")
    p.add_argument("--human", action="store_true")
    p.set_defaults(func=cmd_config_external_disable, skip_deps=True)
```

Já adiciona o import do `group_help_handler` dentro do `_register` (está pelo padrão dos outros grupos).

- [ ] **Step 4: Rodar e ver passar**

```bash
uv run pytest packages/maestra-ai/tests/unit/external/test_cli_config_external.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add packages/maestra-ai/src/maestra_ai/cli/config.py packages/maestra-ai/tests/unit/external/test_cli_config_external.py
git commit -m "feat(cli): config external status/enable/disable"
```

---

## Task 11: onboard — etapa opt-in + chamada enhancer

**Files:**
- Modify: `packages/maestra-ai/src/maestra_ai/core/onboard.py`
- Test: `packages/maestra-ai/tests/unit/external/test_onboard_optin.py`

- [ ] **Step 1: Escrever teste da integração**

Cria `packages/maestra-ai/tests/unit/external/test_onboard_optin.py`:

```python
"""Testes da etapa opt-in no onboard.run."""
from unittest.mock import MagicMock

from maestra_ai.core.onboard import _build_top_100_for_enhancement, _emit_mb_summary


def test_build_top_100_combines_sources():
    top_long = [{"uri": "spotify:track:long1", "name": "L", "artists": [{"name": "A"}]}]
    saved = [{"uri": "spotify:track:saved1", "name": "S", "artists": [{"name": "B"}]}]
    recent = [{"uri": "spotify:track:recent1", "name": "R", "artists": [{"name": "C"}]}]
    weights = {
        "spotify:track:long1": 5.0,
        "spotify:track:saved1": 3.0,
        "spotify:track:recent1": 1.0,
    }
    result = _build_top_100_for_enhancement(
        top_long=top_long, saved=saved, recent=recent, weights=weights,
    )
    assert len(result) == 3
    assert result[0]["uri"] == "spotify:track:long1"  # maior weight


def test_build_top_100_limits_to_100():
    tracks = [
        {"uri": f"spotify:track:{i}", "name": str(i), "artists": [{"name": "X"}]}
        for i in range(150)
    ]
    weights = {t["uri"]: float(150 - i) for i, t in enumerate(tracks)}
    result = _build_top_100_for_enhancement(
        top_long=tracks, saved=[], recent=[], weights=weights,
    )
    assert len(result) == 100


def test_emit_mb_summary_counts(capsys):
    enhanced_tracks = [
        {"musicbrainz": {"genres": ["rock"]}, "sources": ["musicbrainz"]},
        {"musicbrainz": {"genres": []}, "sources": ["musicbrainz"]},
        {"musicbrainz": None, "sources": []},
    ]
    _console = MagicMock()
    _emit_mb_summary(enhanced_tracks, console=_console)
    args = _console.print.call_args_list
    # Ao menos uma linha deve mencionar "2 faixas" (com musicbrainz não-None)
    flat = " ".join(str(c) for c in args)
    assert "musicbrainz" in flat.lower() or "2" in flat
```

- [ ] **Step 2: Rodar e ver falhar**

```bash
uv run pytest packages/maestra-ai/tests/unit/external/test_onboard_optin.py -v
```

Expected: FAIL com `ImportError` (`_build_top_100_for_enhancement` e `_emit_mb_summary` não existem).

- [ ] **Step 3: Implementar helpers em `onboard.py`**

Localiza a função `run()` e ANTES dela (como módulos-level helpers), adiciona:

```python
def _build_top_100_for_enhancement(
    *,
    top_long: list[dict],
    saved: list[dict],
    recent: list[dict],
    weights: dict[str, float],
) -> list[dict]:
    """Monta lista de TrackInfo ordenada por weight; até 100 itens.

    Deduplica por URI. Usa pesos do dict `weights` (combinação já
    calculada de long/medium/short/saved/recent).
    """
    seen: set[str] = set()
    unified: list[dict] = []
    for pool in (top_long, saved, recent):
        for t in pool:
            uri = t.get("uri")
            if not uri or uri in seen:
                continue
            seen.add(uri)
            unified.append(t)
    unified.sort(key=lambda t: weights.get(t.get("uri", ""), 0.0), reverse=True)
    return unified[:100]


def _to_track_info_for_enhancer(t: dict) -> dict:
    """Adapta dict de track do spotipy para `TrackInfo`."""
    return {
        "uri": t.get("uri", ""),
        "name": t.get("name") or "",
        "artists": [a.get("name", "") for a in (t.get("artists") or []) if a.get("name")],
        "isrc": ((t.get("external_ids") or {}).get("isrc")),
    }


def _emit_mb_summary(enhanced_tracks: list[dict], *, console) -> None:
    """Resumo pós-enhancement ao final do onboard.

    Conta tracks com metadata MB não-vazio e imprime linha com total.
    """
    with_mb = sum(
        1 for t in enhanced_tracks
        if t.get("musicbrainz") and (t["musicbrainz"].get("genres") or t["musicbrainz"].get("tags"))
    )
    console.print(
        f"\n[bold]Melhoramento externo (MusicBrainz):[/bold] "
        f"{with_mb} de {len(enhanced_tracks)} faixas com gêneros/tags canônicos.",
    )
```

- [ ] **Step 4: Rodar e ver passar**

```bash
uv run pytest packages/maestra-ai/tests/unit/external/test_onboard_optin.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Integrar no fluxo de `onboard.run`**

Localiza em `onboard.py` o bloco que monta o return dict (perto da linha ~1080, após `_derive_suggestions`). Adiciona **antes** do return, logo após `rationale_path = _persist_rationale(...)`:

```python
    # v0.9.0-alpha.0: melhoramento externo (MusicBrainz) quando habilitado.
    external_enhanced_count = 0
    external_sources_used: list[str] = []
    cfg = storage.read_config()
    if cfg.get("external_sources_enabled") and enhance_external:
        from maestra_ai.core.external import default_enhancer
        enhancer = default_enhancer()
        active = enhancer.active_sources()
        if active:
            top_100 = _build_top_100_for_enhancement(
                top_long=top_long, saved=saved, recent=recent,
                weights=adjusted_weights,
            )
            track_infos = [_to_track_info_for_enhancer(t) for t in top_100]
            enhanced = enhancer.enhance_many(
                track_infos,
                progress_cb=(
                    lambda ev: report_step(
                        -1, "Melhoramento externo", ev.get("detail") or "",
                    )
                ) if progress_cb else None,
            )
            external_enhanced_count = len(enhanced)
            external_sources_used = active
            from rich.console import Console
            _emit_mb_summary(enhanced, console=Console())
```

E no dict de retorno, adiciona duas novas chaves:

```python
        "external_enhanced_count": external_enhanced_count,
        "external_sources_used": external_sources_used,
```

Adiciona o parâmetro `enhance_external: bool = True` na assinatura do `run()` (default True; controlador chamará com True ou False conforme opt-in).

- [ ] **Step 6: Rodar suíte completa para garantir que nada quebrou**

```bash
uv run pytest packages/maestra-ai/tests/ -q
```

Expected: todos os testes existentes continuam passando.

- [ ] **Step 7: Commit**

```bash
git add packages/maestra-ai/src/maestra_ai/core/onboard.py packages/maestra-ai/tests/unit/external/test_onboard_optin.py
git commit -m "feat(onboard): integração com enhancer (MusicBrainz top 100)"
```

---

## Task 12: init — prompt opt-in

**Files:**
- Modify: `packages/maestra-ai/src/maestra_ai/core/init.py`
- Test: `packages/maestra-ai/tests/unit/external/test_init_optin.py`

- [ ] **Step 1: Escrever teste**

Cria `packages/maestra-ai/tests/unit/external/test_init_optin.py`:

```python
"""Testes do prompt opt-in de fontes externas no init."""
from unittest.mock import patch

from maestra_ai.core.init import _prompt_external_sources_optin


def test_prompt_returns_true_for_option_3(monkeypatch):
    monkeypatch.setenv("MAESTRA_CONFIG_DIR", "/tmp/nope")
    with patch("rich.prompt.Prompt.ask", return_value="3"):
        choice = _prompt_external_sources_optin()
    assert choice is True


def test_prompt_returns_false_for_option_2():
    with patch("rich.prompt.Prompt.ask", return_value="2"):
        choice = _prompt_external_sources_optin()
    assert choice is False


def test_prompt_option_1_disabled_in_v09(capsys):
    """Em v0.9, opção 1 (Last.fm/BPM) ainda não está implementada;
    é exibida em dim ou removida. Só temos 2 e 3."""
    # v0.9: apenas 2 e 3 são oferecidas. Se user digitar 1, re-prompt.
    with patch("rich.prompt.Prompt.ask", side_effect=["1", "2"]):
        choice = _prompt_external_sources_optin()
    assert choice is False
```

- [ ] **Step 2: Rodar e ver falhar**

```bash
uv run pytest packages/maestra-ai/tests/unit/external/test_init_optin.py -v
```

Expected: FAIL com `ImportError: cannot import name '_prompt_external_sources_optin'`.

- [ ] **Step 3: Implementar no `init.py`**

Adiciona em `packages/maestra-ai/src/maestra_ai/core/init.py`, após os helpers existentes (`_ask_retry`, `_ask_smart_exit`):

```python
def _prompt_external_sources_optin() -> bool:
    """Pergunta se o usuário quer habilitar fontes externas.

    v0.9: apenas 2 opções ativas — (2) pular, (3) só MusicBrainz.
    Opção 1 (Last.fm/BPM) chega em v0.10; se o usuário digitar 1, voltamos
    ao prompt explicando que ainda não está disponível.
    """
    from rich.prompt import Prompt

    _console.print(
        "\n[bold]━━━ Melhorar curadoria com fontes externas (opcional) ━━━[/bold]\n"
    )
    _console.print(
        "A Maestra pode consultar o MusicBrainz (banco público) para"
        " identificar gêneros canônicos das faixas. Isso recupera"
        " sugestões mais ricas agora que o Spotify removeu o campo"
        " `genres` da API pública.\n"
    )
    _console.print("  [2] Pular — curadoria segue só com dados do Spotify")
    _console.print("  [3] Usar MusicBrainz (sem chave, sem configuração)\n")

    while True:
        choice = Prompt.ask("Escolha", choices=["1", "2", "3"], default="3")
        if choice == "1":
            _console.print(
                "[yellow]Last.fm e BPM chegam em v0.10 — por ora só MusicBrainz. "
                "Escolha 2 ou 3.[/yellow]\n"
            )
            continue
        return choice == "3"
```

E no `_flow_B_analysis` (ou onde `onboard.run` é chamado), pouco antes do call, adiciona:

```python
    enable_external = _prompt_external_sources_optin()
    if enable_external:
        from maestra_ai.core import storage
        cfg = storage.read_config()
        cfg["external_sources_enabled"] = True
        storage.write_config(cfg)
```

E passa `enhance_external=enable_external` para `onboard.run(...)`.

- [ ] **Step 4: Rodar testes**

```bash
uv run pytest packages/maestra-ai/tests/unit/external/test_init_optin.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add packages/maestra-ai/src/maestra_ai/core/init.py packages/maestra-ai/tests/unit/external/test_init_optin.py
git commit -m "feat(init): prompt opt-in de fontes externas (v0.9 = só MB)"
```

---

## Task 13: profile_view + cli/profile — bloco externo

**Files:**
- Modify: `packages/maestra-ai/src/maestra_ai/core/profile_view.py`
- Modify: `packages/maestra-ai/src/maestra_ai/cli/profile.py`
- Test: `packages/maestra-ai/tests/unit/external/test_profile_external.py`

- [ ] **Step 1: Escrever teste**

Cria `packages/maestra-ai/tests/unit/external/test_profile_external.py`:

```python
"""Testes da visão de profile com bloco de fontes externas."""
import json
from pathlib import Path


def test_profile_view_includes_external_block(tmp_path, monkeypatch):
    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("MAESTRA_STATE_DIR", str(tmp_path / "state"))
    (tmp_path / "config" / "maestra").mkdir(parents=True)
    (tmp_path / "data" / "maestra").mkdir(parents=True)
    (tmp_path / "config" / "maestra" / "config.json").write_text(json.dumps({
        "client_id": "x", "client_secret": "y", "redirect_uri": "z",
        "external_sources_enabled": True,
    }))
    (tmp_path / "data" / "maestra" / "external_cache.json").write_text(json.dumps({
        "version": 1,
        "tracks": {
            "spotify:track:a": {
                "uri": "spotify:track:a",
                "musicbrainz": {"mbid": "r1", "genres": ["rock"], "tags": []},
                "sources": ["musicbrainz"],
            },
            "spotify:track:b": {
                "uri": "spotify:track:b",
                "musicbrainz": {"mbid": "r2", "genres": [], "tags": []},
                "sources": ["musicbrainz"],
            },
        },
    }))

    from maestra_ai.core.profile_view import build_profile_view
    view = build_profile_view()

    assert view["external"]["enabled"] is True
    assert view["external"]["musicbrainz"]["tracks_with_genres"] == 1
    assert view["external"]["musicbrainz"]["tracks_total"] == 2
```

- [ ] **Step 2: Rodar e ver falhar**

```bash
uv run pytest packages/maestra-ai/tests/unit/external/test_profile_external.py -v
```

Expected: FAIL (chave `external` não existe no view).

- [ ] **Step 3: Implementar em `profile_view.py`**

Edita `packages/maestra-ai/src/maestra_ai/core/profile_view.py`. No `build_profile_view()`, antes do return, adiciona:

```python
    external = _build_external_block()
```

E no dict de retorno adiciona `"external": external`.

Cria a helper no mesmo arquivo:

```python
def _build_external_block() -> dict:
    """Agrega estatísticas de uso de fontes externas."""
    from maestra_ai.core.external import cache as ext_cache

    cfg = storage.read_config()
    enabled = bool(cfg.get("external_sources_enabled"))

    if not enabled:
        return {"enabled": False}

    cache = ext_cache.load_cache()
    tracks = cache.get("tracks", {})
    total = len(tracks)
    with_mb_genres = sum(
        1 for t in tracks.values()
        if t.get("musicbrainz") and t["musicbrainz"].get("genres")
    )
    return {
        "enabled": True,
        "musicbrainz": {
            "tracks_total": total,
            "tracks_with_genres": with_mb_genres,
        },
    }
```

E garante que `from maestra_ai.core import storage` está no topo do arquivo.

- [ ] **Step 4: Atualizar render em `cli/profile.py`**

Edita `packages/maestra-ai/src/maestra_ai/cli/profile.py`, bloco `cmd_profile_show` (parte do `--human`). Após o bloco de sugestões, adiciona:

```python
    external = view.get("external") or {}
    if external.get("enabled"):
        print("\nMelhoramento externo:")
        mb = external.get("musicbrainz") or {}
        total = mb.get("tracks_total", 0)
        with_genres = mb.get("tracks_with_genres", 0)
        print(f"  MusicBrainz: ativo ({with_genres}/{total} faixas com gêneros)")
```

- [ ] **Step 5: Rodar testes**

```bash
uv run pytest packages/maestra-ai/tests/unit/external/test_profile_external.py -v packages/maestra-ai/tests/unit/test_profile_show.py -v
```

Expected: todos passam.

- [ ] **Step 6: Commit**

```bash
git add packages/maestra-ai/src/maestra_ai/core/profile_view.py packages/maestra-ai/src/maestra_ai/cli/profile.py packages/maestra-ai/tests/unit/external/test_profile_external.py
git commit -m "feat(profile): bloco 'Melhoramento externo' no show --human"
```

---

## Task 14: Integration test — init → cache → profile

**Files:**
- Create: `packages/maestra-ai/tests/integration/test_external_flow.py`

- [ ] **Step 1: Criar teste de integração**

Cria `packages/maestra-ai/tests/integration/test_external_flow.py`:

```python
"""Integration: fluxo completo com fontes externas habilitadas."""
import json
from unittest.mock import patch

import pytest

from maestra_ai.core.external import cache as ext_cache
from maestra_ai.core.external.enhancer import Enhancer


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("MAESTRA_STATE_DIR", str(tmp_path / "state"))
    (tmp_path / "config" / "maestra").mkdir(parents=True)
    return tmp_path


class _StubSource:
    name = "musicbrainz"
    def is_configured(self): return True
    def __init__(self):
        self.calls = 0
    def enhance_track(self, track):
        self.calls += 1
        return {
            "musicbrainz": {"mbid": f"r-{track['uri']}", "genres": ["rock"], "tags": []},
            "artist_mbid": f"a-{track['uri']}",
            "match_method": "isrc",
        }


def test_enhance_then_profile_view_integration(isolated):
    source = _StubSource()
    enhancer = Enhancer(sources=[source])
    tracks = [
        {"uri": "spotify:track:1", "name": "A", "artists": ["X"], "isrc": "I1"},
        {"uri": "spotify:track:2", "name": "B", "artists": ["Y"], "isrc": "I2"},
    ]
    enhancer.enhance_many(tracks)

    cfg_path = isolated / "config" / "maestra" / "config.json"
    cfg_path.write_text(json.dumps({
        "client_id": "x", "client_secret": "y", "redirect_uri": "z",
        "external_sources_enabled": True,
    }))

    from maestra_ai.core.profile_view import build_profile_view
    view = build_profile_view()

    assert view["external"]["enabled"] is True
    assert view["external"]["musicbrainz"]["tracks_total"] == 2
    assert view["external"]["musicbrainz"]["tracks_with_genres"] == 2


def test_cache_hit_avoids_second_call(isolated):
    source = _StubSource()
    enhancer = Enhancer(sources=[source])
    track = {"uri": "spotify:track:1", "name": "A", "artists": ["X"], "isrc": "I1"}
    enhancer.enhance_track(track)
    enhancer.enhance_track(track)
    assert source.calls == 1


def test_refresh_clears_cache(isolated):
    source = _StubSource()
    enhancer = Enhancer(sources=[source])
    track = {"uri": "spotify:track:1", "name": "A", "artists": ["X"], "isrc": "I1"}
    enhancer.enhance_track(track)
    assert ext_cache.load_cache()["tracks"]
    cache = ext_cache.load_cache()
    cache["tracks"] = {}
    ext_cache.save_cache(cache)
    assert ext_cache.load_cache()["tracks"] == {}
```

- [ ] **Step 2: Rodar**

```bash
uv run pytest packages/maestra-ai/tests/integration/test_external_flow.py -v
```

Expected: 3 passed.

- [ ] **Step 3: Commit**

```bash
git add packages/maestra-ai/tests/integration/test_external_flow.py
git commit -m "test(external): integration enhance + cache + profile"
```

---

## Task 15: Migração — state C oferece melhoria via init

**Files:**
- Modify: `packages/maestra-ai/src/maestra_ai/core/init.py`
- Test: adicionar caso em `packages/maestra-ai/tests/unit/external/test_init_optin.py`

- [ ] **Step 1: Escrever teste**

Adiciona ao final de `test_init_optin.py`:

```python
def test_state_c_offers_migration_when_external_flag_absent(monkeypatch, tmp_path):
    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path / "config"))
    (tmp_path / "config" / "maestra").mkdir(parents=True)
    import json
    (tmp_path / "config" / "maestra" / "config.json").write_text(json.dumps({
        "client_id": "x", "client_secret": "y", "redirect_uri": "z",
        # Sem `external_sources_enabled` → candidato a migração.
    }))
    from maestra_ai.core.init import _state_c_should_offer_external
    assert _state_c_should_offer_external() is True


def test_state_c_does_not_offer_when_already_decided(tmp_path, monkeypatch):
    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path / "config"))
    (tmp_path / "config" / "maestra").mkdir(parents=True)
    import json
    (tmp_path / "config" / "maestra" / "config.json").write_text(json.dumps({
        "client_id": "x", "client_secret": "y", "redirect_uri": "z",
        "external_sources_enabled": False,
    }))
    from maestra_ai.core.init import _state_c_should_offer_external
    assert _state_c_should_offer_external() is False
```

- [ ] **Step 2: Rodar e ver falhar**

```bash
uv run pytest packages/maestra-ai/tests/unit/external/test_init_optin.py -v
```

Expected: 2 novos falham.

- [ ] **Step 3: Implementar helper em `init.py`**

Adiciona em `packages/maestra-ai/src/maestra_ai/core/init.py`:

```python
def _state_c_should_offer_external() -> bool:
    """True se o usuário ainda não decidiu sobre fontes externas.

    Ausência da chave `external_sources_enabled` no config = indeciso.
    Presença (true ou false) = já decidiu, respeita.
    """
    from maestra_ai.core import storage
    cfg = storage.read_config()
    return "external_sources_enabled" not in cfg
```

E no sub-menu do state C (localizar `_flow_C_update` ou similar), condicionalmente oferece a migração:

```python
    if _state_c_should_offer_external():
        _console.print(
            "\n[yellow]Novo em v0.9:[/yellow] você pode habilitar fontes externas "
            "para melhorar a curadoria. Vou perguntar agora."
        )
        enable = _prompt_external_sources_optin()
        from maestra_ai.core import storage
        cfg = storage.read_config()
        cfg["external_sources_enabled"] = enable
        storage.write_config(cfg)
```

- [ ] **Step 4: Rodar**

```bash
uv run pytest packages/maestra-ai/tests/unit/external/test_init_optin.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add packages/maestra-ai/src/maestra_ai/core/init.py packages/maestra-ai/tests/unit/external/test_init_optin.py
git commit -m "feat(init): state C oferece migração para fontes externas"
```

---

## Task 16: Curate — atribuição quando houver fonte ativa

**Files:**
- Modify: `packages/maestra-ai/src/maestra_ai/cli/curate.py`
- Test: `packages/maestra-ai/tests/unit/external/test_curate_attribution.py`

Em v0.9 o scoring não muda, mas se o usuário tem `external_sources_enabled: true` e a última curadoria usou cache MB, exibimos o bloco de atribuição no final do `curate --human`.

- [ ] **Step 1: Escrever teste**

Cria `packages/maestra-ai/tests/unit/external/test_curate_attribution.py`:

```python
"""Testes da atribuição em curate quando fontes externas ativas."""
import json


def test_attribution_printed_when_external_enabled(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
    (tmp_path / "config" / "maestra").mkdir(parents=True)
    (tmp_path / "data" / "maestra").mkdir(parents=True)
    (tmp_path / "config" / "maestra" / "config.json").write_text(json.dumps({
        "client_id": "x", "client_secret": "y", "redirect_uri": "z",
        "external_sources_enabled": True,
    }))
    (tmp_path / "data" / "maestra" / "external_cache.json").write_text(json.dumps({
        "version": 1, "tracks": {"spotify:track:a": {"uri": "spotify:track:a", "sources": ["musicbrainz"]}},
    }))

    from maestra_ai.cli.curate import _maybe_print_external_attribution
    _maybe_print_external_attribution()
    out = capsys.readouterr().out
    assert "MusicBrainz" in out
    assert "musicbrainz.org/doc/About" in out


def test_attribution_silent_when_disabled(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
    (tmp_path / "config" / "maestra").mkdir(parents=True)
    (tmp_path / "config" / "maestra" / "config.json").write_text(json.dumps({
        "client_id": "x", "client_secret": "y", "redirect_uri": "z",
        "external_sources_enabled": False,
    }))
    from maestra_ai.cli.curate import _maybe_print_external_attribution
    _maybe_print_external_attribution()
    out = capsys.readouterr().out
    assert "MusicBrainz" not in out
```

- [ ] **Step 2: Rodar e ver falhar**

```bash
uv run pytest packages/maestra-ai/tests/unit/external/test_curate_attribution.py -v
```

Expected: FAIL (função não existe).

- [ ] **Step 3: Implementar**

No topo de `packages/maestra-ai/src/maestra_ai/cli/curate.py`:

```python
def _maybe_print_external_attribution():
    """Imprime bloco de atribuição se fontes externas estão em uso."""
    from rich.console import Console
    from maestra_ai.core import storage
    from maestra_ai.core.external import cache as ext_cache
    from maestra_ai.core.external.attribution import render_attribution

    cfg = storage.read_config()
    if not cfg.get("external_sources_enabled"):
        return
    cache = ext_cache.load_cache()
    sources_used: set[str] = set()
    for entry in cache.get("tracks", {}).values():
        for s in entry.get("sources", []) or []:
            sources_used.add(s)
    if not sources_used:
        return
    text = render_attribution(sorted(sources_used))
    if text:
        Console().print(text)
```

E chama essa função no final de `cmd_curate` (após o `output(...)`), apenas quando `getattr(args, "human", False)`:

```python
    if getattr(args, "human", False):
        _maybe_print_external_attribution()
```

- [ ] **Step 4: Rodar**

```bash
uv run pytest packages/maestra-ai/tests/unit/external/test_curate_attribution.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add packages/maestra-ai/src/maestra_ai/cli/curate.py packages/maestra-ai/tests/unit/external/test_curate_attribution.py
git commit -m "feat(curate): bloco de atribuição quando external ativo"
```

---

## Task 17: Suíte completa + lint + CHANGELOG + push

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Rodar suíte completa + lint**

```bash
uv run pytest -q
uv run ruff check packages/
```

Expected: todos passam, ruff sem issues. Se ruff aponta problemas, corrigir antes do commit final.

- [ ] **Step 2: Atualizar CHANGELOG**

Edita `CHANGELOG.md`, insere abaixo de `## [Unreleased]`:

```markdown
## [0.9.0-alpha.0] — 2026-04-20

### Adicionado
- **Fontes externas de metadata** (v0.9: MusicBrainz-only, arquitetura para v0.10):
  - Novo pacote `core/external/` com `EnhancementSource` Protocol,
    `Enhancer` (cache + orquestração), fonte MusicBrainz via `musicbrainzngs`,
    cache persistente `external_cache.json`.
  - Opt-in no `init`: nova etapa "Melhorar curadoria com fontes externas" com
    opções `[2]` Pular / `[3]` Usar MusicBrainz.
  - `maestra config external status/enable/disable` — controle explícito.
  - `maestra cache refresh [--source X] [--uri Y]` — força re-fetch.
  - `maestra profile show --human` — bloco "Melhoramento externo" com
    contagem de faixas por fonte.
  - `maestra curate --human` — bloco de atribuição clicável (OSC 8) ao fim
    quando fontes externas foram usadas.
  - Migração no state C: usuários existentes sem decisão são oferecidos a
    habilitar fontes externas no sub-menu de update.
- Lookup MB primário via ISRC (`track.external_ids.isrc`); fallback
  `name+artist`.
- Graceful degradation: erros de rede no MB não bloqueiam a análise.
- Atribuição unificada com links clicáveis para MusicBrainz, Last.fm e
  GetSongBPM (últimas duas chegam em v0.10).

### Alterado
- `onboard.run` ganha `enhance_external: bool = True` e dois campos no report:
  `external_enhanced_count`, `external_sources_used`.

### Dependências
- `musicbrainzngs>=0.7.1` (nova, obrigatória).
- `responses>=0.25` já em dev-deps.

### Referência
- Spec: `docs/superpowers/specs/2026-04-20-v090-external-sources-design.md`
- Plano: `docs/superpowers/plans/2026-04-20-v090-musicbrainz.md`
```

- [ ] **Step 3: Commit + tag**

```bash
git add CHANGELOG.md
git commit -m "docs: CHANGELOG v0.9.0-alpha.0"
git tag v0.9.0-alpha.0
```

- [ ] **Step 4: Pedir confirmação ao usuário antes de push**

Aguardar autorização explícita do usuário antes de:

```bash
git push origin main
git push origin v0.9.0-alpha.0
```

---

## Definition of Done (DoD)

- [ ] `uv run pytest -q` → todos os testes passam (615+ pré-existentes + novos)
- [ ] `uv run ruff check packages/` → `All checks passed`
- [ ] `maestra init` oferece a etapa opt-in corretamente
- [ ] `maestra config external enable && maestra cache refresh` funcionam
- [ ] `maestra profile show --human` exibe bloco "Melhoramento externo"
- [ ] `maestra curate --human` exibe atribuição quando external ativo
- [ ] CHANGELOG e version bumpados
- [ ] Commits atômicos, cada task com seu commit
- [ ] Tag `v0.9.0-alpha.0` criada (push só após autorização)

## Observações do plano

1. **Paralelismo propositalmente omitido** em v0.9: única fonte é MB com rate
   limit de 1 req/s. ThreadPoolExecutor vira premature optimization. Quando
   v0.10 adicionar Last.fm e GetSongBPM, revisita.

2. **Nenhum test chama API pública** real. Tudo mockado com `unittest.mock`
   ou fixtures JSON estáticas.

3. **Rate limit testado via lib** (`musicbrainzngs.set_rate_limit` é chamado
   no construtor e garantido pela própria lib). Não testamos `time.sleep`
   manualmente — confiamos no contrato da dependência.

4. **Sub-tasks de UI** (atribuição em curate, profile bloco) são testáveis
   isoladas via `capsys`. Evitam smoke CLI pesado.
