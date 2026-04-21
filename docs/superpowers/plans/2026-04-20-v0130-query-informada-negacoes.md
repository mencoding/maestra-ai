# v0.13.0 — Query informada e negações semânticas — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fechar os três gaps do issue #8 — parser unificado de contexto, `_track_tags` real consumindo cache external, e `_build_informed_query` real derivando query do cruzamento parsed × taste.

**Architecture:** Dois módulos puros novos (`context_parser.py`, `tag_filter.py`) consumidos por extensões mínimas em `ContextState`, `Curator` e `scoring`. Parser frozen e memoizado; hard filter com fallback adaptativo; scoring composto ganha um componente `anti_tag_penalty` ativo só em modo degraded.

**Tech Stack:** Python 3.11+, dataclasses (frozen), pytest, unicodedata (NFKC + casefold), logging.

**Spec:** `docs/superpowers/specs/2026-04-20-v0130-query-informada-negacoes-design.md`.

**Base branch:** `feat/issue-8-v0130-query-informada-negacoes` a partir de `main` pós-merge dos PRs #11, #12 e #15.

---

## Task 1: Scaffold do módulo `context_parser.py`

**Files:**
- Create: `packages/maestra-ai/src/maestra_ai/core/context_parser.py`
- Create: `packages/maestra-ai/tests/unit/test_context_parser.py`

- [ ] **Step 1: Criar teste que importa ParsedContext e parse vazio**

```python
# packages/maestra-ai/tests/unit/test_context_parser.py
"""Testes do parser de contexto (issue #8, v0.13)."""
from __future__ import annotations

import dataclasses

import pytest


def test_parse_retorna_parsed_context_com_text_vazio_quando_input_vazio():
    from maestra_ai.core.context_parser import ParsedContext, parse
    p = parse("")
    assert isinstance(p, ParsedContext)
    assert p.text == ""
    assert p.positive == ()
    assert p.negative == ()
    assert p.artists_hint == ()
    assert p.bpm is None


def test_parsed_context_e_frozen():
    from maestra_ai.core.context_parser import ParsedContext
    p = ParsedContext(text="x")
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.text = "mudou"  # type: ignore[misc]
```

- [ ] **Step 2: Rodar teste e confirmar que falha com ModuleNotFoundError**

```bash
uv run pytest packages/maestra-ai/tests/unit/test_context_parser.py -v
```

Expected: ambos falham com `ModuleNotFoundError: No module named 'maestra_ai.core.context_parser'`.

- [ ] **Step 3: Criar o módulo com ParsedContext e parse mínimo**

```python
# packages/maestra-ai/src/maestra_ai/core/context_parser.py
"""Parser puro de contexto musical livre para ParsedContext estruturada.

Módulo sem dependências do core — só stdlib. Consumido por ContextState
(memoização) e por Curator (_build_informed_query, _apply_negative_filter).

Issue #8, v0.13.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ParsedContext:
    """Estrutura derivada do texto cru do contexto.

    - text: texto original preservado (sem normalização) para log/debug.
    - positive: termos após marker positivo ("tipo X", "como Y").
    - negative: termos após marker negativo ("evitar X", "sem Y").
    - artists_hint: nomes próprios capitalizados após marker positivo.
    - bpm: objeto {min, max} repassado do ContextState.
    """
    text: str
    positive: tuple[str, ...] = ()
    negative: tuple[str, ...] = ()
    artists_hint: tuple[str, ...] = ()
    bpm: dict | None = None


def parse(text: str, bpm: dict | None = None) -> ParsedContext:
    """Extrai intenção estruturada de texto livre.

    Puro, idempotente, determinístico. Nenhum I/O, nenhum logging.
    """
    return ParsedContext(text=text or "", bpm=bpm)
```

- [ ] **Step 4: Rodar teste e confirmar que passa**

```bash
uv run pytest packages/maestra-ai/tests/unit/test_context_parser.py -v
```

Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add packages/maestra-ai/src/maestra_ai/core/context_parser.py \
        packages/maestra-ai/tests/unit/test_context_parser.py
git commit -m "feat(context_parser): scaffold ParsedContext + parse mínimo

Issue #8, v0.13. Base pros passos seguintes do parser unificado."
```

---

## Task 2: Parse de negações

**Files:**
- Modify: `packages/maestra-ai/src/maestra_ai/core/context_parser.py` (adiciona NEGATIVE_MARKERS + lógica)
- Modify: `packages/maestra-ai/tests/unit/test_context_parser.py`

- [ ] **Step 1: Escrever testes de negações**

```python
# Adicionar ao fim de test_context_parser.py
class TestNegativos:
    def test_extrai_um_negativo_apos_evitar(self):
        from maestra_ai.core.context_parser import parse
        p = parse("metal evitar ambient")
        assert "ambient" in p.negative

    def test_extrai_um_negativo_apos_sem(self):
        from maestra_ai.core.context_parser import parse
        p = parse("rock sem ballads")
        assert "ballads" in p.negative

    def test_extrai_um_negativo_apos_nao(self):
        from maestra_ai.core.context_parser import parse
        p = parse("música não acústica")
        assert "acústica" in p.negative

    def test_extrai_multiplos_negativos_em_virgula(self):
        from maestra_ai.core.context_parser import parse
        p = parse("foco sem distração, evitar vocal")
        assert "distração" in p.negative
        assert "vocal" in p.negative

    def test_nenhuma_negacao_retorna_tupla_vazia(self):
        from maestra_ai.core.context_parser import parse
        p = parse("metal tribal denso")
        assert p.negative == ()
```

- [ ] **Step 2: Rodar e confirmar que falham (negative sempre vazio)**

```bash
uv run pytest packages/maestra-ai/tests/unit/test_context_parser.py::TestNegativos -v
```

Expected: 4 fails (exceto `test_nenhuma_negacao_retorna_tupla_vazia`).

- [ ] **Step 3: Implementar NEGATIVE_MARKERS + extração**

Substituir `context_parser.py` com:

```python
"""Parser puro de contexto musical livre para ParsedContext estruturada.

Módulo sem dependências do core — só stdlib. Consumido por ContextState
(memoização) e por Curator (_build_informed_query, _apply_negative_filter).

Issue #8, v0.13.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


NEGATIVE_MARKERS: tuple[str, ...] = ("evitar ", "sem ", "não ", "nao ")


@dataclass(frozen=True)
class ParsedContext:
    text: str
    positive: tuple[str, ...] = ()
    negative: tuple[str, ...] = ()
    artists_hint: tuple[str, ...] = ()
    bpm: dict | None = None


def _split_clauses(text: str) -> list[str]:
    """Quebra por vírgula, ponto, ponto-e-vírgula. Retorna fragmentos limpos."""
    return [c.strip() for c in re.split(r"[,.;]", text) if c.strip()]


def _extract_after_marker(clause: str, markers: tuple[str, ...]) -> str | None:
    """Se clause começa com um marker, retorna o resto. Caso contrário, None."""
    for marker in markers:
        idx = clause.find(marker)
        if idx >= 0:
            return clause[idx + len(marker):].strip()
    return None


def parse(text: str, bpm: dict | None = None) -> ParsedContext:
    """Extrai intenção estruturada de texto livre.

    Puro, idempotente, determinístico. Nenhum I/O, nenhum logging.
    """
    if not text:
        return ParsedContext(text="", bpm=bpm)

    negative: list[str] = []
    for clause in _split_clauses(text):
        rest = _extract_after_marker(clause, NEGATIVE_MARKERS)
        if rest:
            # Pega o primeiro termo (primeira "palavra-chave" do rest)
            first_token = rest.split()[0] if rest.split() else ""
            if first_token:
                negative.append(first_token)

    return ParsedContext(
        text=text,
        negative=tuple(negative),
        bpm=bpm,
    )
```

- [ ] **Step 4: Rodar e confirmar que passam**

```bash
uv run pytest packages/maestra-ai/tests/unit/test_context_parser.py -v
```

Expected: `7 passed`.

- [ ] **Step 5: Commit**

```bash
git add packages/maestra-ai/src/maestra_ai/core/context_parser.py \
        packages/maestra-ai/tests/unit/test_context_parser.py
git commit -m "feat(context_parser): extrai negações após evitar/sem/não

Issue #8. Parser identifica primeiro token após marker negativo em cada
cláusula (separadas por vírgula/ponto)."
```

---

## Task 3: Parse de positivos e artists_hint

**Files:**
- Modify: `packages/maestra-ai/src/maestra_ai/core/context_parser.py`
- Modify: `packages/maestra-ai/tests/unit/test_context_parser.py`

- [ ] **Step 1: Escrever testes**

```python
class TestPositivos:
    def test_extrai_termo_apos_tipo(self):
        from maestra_ai.core.context_parser import parse
        p = parse("tipo lo-fi")
        assert "lo-fi" in p.positive

    def test_extrai_termo_apos_como(self):
        from maestra_ai.core.context_parser import parse
        p = parse("algo como jazz")
        assert "jazz" in p.positive

    def test_extrai_termo_apos_parecido_com(self):
        from maestra_ai.core.context_parser import parse
        p = parse("parecido com bossa")
        assert "bossa" in p.positive

    def test_positivo_e_negativo_coexistem(self):
        from maestra_ai.core.context_parser import parse
        p = parse("tipo rock, sem ballads")
        assert "rock" in p.positive
        assert "ballads" in p.negative


class TestArtistsHint:
    def test_captura_nome_proprio_apos_marker_positivo(self):
        from maestra_ai.core.context_parser import parse
        p = parse("tipo The HU")
        assert "The HU" in p.artists_hint

    def test_captura_multi_palavra_capitalizada(self):
        from maestra_ai.core.context_parser import parse
        p = parse("como Dance With The Dead")
        assert "Dance With The Dead" in p.artists_hint

    def test_palavra_minuscula_nao_vira_artist(self):
        from maestra_ai.core.context_parser import parse
        p = parse("tipo rock")
        assert p.artists_hint == ()
```

- [ ] **Step 2: Rodar e confirmar que falham**

```bash
uv run pytest packages/maestra-ai/tests/unit/test_context_parser.py::TestPositivos \
                packages/maestra-ai/tests/unit/test_context_parser.py::TestArtistsHint -v
```

Expected: 7 fails.

- [ ] **Step 3: Adicionar POSITIVE_MARKERS e extração**

Modificar `context_parser.py`, adicionar antes de `parse`:

```python
POSITIVE_MARKERS: tuple[str, ...] = (
    "algo tipo ",
    "parecido com ",
    "tipo ",
    "como ",
    "mais ",
)


def _extract_artists(original_clause: str, term: str) -> list[str]:
    """Se o term extraído começa com maiúscula(s), considera artista.

    Recebe o original_clause (não normalizado) e o term já extraído.
    Procura a sequência capitalizada começando na posição do term.
    """
    # Regex: sequência de palavras capitalizadas (cada uma começa maiúscula)
    pattern = r"\b([A-Z][A-Za-z]*(?:\s+[A-Z][A-Za-z]*)*)\b"
    matches = re.findall(pattern, original_clause)
    return [m for m in matches if len(m) > 1]
```

E modificar a função `parse` para:

```python
def parse(text: str, bpm: dict | None = None) -> ParsedContext:
    """Extrai intenção estruturada de texto livre.

    Puro, idempotente, determinístico. Nenhum I/O, nenhum logging.
    """
    if not text:
        return ParsedContext(text="", bpm=bpm)

    negative: list[str] = []
    positive: list[str] = []
    artists_hint: list[str] = []

    for clause in _split_clauses(text):
        neg_rest = _extract_after_marker(clause, NEGATIVE_MARKERS)
        pos_rest = _extract_after_marker(clause, POSITIVE_MARKERS)

        # Negativos têm prioridade sobre positivos em caso de conflito
        if neg_rest is not None:
            first = neg_rest.split()[0] if neg_rest.split() else ""
            if first:
                negative.append(first)
            continue  # não processa positivo nesta cláusula

        if pos_rest is not None:
            # Para artists_hint: coleta palavras capitalizadas da cláusula
            caps = _extract_artists(clause, pos_rest)
            artists_hint.extend(caps)
            # Para positive: primeiro token do rest (pode ser "rock", "lo-fi", etc.)
            first = pos_rest.split()[0] if pos_rest.split() else ""
            if first and first[0].islower():
                positive.append(first)

    return ParsedContext(
        text=text,
        positive=tuple(positive),
        negative=tuple(negative),
        artists_hint=tuple(artists_hint),
        bpm=bpm,
    )
```

- [ ] **Step 4: Rodar e confirmar que passam**

```bash
uv run pytest packages/maestra-ai/tests/unit/test_context_parser.py -v
```

Expected: `14 passed`.

- [ ] **Step 5: Commit**

```bash
git add packages/maestra-ai/src/maestra_ai/core/context_parser.py \
        packages/maestra-ai/tests/unit/test_context_parser.py
git commit -m "feat(context_parser): positivos + artists_hint

Issue #8. Palavras minúsculas após marker positivo viram positive;
sequências capitalizadas viram artists_hint. Negativos têm prioridade
sobre positivos em caso de conflito na mesma cláusula."
```

---

## Task 4: Normalização unicode + fold

**Files:**
- Modify: `packages/maestra-ai/src/maestra_ai/core/context_parser.py`
- Modify: `packages/maestra-ai/tests/unit/test_context_parser.py`

- [ ] **Step 1: Escrever testes de normalização**

```python
class TestNormalizacao:
    def test_nao_e_nao_sao_equivalentes(self):
        from maestra_ai.core.context_parser import parse
        p1 = parse("não acústico")
        p2 = parse("nao acustico")
        # Ambos devem pegar o negativo
        assert len(p1.negative) == 1
        assert len(p2.negative) == 1

    def test_maiusculas_nao_afetam_marker(self):
        from maestra_ai.core.context_parser import parse
        p = parse("EVITAR jazz")
        assert "jazz" in p.negative

    def test_acentos_preservados_no_term_extraido(self):
        from maestra_ai.core.context_parser import parse
        p = parse("sem distração")
        # O term pode estar normalizado ou preservado — o importante é
        # que o match funcionou e o term é recuperável
        assert len(p.negative) == 1
```

- [ ] **Step 2: Rodar e confirmar falhas**

Expected: `test_maiusculas_nao_afetam_marker` falha (marker só matcha lowercase).

- [ ] **Step 3: Adicionar normalização NFKC + casefold antes do match**

Modificar `_extract_after_marker` e `_split_clauses` pra usar texto normalizado no matching mas preservar original:

```python
import unicodedata

def _normalize_for_match(text: str) -> str:
    """NFKC + casefold pra match determinístico, invariante a acento/case."""
    return unicodedata.normalize("NFKC", text).casefold()
```

Refatorar `parse` pra processar clausula normalizada com markers normalizados:

```python
def parse(text: str, bpm: dict | None = None) -> ParsedContext:
    if not text:
        return ParsedContext(text="", bpm=bpm)

    # Markers normalizados (constantes computadas uma vez, mas aqui por clareza)
    neg_markers_norm = tuple(_normalize_for_match(m) for m in NEGATIVE_MARKERS)
    pos_markers_norm = tuple(_normalize_for_match(m) for m in POSITIVE_MARKERS)

    negative: list[str] = []
    positive: list[str] = []
    artists_hint: list[str] = []

    for clause in _split_clauses(text):
        clause_norm = _normalize_for_match(clause)

        neg_rest_norm = _extract_after_marker(clause_norm, neg_markers_norm)
        pos_rest_norm = _extract_after_marker(clause_norm, pos_markers_norm)

        if neg_rest_norm is not None:
            first = neg_rest_norm.split()[0] if neg_rest_norm.split() else ""
            if first:
                negative.append(first)
            continue

        if pos_rest_norm is not None:
            caps = _extract_artists(clause, pos_rest_norm)
            artists_hint.extend(caps)
            first = pos_rest_norm.split()[0] if pos_rest_norm.split() else ""
            if first and first[0].islower():
                positive.append(first)

    return ParsedContext(
        text=text,
        positive=tuple(positive),
        negative=tuple(negative),
        artists_hint=tuple(artists_hint),
        bpm=bpm,
    )
```

- [ ] **Step 4: Rodar e confirmar que passam**

```bash
uv run pytest packages/maestra-ai/tests/unit/test_context_parser.py -v
```

Expected: todos passam.

- [ ] **Step 5: Commit**

```bash
git add packages/maestra-ai/src/maestra_ai/core/context_parser.py \
        packages/maestra-ai/tests/unit/test_context_parser.py
git commit -m "feat(context_parser): normalização NFKC + casefold no matching

Issue #8. \"EVITAR\", \"evitar\" e \"Evitar\" viram mesmo marker. \"não\"
e \"nao\" idem. Texto original é preservado em ParsedContext.text."
```

---

## Task 4.5: Fix BpmRange + artist leak (correção inline pós-review)

> **Nota:** Esta task não estava no plano original. Foi executada inline após cumulative
> quality review das Tasks 1–4. Commit: `4676df6`.

**Problema 1 — hashability:** `bpm: dict | None` em `ParsedContext(frozen=True)` quebra
hashability (dict é mutável e não hashável). Qualquer tentativa de usar o `ParsedContext`
como chave de cache falharia.

**Fix:** Novo `BpmRange` frozen dataclass com campos `min: int | None`, `max: int | None`
e classmethod `from_any(BpmRange | dict | None) -> BpmRange | None`. Campo `ParsedContext.bpm`
passa a ser `BpmRange | None`. `parse()` aceita dict para ergonomia dos callers existentes
(converte via `from_any`). Camada de persistência em disco inalterada.

**Problema 2 — artist leak:** `parse("tipo The HU")` colocava `"the"` (casefold do primeiro
token) em `positive`. O matching usava o texto normalizado para decidir positive vs artist.

**Fix:** `_extract_after_marker` refatorado para `_extract_after_marker_pair`, que devolve
`(rest_norm, rest_original)`. A decisão positive-vs-artist usa o case ORIGINAL do primeiro
token — só vai para `positive` se começar minúsculo no texto cru.

**Arquivos alterados:**
- `packages/maestra-ai/src/maestra_ai/core/context_parser.py`
- `packages/maestra-ai/tests/unit/test_context_parser.py` (64 linhas de testes adicionados)

- [x] **Executado** — ver commit `4676df6`

---

## Task 5: Scaffold e implementação de `tag_filter.py`

**Files:**
- Create: `packages/maestra-ai/src/maestra_ai/core/external/tag_filter.py`
- Create: `packages/maestra-ai/tests/unit/external/test_tag_filter.py`

- [ ] **Step 1: Escrever testes**

```python
# packages/maestra-ai/tests/unit/external/test_tag_filter.py
"""Testes do filtro de tags Last.fm (issue #8)."""
from __future__ import annotations


def test_remove_tag_de_decada():
    from maestra_ai.core.external.tag_filter import filter_lastfm_tags
    raw = [{"name": "2010s", "count": 100}, {"name": "folk metal", "count": 50}]
    assert filter_lastfm_tags(raw) == {"folk metal"}


def test_remove_tag_de_pais():
    from maestra_ai.core.external.tag_filter import filter_lastfm_tags
    raw = [{"name": "brazilian", "count": 200}, {"name": "mpb", "count": 90}]
    assert filter_lastfm_tags(raw) == {"mpb"}


def test_remove_tag_avaliativa():
    from maestra_ai.core.external.tag_filter import filter_lastfm_tags
    raw = [{"name": "awesome", "count": 500}, {"name": "shoegaze", "count": 100}]
    assert filter_lastfm_tags(raw) == {"shoegaze"}


def test_top_n_corta_por_popularidade():
    from maestra_ai.core.external.tag_filter import filter_lastfm_tags
    raw = [
        {"name": "tag1", "count": 100},
        {"name": "tag2", "count": 90},
        {"name": "tag3", "count": 80},
        {"name": "tag4", "count": 70},
    ]
    assert filter_lastfm_tags(raw, top_n=2) == {"tag1", "tag2"}


def test_normaliza_case():
    from maestra_ai.core.external.tag_filter import filter_lastfm_tags
    raw = [{"name": "Folk Metal", "count": 50}, {"name": "folk metal", "count": 40}]
    result = filter_lastfm_tags(raw)
    # Depois da normalização, os dois viram "folk metal" e viram um único set
    assert result == {"folk metal"}


def test_input_vazio():
    from maestra_ai.core.external.tag_filter import filter_lastfm_tags
    assert filter_lastfm_tags([]) == set()


def test_item_sem_count_trata_como_zero():
    from maestra_ai.core.external.tag_filter import filter_lastfm_tags
    raw = [{"name": "shoegaze"}]  # sem count
    assert filter_lastfm_tags(raw) == {"shoegaze"}
```

- [ ] **Step 2: Rodar e confirmar falhas**

```bash
uv run pytest packages/maestra-ai/tests/unit/external/test_tag_filter.py -v
```

Expected: 7 fails (ModuleNotFoundError).

- [ ] **Step 3: Implementar tag_filter.py**

```python
# packages/maestra-ai/src/maestra_ai/core/external/tag_filter.py
"""Filtro de tags Last.fm para remover ruído (meta-tags, avaliativos).

Complemento puro do enhancer. Input: lista bruta de dicts do pylast
(cada item com keys `name` e `count`). Output: set de tags normalizadas,
filtradas por relevância.

Issue #8, v0.13.
"""
from __future__ import annotations


META_TAGS: frozenset[str] = frozenset({
    # Décadas
    "1950s", "1960s", "1970s", "1980s", "1990s", "2000s", "2010s", "2020s",
    # Países / nacionalidade
    "american", "british", "french", "german", "japanese", "brazilian",
    "italian", "spanish", "swedish", "norwegian", "canadian", "australian",
    "irish", "finnish", "dutch", "polish", "russian", "chinese", "korean",
    # Avaliativos / vazios
    "awesome", "favorite", "favourite", "good", "great", "amazing",
    "best", "love", "loved", "cool", "nice", "music", "songs", "song",
    "seen live",
})


def filter_lastfm_tags(raw: list[dict], *, top_n: int = 10) -> set[str]:
    """Retorna set de tags significativas (normalizadas, sem meta-tags).

    - `raw`: lista de dicts com `name` (obrigatório) e `count` (opcional, default 0).
    - `top_n`: corta pelo top `top_n` ordenado por `count` desc depois do filter.
    """
    if not raw:
        return set()

    # Normaliza (lowercase + strip) e filtra meta-tags
    normalized = []
    for item in raw:
        name = (item.get("name") or "").strip().lower()
        if not name or name in META_TAGS:
            continue
        count = item.get("count") or 0
        normalized.append((name, count))

    # Ordena por count desc, pega top_n, deduplica pelo set
    normalized.sort(key=lambda x: x[1], reverse=True)
    top = normalized[:top_n]
    return {name for name, _ in top}
```

- [ ] **Step 4: Rodar e confirmar que passam**

```bash
uv run pytest packages/maestra-ai/tests/unit/external/test_tag_filter.py -v
```

Expected: `7 passed`.

- [ ] **Step 5: Commit**

```bash
git add packages/maestra-ai/src/maestra_ai/core/external/tag_filter.py \
        packages/maestra-ai/tests/unit/external/test_tag_filter.py
git commit -m "feat(tag_filter): filtro de meta-tags Last.fm

Issue #8. Remove décadas, países e adjetivos avaliativos; normaliza
case; corta top_n por popularidade. Base pra _track_tags real."
```

---

## Task 6: `ContextState.parsed()` com memoização

**Files:**
- Modify: `packages/maestra-ai/src/maestra_ai/core/context.py`
- Modify: `packages/maestra-ai/tests/unit/test_context.py`

- [ ] **Step 1: Ler o arquivo atual de context.py pra localizar a classe ContextState**

```bash
grep -n "class ContextState\|def set\|def show" packages/maestra-ai/src/maestra_ai/core/context.py
```

- [ ] **Step 2: Escrever testes em test_context.py**

Adicionar ao fim do arquivo:

```python
class TestParsed:
    def test_parsed_retorna_none_quando_sem_contexto(self, tmp_path):
        from maestra_ai.core.context import ContextState
        state = ContextState(tmp_path / "ctx.json")
        assert state.parsed() is None

    def test_parsed_retorna_parsed_context_apos_set(self, tmp_path):
        from maestra_ai.core.context import ContextState
        from maestra_ai.core.context_parser import ParsedContext
        state = ContextState(tmp_path / "ctx.json")
        state.set("metal tribal evitar ambient")
        p = state.parsed()
        assert isinstance(p, ParsedContext)
        assert "ambient" in p.negative

    def test_parsed_memoiza_entre_chamadas(self, tmp_path):
        from maestra_ai.core.context import ContextState
        state = ContextState(tmp_path / "ctx.json")
        state.set("foco")
        p1 = state.parsed()
        p2 = state.parsed()
        assert p1 is p2  # identidade preservada por memoização

    def test_parsed_invalida_apos_novo_set(self, tmp_path):
        from maestra_ai.core.context import ContextState
        state = ContextState(tmp_path / "ctx.json")
        state.set("foco")
        p1 = state.parsed()
        state.set("energia")
        p2 = state.parsed()
        assert p1 is not p2
        assert p2.text == "energia"

    def test_parsed_repass_bpm_do_context(self, tmp_path):
        from maestra_ai.core.context import ContextState
        from maestra_ai.core.context_parser import BpmRange  # T4.5: bpm é BpmRange, não dict
        state = ContextState(tmp_path / "ctx.json")
        state.set("foco", bpm={"min": 60, "max": 90})
        p = state.parsed()
        assert p.bpm == BpmRange(min=60, max=90)
```

- [ ] **Step 3: Rodar e confirmar falhas**

```bash
uv run pytest packages/maestra-ai/tests/unit/test_context.py::TestParsed -v
```

Expected: 5 fails (`parsed` não existe).

- [ ] **Step 4: Implementar `parsed()` em ContextState**

Editar `context.py`, adicionar método na classe:

```python
# No topo do arquivo, após imports existentes
from maestra_ai.core.context_parser import ParsedContext, parse as _parse_context

# Dentro da classe ContextState, adicionar:
def parsed(self) -> ParsedContext | None:
    """Retorna ParsedContext do estado atual, memoizado até mudar o text.

    None se não há contexto ativo (show() retorna None, ou TTL expirou).
    """
    data = self.show()
    if not data:
        return None
    ctx = data.get("context") or {}
    text = ctx.get("text") or ""
    bpm = ctx.get("bpm")

    # Cache por text cru — se text muda, reparseia; se não, devolve o memo
    cache = getattr(self, "_parsed_cache", None)
    if cache is not None and cache[0] == text and cache[1].bpm == bpm:
        return cache[1]
    parsed = _parse_context(text, bpm=bpm)
    self._parsed_cache = (text, parsed)
    return parsed
```

Garantir que `set()` invalida o cache. Se `set()` já é um método, adicionar no início:

```python
def set(self, ...):
    self._parsed_cache = None
    # ... resto da lógica existente
```

- [ ] **Step 5: Rodar todos os testes de context e confirmar verde**

```bash
uv run pytest packages/maestra-ai/tests/unit/test_context.py -v
```

Expected: todos passam (novos + existentes).

- [ ] **Step 6: Commit**

```bash
git add packages/maestra-ai/src/maestra_ai/core/context.py \
        packages/maestra-ai/tests/unit/test_context.py
git commit -m "feat(context): ContextState.parsed() com memoização por text

Issue #8. Cache invalidado automaticamente em set(). Identidade
preservada entre chamadas idempotentes. Chave = text + bpm."
```

---

## Task 7: `_track_tags` real consumindo cache external

**Files:**
- Modify: `packages/maestra-ai/src/maestra_ai/core/curator.py` (método `_track_tags`)
- Modify: `packages/maestra-ai/tests/unit/test_curator.py`

- [ ] **Step 1: Escrever testes**

Adicionar em test_curator.py:

```python
class TestTrackTags:
    def test_track_sem_entrada_no_cache_retorna_vazio(self, curator):
        from maestra_ai.core.curator import Curator
        track = {"uri": "spotify:track:nao_cacheado", "artist": "X"}
        assert curator._track_tags(track) == set()

    def test_track_com_tags_mb_retorna_as_tags(self, curator, monkeypatch):
        from maestra_ai.core.external import cache as cache_mod
        monkeypatch.setattr(cache_mod, "get_track", lambda uri: {
            "musicbrainz": {"tags": ["folk metal", "viking metal"]},
        })
        track = {"uri": "spotify:track:x", "artist": "A"}
        tags = curator._track_tags(track)
        assert "folk metal" in tags
        assert "viking metal" in tags

    def test_track_com_tags_lf_filtradas(self, curator, monkeypatch):
        from maestra_ai.core.external import cache as cache_mod
        monkeypatch.setattr(cache_mod, "get_track", lambda uri: {
            "lastfm": {"top_tags": [
                {"name": "2010s", "count": 100},    # meta, descarta
                {"name": "shoegaze", "count": 50},  # mantém
            ]},
        })
        track = {"uri": "spotify:track:x", "artist": "A"}
        tags = curator._track_tags(track)
        assert "shoegaze" in tags
        assert "2010s" not in tags

    def test_merge_mb_e_lf(self, curator, monkeypatch):
        from maestra_ai.core.external import cache as cache_mod
        monkeypatch.setattr(cache_mod, "get_track", lambda uri: {
            "musicbrainz": {"tags": ["folk metal"]},
            "lastfm": {"top_tags": [{"name": "viking", "count": 50}]},
        })
        track = {"uri": "spotify:track:x", "artist": "A"}
        tags = curator._track_tags(track)
        assert "folk metal" in tags
        assert "viking" in tags
```

- [ ] **Step 2: Rodar e confirmar falhas**

```bash
uv run pytest packages/maestra-ai/tests/unit/test_curator.py::TestTrackTags -v
```

Expected: 3 fails (exceto `test_track_sem_entrada_no_cache_retorna_vazio` que já passa com stub vazio).

- [ ] **Step 3: Implementar `_track_tags` real**

Editar `core/curator.py`, substituir o método `_track_tags` (linha ~177) por:

```python
def _track_tags(self, track: dict) -> set[str]:
    """Tags do artista/track via cache external.

    Merge MB (canônico) + LF (filtrado via tag_filter). Retorna set vazio
    quando o cache não tem entrada pro URI ou nenhuma source populou.
    """
    from maestra_ai.core.external import cache as cache_mod
    from maestra_ai.core.external.tag_filter import filter_lastfm_tags

    cached = cache_mod.get_track(track.get("uri", ""))
    if not cached:
        return set()

    tags: set[str] = set()

    # MusicBrainz: tags já canônicas, union direto
    mb = cached.get("musicbrainz") or {}
    mb_tags = mb.get("tags") or []
    tags.update(t.lower() for t in mb_tags if t)

    # Last.fm: raw precisa passar pelo filtro
    lf = cached.get("lastfm") or {}
    lf_raw = lf.get("top_tags") or []
    tags.update(filter_lastfm_tags(lf_raw))

    return tags
```

- [ ] **Step 4: Rodar e confirmar verde**

```bash
uv run pytest packages/maestra-ai/tests/unit/test_curator.py -v
```

Expected: todos passam.

- [ ] **Step 5: Commit**

```bash
git add packages/maestra-ai/src/maestra_ai/core/curator.py \
        packages/maestra-ai/tests/unit/test_curator.py
git commit -m "feat(curator): _track_tags consome cache external (MB + LF)

Issue #8. Encerra stub de v0.10.0-alpha.1. MB canônico, LF filtrado
por tag_filter. Desbloqueia tag_similarity no scoring composto."
```

---

## Task 8: `_apply_negative_filter` + fallback adaptativo

**Files:**
- Modify: `packages/maestra-ai/src/maestra_ai/core/curator.py`
- Modify: `packages/maestra-ai/tests/unit/test_curator.py`

- [ ] **Step 1: Escrever testes**

Adicionar em test_curator.py:

```python
class TestApplyNegativeFilter:
    def _ctx(self, neg):
        from maestra_ai.core.context_parser import ParsedContext
        return ParsedContext(text="dummy", negative=tuple(neg))

    def test_sem_negacoes_no_op(self, curator):
        candidates = [{"uri": f"spotify:track:{i}", "artist": "A"} for i in range(15)]
        result, degraded = curator._apply_negative_filter(candidates, self._ctx([]))
        assert result == candidates
        assert degraded is False

    def test_hard_filter_quando_acima_de_min_candidates(self, curator, monkeypatch):
        from maestra_ai.core.external import cache as cache_mod
        def fake_get(uri):
            return {"musicbrainz": {"tags": ["ambient"]}} if uri.endswith("1") else {"musicbrainz": {"tags": ["rock"]}}
        monkeypatch.setattr(cache_mod, "get_track", fake_get)

        candidates = [{"uri": f"spotify:track:{i}", "artist": "A"} for i in range(20)]
        # Apenas candidate ...1 tem ambient; outros têm rock. 1 remove → 19 sobram > 10
        result, degraded = curator._apply_negative_filter(candidates, self._ctx(["ambient"]))
        assert len(result) == 19
        assert degraded is False

    def test_degrada_quando_filtro_esvazia_abaixo_de_min(self, curator, monkeypatch):
        from maestra_ai.core.external import cache as cache_mod
        # Todos os candidatos têm "ambient"
        monkeypatch.setattr(cache_mod, "get_track", lambda uri: {"musicbrainz": {"tags": ["ambient"]}})

        candidates = [{"uri": f"spotify:track:{i}", "artist": "A"} for i in range(12)]
        result, degraded = curator._apply_negative_filter(candidates, self._ctx(["ambient"]))
        assert result == candidates  # originais preservados
        assert degraded is True

    def test_fronteira_exatamente_min_candidates_e_sucesso(self, curator, monkeypatch):
        from maestra_ai.core.external import cache as cache_mod
        def fake_get(uri):
            # candidates 0..9 sem ambient; 10..14 com ambient
            idx = int(uri.split(":")[-1])
            return {"musicbrainz": {"tags": ["rock"] if idx < 10 else ["ambient"]}}
        monkeypatch.setattr(cache_mod, "get_track", fake_get)

        candidates = [{"uri": f"spotify:track:{i}", "artist": "A"} for i in range(15)]
        # Após filter: 10 sobram (exatamente MIN_CANDIDATES=10)
        result, degraded = curator._apply_negative_filter(candidates, self._ctx(["ambient"]))
        assert len(result) == 10
        assert degraded is False  # >= MIN_CANDIDATES aceita
```

- [ ] **Step 2: Rodar e confirmar falhas**

Expected: 4 fails (método não existe).

- [ ] **Step 3: Implementar `_apply_negative_filter`**

Editar `core/curator.py`, adicionar como método da classe `Curator`:

```python
def _apply_negative_filter(
    self,
    candidates: list[dict],
    parsed,  # ParsedContext — tipagem leve pra evitar import circular
) -> tuple[list[dict], bool]:
    """Hard filter removendo candidatos com tag em parsed.negative.

    Se len(filtered) < MIN_CANDIDATES, retorna originais com degraded=True.
    Caller usa degraded pra ativar anti_tag_penalty no scoring.
    """
    import logging
    logger = logging.getLogger(__name__)

    if not parsed.negative:
        return candidates, False

    negative_set = set(parsed.negative)
    filtered = [
        c for c in candidates
        if not (self._track_tags(c) & negative_set)
    ]

    if len(filtered) >= MIN_CANDIDATES:
        return filtered, False

    logger.warning(
        "hard filter on %s would leave %d candidates (< %d); "
        "degrading to soft penalty",
        sorted(negative_set), len(filtered), MIN_CANDIDATES,
    )
    return candidates, True
```

- [ ] **Step 4: Rodar e confirmar verde**

```bash
uv run pytest packages/maestra-ai/tests/unit/test_curator.py::TestApplyNegativeFilter -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add packages/maestra-ai/src/maestra_ai/core/curator.py \
        packages/maestra-ai/tests/unit/test_curator.py
git commit -m "feat(curator): _apply_negative_filter com fallback adaptativo

Issue #8. Hard filter remove candidatos com tag negada; se resultado
< MIN_CANDIDATES, retorna originais com degraded=True e log warning.
Caller (curate) usa flag pra ativar anti_tag_penalty."
```

---

## Task 9: `anti_tag_penalty` em `scoring.py`

**Files:**
- Modify: `packages/maestra-ai/src/maestra_ai/core/scoring.py`
- Modify: `packages/maestra-ai/tests/unit/test_scoring.py`

- [ ] **Step 1: Escrever testes**

Adicionar em test_scoring.py:

```python
class TestAntiTagPenalty:
    def test_sem_overlap_retorna_zero(self):
        from maestra_ai.core.scoring import anti_tag_penalty
        assert anti_tag_penalty({"rock"}, {"ambient"}, degraded=True) == 0.0

    def test_com_overlap_retorna_negativo(self):
        from maestra_ai.core.scoring import anti_tag_penalty
        p = anti_tag_penalty({"rock", "ambient"}, {"ambient"}, degraded=True)
        assert p < 0

    def test_degraded_false_sempre_zero(self):
        from maestra_ai.core.scoring import anti_tag_penalty
        # Mesmo com overlap, se degraded=False, retorna 0
        assert anti_tag_penalty({"ambient"}, {"ambient"}, degraded=False) == 0.0

    def test_multiplos_overlaps_penalizam_mais_ate_limite(self):
        from maestra_ai.core.scoring import anti_tag_penalty
        p1 = anti_tag_penalty({"a"}, {"a"}, degraded=True)
        p2 = anti_tag_penalty({"a", "b"}, {"a", "b"}, degraded=True)
        p5 = anti_tag_penalty({"a", "b", "c", "d", "e"}, {"a", "b", "c", "d", "e"}, degraded=True)
        assert p2 < p1  # mais negativo
        assert p5 <= p2  # não pior que 3 (limite em 3 pela spec)

    def test_negative_tags_vazio_retorna_zero(self):
        from maestra_ai.core.scoring import anti_tag_penalty
        assert anti_tag_penalty({"rock"}, set(), degraded=True) == 0.0
```

- [ ] **Step 2: Rodar e confirmar falhas**

Expected: 5 fails.

- [ ] **Step 3: Implementar `anti_tag_penalty`**

Adicionar em `core/scoring.py`:

```python
# Constante no topo do módulo (com as outras weights)
W_ANTI_TAG: float = 0.4  # calibrar após primeira semana de uso (issue #13)


def anti_tag_penalty(
    track_tags: set[str],
    negative_tags: set[str],
    *,
    degraded: bool,
) -> float:
    """Penalty negativa para candidatos com tag negada, ativa só em modo degraded.

    Retorna 0.0 quando:
    - degraded=False (hard filter já tratou, não penalizar duas vezes).
    - Sem overlap entre track_tags e negative_tags.

    Escala: proporcional ao overlap, limitado em 3 tags pra evitar crescimento
    descontrolado. Fórmula: -W_ANTI_TAG * min(overlap_count, 3) / 3.
    """
    if not degraded or not negative_tags:
        return 0.0
    overlap = len(track_tags & negative_tags)
    if overlap == 0:
        return 0.0
    capped = min(overlap, 3)
    return -W_ANTI_TAG * (capped / 3)
```

- [ ] **Step 4: Rodar e confirmar verde**

```bash
uv run pytest packages/maestra-ai/tests/unit/test_scoring.py::TestAntiTagPenalty -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add packages/maestra-ai/src/maestra_ai/core/scoring.py \
        packages/maestra-ai/tests/unit/test_scoring.py
git commit -m "feat(scoring): anti_tag_penalty para modo degraded

Issue #8. Penalty negativa proporcional ao overlap com tags negadas,
capped em 3. Ativa só quando _apply_negative_filter degradou; zero
caso contrário (não penaliza duas vezes)."
```

---

## Task 10: `_build_informed_query` real

**Files:**
- Modify: `packages/maestra-ai/src/maestra_ai/core/curator.py`
- Modify: `packages/maestra-ai/tests/unit/test_curator.py`

- [ ] **Step 1: Escrever testes**

Adicionar em test_curator.py:

```python
class TestBuildInformedQuery:
    def _ctx(self, **kwargs):
        from maestra_ai.core.context_parser import ParsedContext
        defaults = {"text": "", "positive": (), "negative": (), "artists_hint": (), "bpm": None}
        defaults.update(kwargs)
        return ParsedContext(**defaults)

    def test_vazio_retorna_none(self, curator, monkeypatch):
        monkeypatch.setattr(curator.taste, "get_preferred_artists", lambda: [])
        assert curator._build_informed_query(self._ctx()) is None

    def test_so_positivo_gera_query(self, curator, monkeypatch):
        monkeypatch.setattr(curator.taste, "get_preferred_artists", lambda: [])
        q = curator._build_informed_query(self._ctx(positive=("metal",)))
        assert q is not None
        assert "metal" in q

    def test_positivo_e_artist_hint_combinam(self, curator, monkeypatch):
        monkeypatch.setattr(curator.taste, "get_preferred_artists", lambda: [])
        q = curator._build_informed_query(self._ctx(
            positive=("metal",), artists_hint=("Gojira",)
        ))
        assert "Gojira" in q
        assert "metal" in q

    def test_bpm_adiciona_qualificador(self, curator, monkeypatch):
        from maestra_ai.core.context_parser import BpmRange  # T4.5: bpm é BpmRange, não dict
        monkeypatch.setattr(curator.taste, "get_preferred_artists", lambda: [])
        q = curator._build_informed_query(self._ctx(
            positive=("metal",), bpm=BpmRange(min=100, max=120)
        ))
        assert q is not None
        assert "metal" in q
        # Qualificador de bpm é adicionado — formato "110bpm" (média)
        assert "110" in q or "bpm" in q.lower()

    def test_so_taste_sem_positive_usa_top_artista(self, curator, monkeypatch):
        monkeypatch.setattr(curator.taste, "get_preferred_artists", lambda: ["Heilung"])
        q = curator._build_informed_query(self._ctx())
        assert q is not None
        assert "Heilung" in q

    def test_top_taste_negado_pula_pro_proximo(self, curator, monkeypatch):
        monkeypatch.setattr(
            curator.taste, "get_preferred_artists",
            lambda: ["Ambient Band", "Heilung"]
        )
        q = curator._build_informed_query(self._ctx(negative=("ambient",)))
        # "Ambient Band" tem "ambient" case-insensitive → pula
        assert q is not None
        assert "Heilung" in q
        assert "Ambient" not in q

    def test_todos_os_top_taste_negados_e_sem_positive_retorna_none(self, curator, monkeypatch):
        monkeypatch.setattr(
            curator.taste, "get_preferred_artists",
            lambda: ["Ambient One", "Ambient Two", "Ambient Three"]
        )
        q = curator._build_informed_query(self._ctx(negative=("ambient",)))
        assert q is None
```

- [ ] **Step 2: Rodar e confirmar falhas**

Expected: 6 fails (stub atual retorna None sempre, só `test_vazio_retorna_none` passa).

- [ ] **Step 3: Implementar `_build_informed_query` real**

Substituir o método em `core/curator.py`:

```python
def _build_informed_query(self, parsed) -> str | None:
    """Query informada a partir de ParsedContext + taste.

    Formato: "{artist_hint_ou_top_taste} {positive} {bpm_qualifier}".
    Skip top taste que aparecem em negative. Retorna None se nenhum sinal.
    """
    negative = set(parsed.negative) if parsed.negative else set()

    # Parte 1: artista (artist_hint tem prioridade sobre top taste)
    artist_part: str | None = None
    if parsed.artists_hint:
        artist_part = parsed.artists_hint[0]
    else:
        # Top preferred artist que não bata com negative
        top = self.taste.get_preferred_artists() or []
        for a in top[:5]:
            if not any(n in a.lower() for n in negative):
                artist_part = a
                break

    # Parte 2: positive (primeiro termo, se houver)
    positive_part = parsed.positive[0] if parsed.positive else None

    # Parte 3: bpm qualifier
    # T4.5: parsed.bpm é BpmRange (não dict) — acesso via atributo, não .get()
    bpm_part = None
    if parsed.bpm is not None and parsed.bpm.min is not None and parsed.bpm.max is not None:
        mid = (parsed.bpm.min + parsed.bpm.max) // 2
        bpm_part = f"{mid}bpm"

    # Se nenhuma parte produziu sinal, retorna None
    parts = [p for p in (artist_part, positive_part, bpm_part) if p]
    if not parts:
        return None
    return " ".join(parts)
```

- [ ] **Step 4: Rodar e confirmar verde**

```bash
uv run pytest packages/maestra-ai/tests/unit/test_curator.py::TestBuildInformedQuery -v
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add packages/maestra-ai/src/maestra_ai/core/curator.py \
        packages/maestra-ai/tests/unit/test_curator.py
git commit -m "feat(curator): _build_informed_query real

Issue #8. Deriva query de ParsedContext + taste.get_preferred_artists.
Skip top taste que batem com parsed.negative. BPM target vira
qualificador (ex: '110bpm'). Encerra stub de v0.10.0-alpha.1."
```

---

## Task 11: Integração em `curate()`

**Files:**
- Modify: `packages/maestra-ai/src/maestra_ai/core/curator.py` (método `curate`)
- Modify: `packages/maestra-ai/tests/unit/test_curator.py`

- [ ] **Step 1: Escrever testes de integração**

Adicionar em test_curator.py:

```python
class TestCurateIntegracaoV013:
    def test_curate_usa_parsed_context_quando_informado(self, curator, mock_controller, monkeypatch):
        """curate() agora aceita ctx como str ou ParsedContext."""
        # Fixture mock_controller retorna N tracks. Assert que o fluxo
        # completa sem erro e devolve tupla de 3.
        result = curator.curate("foco", count=3)
        assert len(result) == 3  # (tracks, queries, sources)

    def test_curate_aplica_negative_filter_e_reporta_queries(self, curator, mock_controller, monkeypatch):
        """Com contexto que tem 'evitar ambient', tracks com tag 'ambient' não aparecem."""
        from maestra_ai.core.external import cache as cache_mod
        # Mock: cada track tem tag baseada em sufixo
        def fake_get(uri):
            has_ambient = "1" in uri
            return {"musicbrainz": {"tags": ["ambient"] if has_ambient else ["rock"]}}
        monkeypatch.setattr(cache_mod, "get_track", fake_get)

        tracks, queries, sources = curator.curate("rock evitar ambient", count=5)
        # Tracks devolvidas não devem ter "ambient"
        for t in tracks:
            cached = fake_get(t["uri"])
            assert "ambient" not in (cached.get("musicbrainz") or {}).get("tags", [])

    def test_curate_degraded_log_warning(self, curator, mock_controller, monkeypatch, caplog):
        """Quando hard filter esvazia, loga warning."""
        import logging
        from maestra_ai.core.external import cache as cache_mod
        # Todos os candidatos têm "ambient"
        monkeypatch.setattr(cache_mod, "get_track",
                            lambda uri: {"musicbrainz": {"tags": ["ambient"]}})

        with caplog.at_level(logging.WARNING):
            curator.curate("rock evitar ambient", count=3)
        assert any("degrading to soft penalty" in r.message for r in caplog.records)
```

- [ ] **Step 2: Rodar e confirmar falhas**

Expected: a função ainda não integra `_apply_negative_filter`, então test 2 e 3 falham.

- [ ] **Step 3: Integrar na função `curate()`**

Editar `core/curator.py`, adaptar `curate()` pra incluir o novo stage:

```python
def curate(self, context, count=5, exclude_uris=None, exclude_artists=None,
           max_per_artist=None, enhance_candidates=True):
    """Gera lista de faixas para um contexto."""
    from maestra_ai.core.context_parser import parse as parse_context_text
    from maestra_ai.core.scoring import anti_tag_penalty

    # Normaliza: aceita string ou ParsedContext
    if hasattr(context, "text"):  # ParsedContext duck-typing
        parsed = context
        context_text = parsed.text
    else:
        context_text = self._normalize_context(context)
        parsed = parse_context_text(context_text, bpm=self._active_bpm_target())

    queries_used: list[str] = []
    candidates: list[dict] = []
    excluded = set(exclude_uris or [])
    excluded_artists = set(exclude_artists or [])
    seen: set[str] = set(excluded)
    search_limit = max(count, count + len(excluded), 10)

    def _search_and_collect(query: str) -> None:
        queries_used.append(query)
        results = self.controller.search(query, type="track", limit=search_limit)
        for r in results:
            if r["uri"] in seen:
                continue
            seen.add(r["uri"])
            candidates.append(r)

    # 1) Query informada (agora real)
    informed = self._build_informed_query(parsed)
    if informed:
        _search_and_collect(informed)

    # 2) Fallback SEMANTIC_MAP se abaixo do mínimo
    if len(candidates) < MIN_CANDIDATES:
        for q in self._resolve_queries(context_text):
            if q in queries_used:
                continue
            _search_and_collect(q)
            if len(candidates) >= MIN_CANDIDATES:
                break

    # 3) Enhancement (inalterado)
    if enhance_candidates and candidates:
        import logging
        logger = logging.getLogger(__name__)
        from maestra_ai.core.external import default_enhancer
        from maestra_ai.core.external.types import TrackInfo

        enhancer = default_enhancer()
        if enhancer._sources:
            track_infos: list[TrackInfo] = []
            for c in candidates:
                track_infos.append({
                    "uri": c["uri"],
                    "name": c.get("track", c.get("name", "Unknown")),
                    "artists": [c["artist"]],
                    "isrc": c.get("isrc"),
                })
            try:
                enhancer.enhance_many(track_infos)
            except Exception as e:
                logger.warning("Enhancement de candidatos falhou: %s", e)

    # 4) NOVO: hard filter adaptativo
    candidates, degraded = self._apply_negative_filter(candidates, parsed)

    # 5) Filtros existentes
    filtered = []
    for c in candidates:
        if self.taste.is_rejected(c["uri"]):
            continue
        if self.taste.context_score(c["uri"], context_text) < 0:
            continue
        if c["artist"] in excluded_artists:
            continue
        filtered.append(c)

    filtered = self.taste.filter_with_artist_info(filtered)

    # 6) Re-rank com anti_tag_penalty quando degraded
    from maestra_ai.core.config import load_and_migrate, load_curate_weights
    cfg = load_and_migrate()
    weights = load_curate_weights(cfg)
    has_lf = (cfg.get("external_sources") or {}).get("lastfm", {}).get("enabled", False)
    negative_set = set(parsed.negative)

    def _score(c):
        base = self._compose_score_for(c, context_text, weights, has_lf)
        if degraded and negative_set:
            base += anti_tag_penalty(
                self._track_tags(c), negative_set, degraded=True,
            )
        return base

    filtered.sort(key=_score, reverse=True)

    # 7) max_per_artist
    if max_per_artist:
        limited: list[dict] = []
        counts: dict[str, int] = {}
        for t in filtered:
            a = t["artist"]
            if counts.get(a, 0) >= max_per_artist:
                continue
            counts[a] = counts.get(a, 0) + 1
            limited.append(t)
        filtered = limited

    return filtered[:count], queries_used, self._active_sources()
```

- [ ] **Step 4: Rodar suite completa e confirmar verde**

```bash
uv run pytest packages/maestra-ai -q
```

Expected: todos passam. Se algum teste antigo quebrou por causa do novo stage (ex: um mock que não retorna dict), ajustar para fornecer os campos esperados.

- [ ] **Step 5: Commit**

```bash
git add packages/maestra-ai/src/maestra_ai/core/curator.py \
        packages/maestra-ai/tests/unit/test_curator.py
git commit -m "feat(curator): integra parsed + negative_filter + anti_tag_penalty

Issue #8. curate() agora:
- Parseia contexto via ContextState/context_parser (aceita str ou ParsedContext)
- Chama _build_informed_query(parsed) real pra query inicial
- Aplica hard filter com fallback adaptativo após enhance_many
- No re-rank, aplica anti_tag_penalty quando degraded=True
- Mantém assinatura de retorno (tracks, queries_used, sources_used)

Encerra issue #8."
```

---

## Task 12: Expor integração via `ContextState.parsed()` nos consumidores chave

**Files:**
- Modify: `packages/maestra-ai/src/maestra_ai/cli/playlist.py`
- Modify: `packages/maestra-mcp/src/maestra_mcp/tools.py` (se houver handler de curate)

- [ ] **Step 1: Verificar onde curate é chamado**

```bash
grep -rn "curator.curate\|\.curate(" packages/maestra-ai/src/ packages/maestra-mcp/src/ 2>&1 | grep -v test
```

- [ ] **Step 2: Preservar compatibilidade**

A integração da Task 11 já aceita tanto string quanto ParsedContext. Chamadas existentes passando string continuam funcionando. **Sem mudança necessária**, a menos que grep revele um caso que se beneficiaria de passar ParsedContext diretamente.

- [ ] **Step 3: Se aplicável, migrar um caller pra passar parsed**

Por exemplo, `cli/curate.py` pode chamar:

```python
from maestra_ai.core.context import ContextState
state = ContextState(...)
parsed = state.parsed()
if parsed is not None:
    tracks, queries, sources = curator.curate(parsed, count=count)
else:
    tracks, queries, sources = curator.curate("foco", count=count)
```

Só fazer se o callsite já carrega ContextState.

- [ ] **Step 4: Rodar suite completa**

```bash
uv run pytest -q
```

Expected: todos passam.

- [ ] **Step 5: Commit (ou skip se não mudou nada)**

Se houve mudança:

```bash
git add <files>
git commit -m "refactor(callers): passa ParsedContext onde cabe

Issue #8. Preserva compat — curate ainda aceita string."
```

---

## Task 13: CHANGELOG + version bump pra v0.13.0

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `packages/maestra-ai/pyproject.toml`
- Modify: `packages/maestra-mcp/pyproject.toml` (se maestra-mcp pin versão)

- [ ] **Step 1: Ler version atual**

```bash
grep version packages/maestra-ai/pyproject.toml
```

- [ ] **Step 2: Bump pra 0.13.0**

Editar `packages/maestra-ai/pyproject.toml`, trocar `version = "0.12.0"` (ou atual) por `version = "0.13.0"`.

Se `packages/maestra-mcp/pyproject.toml` pin `maestra-ai>=0.X.0`, atualizar pra `>=0.13.0`.

- [ ] **Step 3: Adicionar entrada no CHANGELOG**

```markdown
## [0.13.0] - 2026-XX-XX

### Added
- Parser unificado de contexto (`context_parser.py`) com `ParsedContext`
  frozen — campos `positive`, `negative`, `artists_hint`, `bpm`.
- `ContextState.parsed()` memoizado, invalidação automática via `set()`.
- `_track_tags()` agora consome cache external (MB canônico + LF filtrado
  via `tag_filter.py`), substituindo stub de v0.10.0-alpha.1.
- `_build_informed_query()` real: deriva query de `ParsedContext` cruzado
  com `taste.get_preferred_artists()`, qualificador de BPM quando presente.
- `_apply_negative_filter` no stage de curate com fallback adaptativo
  (hard filter → soft penalty quando `< MIN_CANDIDATES`).
- `anti_tag_penalty` em `scoring.py`, ativo só em modo degraded.

### Changed
- `Curator.curate()` agora aceita `str` ou `ParsedContext` como contexto.

### Fixed
- Issue #8: curadoria respeita negações ("evitar X", "sem Y") e usa tags
  reais do cache external no scoring.

### Related
- Issue #13 continua aberta para melhorias futuras (parser EN, threshold
  de count em LF, cascade de ampliação da query informada, telemetria).
```

- [ ] **Step 4: Rodar suite pra garantir que version bump não quebra nada**

```bash
uv run pytest -q
```

- [ ] **Step 5: Commit**

```bash
git add CHANGELOG.md packages/maestra-ai/pyproject.toml packages/maestra-mcp/pyproject.toml
git commit -m "chore: bump para v0.13.0 + CHANGELOG

Fecha issue #8: query informada e negações semânticas."
```

---

## Task 14: Atualizar MCP instructions removendo o aviso de #8

**Files:**
- Modify: `packages/maestra-mcp/src/maestra_mcp/instructions.py`
- Modify: `packages/maestra-mcp/tests/test_instructions.py` (ajustar asserts se necessário)

- [ ] **Step 1: Remover bloco de aviso da issue #8**

Editar `instructions.py`, remover o parágrafo:

```markdown
- **Curadoria automática não respeita negações no contexto** (issue #8,
  v0.13): se o contexto ativo contém "evitar X" ou "sem Y", aplique
  filtro manual após `play_context` — o scoring ainda não penaliza
  tags negativas do cache external.
```

Se esse era o único item restante em "Limitações atuais" (porque #6 também já foi fixada), considere remover toda a seção ou manter com placeholder indicando "nenhuma limitação conhecida no momento".

- [ ] **Step 2: Atualizar teste de alerta**

Em `test_instructions.py`, remover a asserção:

```python
assert "#8" in INSTRUCTIONS or "negaç" in INSTRUCTIONS.lower() or "evitar" in INSTRUCTIONS.lower(), (
    "alerta sobre issue #8 (negações no contexto) ausente"
)
```

Substituir pelo teste reverso (documenta que o aviso não deve mais estar):

```python
def test_instructions_nao_mais_alerta_sobre_8():
    """Issue #8 foi resolvida em v0.13 — alerta deve ter sido removido."""
    from maestra_mcp.instructions import INSTRUCTIONS
    # Se este teste quebrar, algum refactor adicionou de volta o aviso
    # equivocadamente — o fix já está em produção.
    assert "#8" not in INSTRUCTIONS, (
        "aviso sobre issue #8 voltou indevidamente — "
        "a feature está implementada desde v0.13"
    )
```

- [ ] **Step 3: Rodar teste**

```bash
uv run pytest packages/maestra-mcp/tests/test_instructions.py -v
```

Expected: todos passam.

- [ ] **Step 4: Commit**

```bash
git add packages/maestra-mcp/src/maestra_mcp/instructions.py \
        packages/maestra-mcp/tests/test_instructions.py
git commit -m "docs(mcp): remove aviso de #8 das instructions (fix em v0.13)

Issue #8 resolvida. Mcp instructions param de avisar agentes sobre
necessidade de filtro manual de negações."
```

---

## Task 15: Atualizar spec do vault Iris

**Files:**
- Modify: `/home/menzani/claude/.iris/projetos/pessoal/maestra-ai/maestra-ai.md` (opcional se o doc vivo do vault reflete v0.13)
- Modify: `/home/menzani/.claude/iris/memory/project_maestra_spotify.md` (memória Iris, refletir v0.13)

- [ ] **Step 1: Atualizar projeto MD no vault**

No maestra-ai.md, mover seção v0.12 pra histórico e adicionar v0.13:

```markdown
### v0.13 — Query informada e negações (2026-XX-XX)

- Parser unificado de contexto (`context_parser.py`) com `ParsedContext`
- `ContextState.parsed()` memoizado
- `_track_tags` real consumindo cache external
- `_build_informed_query` real
- Hard filter + anti_tag_penalty pra negações
- MCP instructions atualizadas: aviso de #8 removido
```

- [ ] **Step 2: Atualizar memória do Iris**

Na memória `project_maestra_spotify.md`:
- Mudar "Release atual: **v0.10.0**" pra "Release atual: **v0.13.0**"
- Adicionar bullet sobre v0.13 antes dos bullets de v0.10/v0.9

- [ ] **Step 3: Commit no vault Iris**

```bash
cd /home/menzani/claude/.iris
git add memory/project_maestra_spotify.md projetos/pessoal/maestra-ai/maestra-ai.md
git commit -m "docs: v0.13 do maestra-ai em memória e índice"
```

---

## Self-review checklist

- [ ] Todos os 3 gaps do spec cobertos por task dedicada:
  - `_track_tags` real → Task 7
  - Parser de negações → Tasks 1–4
  - `_build_informed_query` real → Task 10
- [ ] Sem placeholders, TBD ou "implementar depois" em qualquer step.
- [ ] Nomes consistentes (ex: `ParsedContext`, `_apply_negative_filter`, `anti_tag_penalty`, `W_ANTI_TAG`, `MIN_CANDIDATES`).
- [ ] Cada task tem commit próprio — histórico linear e auditável.
- [ ] TDD preservado: teste primeiro, red, implementação, green, commit em todas as tasks de código.
- [ ] Fronteira de `MIN_CANDIDATES` tratada nos testes (Task 8, `test_fronteira_exatamente_min_candidates_e_sucesso`).
- [ ] Integração end-to-end garante que `curate()` inteiro funciona (Task 11, `TestCurateIntegracaoV013`).
- [ ] Version bump + CHANGELOG + memória Iris como tasks finais.
- [ ] MCP instructions atualizadas (Task 14) — remove aviso do bug fixado.

**Próximo passo após aprovação**: criar branch `feat/issue-8-v0130-query-informada-negacoes` a partir do `main` atualizado (pós-merge de #11, #12, #15, #16) e iniciar execução.

---

## Execução

**Executado em:** 2026-04-21
**Branch:** `feat/issue-8-v0130-query-informada-negacoes`
**Commits:** `6fbca0e..0265af2`
**Suite:** 891 passed, 0 failed
**Issue #8:** fechada

Divergências em relação ao plano original estão documentadas na Task 4.5 acima e na seção
"Divergências implementadas vs spec original" do spec MD correspondente.
