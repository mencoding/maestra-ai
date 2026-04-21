# v0.13.0 — Query informada e negações semânticas

**Data:** 2026-04-20
**Issue principal:** [#8](https://github.com/mencoding/maestra-ai/issues/8)
**Issue de backlog:** [#13](https://github.com/mencoding/maestra-ai/issues/13) (itens rejeitados por YAGNI imediato)
**Autor:** Léo + Claude (brainstorm síncrono)
**Status:** approved — aguardando writing-plans

---

## Problema

A curadoria atual (`Curator.curate()`) ignora negações no contexto e opera com match textual ingênuo. Exemplos empíricos documentados:

- Contexto `"metal tribal… evitar ambient calmo, evitar acústico suave"` com BPM 100–140 retorna `Dark Ambient Strumming` (Horror Music Archives) e `Dark Gothic Ambient` (Myers Music). O curador pega a palavra "ambient" em match literal do SEMANTIC_MAP e ignora as negações.
- Contexto rico mencionando referências (The HU, Heilung, Wardruna) não beneficia o scoring — `_track_tags` devolve `set()` vazio, então `tag_similarity` vale 0 e o peso tag colapsa pra zero no scoring composto.

Três stubs documentados no código corroboram o gap:

1. `Curator._build_informed_query(context)` — retorna `None` (comentário: "v0.10.0-alpha.1: stub mínimo").
2. `Curator._track_tags(track)` — retorna `set()` (comentário: "v0.10.0-alpha.1: simplificado").
3. Nenhum parser existente entende negações (`evitar`, `sem`, `não`).

## Escopo

Atacar os três gaps em um único spec. Decisão deliberada após brainstorm: a fronteira entre eles é artificial — `_build_informed_query` real precisa da estrutura parseada do contexto (que não existe), e o scoring com `_track_tags` real precisa de negações funcionais pra não introduzir novas falhas (tags negativas ponderariam positivamente).

### Fora do escopo

- Parser bilíngue PT + EN → issue #13 (item 1).
- Filtro de qualidade Last.fm por threshold de popularidade → #13 (item 2).
- `_build_informed_query` em cascade de ampliação → #13 (item 3).
- Telemetria automática pra calibrar weights → #13 (item 4).
- Integração live com catálogo real (fica em `tests/integration/…live.py` existentes).

## Decisões consolidadas

| # | Decisão | Escolha |
|---|---|---|
| 1 | Escopo | Atacar os 3 gaps juntos (A + B + C) |
| 2 | Forma de representar contexto estruturado | Híbrido — `ContextState` inalterado; derivação via parser puro com memoização |
| 3 | Severidade das negações | Hard filter com fallback adaptativo (< MIN_CANDIDATES → soft penalty + warning) |
| 4 | Escopo do parser | Unificado — `ParsedContext` com `text`, `positive`, `negative`, `artists_hint`, `bpm` |
| 5 | Approach técnica | **2 (BALANCED)** — parser regex com normalização, `_track_tags` merge MB+LF filtrado, `_build_informed_query` real |

## Arquitetura

Três unidades novas + duas modificadas. Todas isoladas e testáveis isoladamente.

### Unidades novas

1. **`core/context_parser.py`** — módulo puro sem import do core.
   - `@dataclass(frozen=True) ParsedContext`.
   - `parse(text: str, bpm: dict | None = None) -> ParsedContext`.
   - Constantes centralizadas: `POSITIVE_MARKERS`, `NEGATIVE_MARKERS`, `META_TAGS`.

2. **`ParsedContext`** — dataclass frozen, definida em `context_parser.py`.
   - Campos: `text: str`, `positive: tuple[str, ...]`, `negative: tuple[str, ...]`, `artists_hint: tuple[str, ...]`, `bpm: dict | None`.
   - Frozen → hashable, seguro pra cache.

3. **`core/external/tag_filter.py`** — helper puro.
   - `filter_lastfm_tags(raw: list[dict], *, top_n: int = 10) -> set[str]`.
   - Remove tags-meta (anos, países, adjetivos avaliativos), normaliza case.

### Unidades modificadas

4. **`core/curator.py`**:
   - `_build_informed_query()` passa a derivar query real via `ParsedContext + taste.conjunto_positivo`.
   - `_track_tags()` passa a consumir `core/external/cache.py`, mergeando MB (autoritativo) + LF filtrado.
   - `curate()` ganha stage novo `_apply_negative_filter` entre `enhance_many` e `taste.is_rejected`, com fallback adaptativo.

5. **`core/context.py` — `ContextState`**:
   - Método novo `parsed() -> ParsedContext | None` que chama `context_parser.parse()` e memoiza com chave = `text` cru.
   - `set()` invalida o cache.

### O que NÃO muda

- Schema persistido em disco de `context.json` (`{text, bpm, set_at, ttl_minutes}`).
- Assinatura externa de `Curator.curate()` — continua `(tracks, queries, sources)`.
- Schema MCP `set_context` / `get_context` — continua aceitando `description: str`.
- `scoring.compose_score()` — só ganha novo componente via extensão, não redesenho.

## Componentes — contratos

### `core/context_parser.py`

```python
from __future__ import annotations
from dataclasses import dataclass

POSITIVE_MARKERS = ("tipo ", "como ", "algo tipo ", "parecido com ", "mais ")
NEGATIVE_MARKERS = ("evitar ", "sem ", "não ", "nao ")
META_TAGS = frozenset({
    # Anos
    "1970s", "1980s", "1990s", "2000s", "2010s", "2020s",
    # Países
    "brazilian", "american", "british", "french", "german", "japanese",
    # Avaliativos
    "awesome", "favorite", "favourite", "good", "great", "amazing",
    # Genéricos vazios
    "music", "cool", "nice",
})

@dataclass(frozen=True)
class ParsedContext:
    text: str
    positive: tuple[str, ...] = ()
    negative: tuple[str, ...] = ()
    artists_hint: tuple[str, ...] = ()
    bpm: dict | None = None

def parse(text: str, bpm: dict | None = None) -> ParsedContext:
    """Extrai intenção estruturada de texto livre. Puro, idempotente,
    determinístico. Nenhum I/O, nenhum logging."""
```

**Regras de parsing:**

- Normalização: `unicodedata.normalize("NFKC", text).casefold()` antes do match.
- Matcher esquerdo-a-direita, greedy por marker. Marker consome até próxima vírgula, ponto, ou próximo marker.
- Positivos e negativos são **conjuntos disjuntos**: se token aparece em ambos, vence o negativo.
- `artists_hint` extraído via detecção de capitalização no `text` original (não normalizado) após marker positivo.

### `core/external/tag_filter.py`

```python
def filter_lastfm_tags(raw: list[dict], *, top_n: int = 10) -> set[str]:
    """Recebe lista bruta do LF (dicts com keys `name` e `count`).
    Descarta tags-meta definidas em META_TAGS, normaliza case,
    preserva top_n por `count` desc."""
```

### `core/context.py` — extensão de `ContextState`

```python
def parsed(self) -> ParsedContext | None:
    """Retorna ParsedContext do estado atual, memoizado até TTL expirar.
    None se .show() retorna None (sem contexto ativo)."""

def set(self, ..., **kwargs) -> dict:
    """Override que invalida self._parsed_cache antes de delegar."""
```

Memoização é atributo interno `_parsed_cache: tuple[str, ParsedContext] | None`. Chave = `text` cru. Invalidação automática via `set()`.

### `core/curator.py` — funções novas/modificadas

```python
def _track_tags(self, track: dict) -> set[str]:
    """Tags do track via cache external. MB canônico + LF filtrado via
    tag_filter. Retorna set() quando nenhuma source populou."""

def _build_informed_query(self, parsed: ParsedContext) -> str | None:
    """Query informada: positive + artists_hint + top genre do
    taste.conjunto_positivo + qualificador bpm. Pula top taste que
    apareça em parsed.negative. Retorna None quando sem sinal."""

def _apply_negative_filter(
    self,
    candidates: list[dict],
    parsed: ParsedContext,
) -> tuple[list[dict], bool]:
    """Hard filter removendo candidatos com tag em parsed.negative.
    Retorna (filtered, degraded).
    Se len(filtered) < MIN_CANDIDATES → retorna candidatos originais,
    degraded=True, log warning."""
```

### `core/scoring.py` — função nova

```python
def anti_tag_penalty(
    track_tags: set[str],
    negative_tags: set[str],
    degraded: bool,
) -> float:
    """Penalty negativo quando há overlap entre track_tags e negative_tags.
    Retorna 0.0 quando degraded=False (hard filter já tratou) ou sem overlap.
    Escala: -0.5 * min(overlap_count, 3) * W_ANTI_TAG."""
```

`W_ANTI_TAG` constante privada, valor inicial `0.4` (calibrar via testes empíricos).

## Fluxo de dados em `curate()`

```
curate(context, count=5, …)
  │
  ▼
ContextState.parsed()          ← memo hit ou parse via context_parser
  │
  ▼
parsed: ParsedContext
  │
  ├─► _build_informed_query(parsed) → informed query ou None
  │       │
  │       ▼
  │   _search_and_collect(informed)
  │
  ├─► fallback _resolve_queries (se < MIN_CANDIDATES) — cascade existente
  │
  ▼
candidates: list[dict]
  │
  ▼
enhance_many(candidates)       ← popula cache external (inalterado)
  │
  ▼
filtered, degraded = _apply_negative_filter(candidates, parsed)      ← NOVO
  │
  ▼
filter por is_rejected, context_score<0, excluded_artists           (inalterado)
  │
  ▼
taste.filter_with_artist_info                                        (inalterado)
  │
  ▼
re-rank: para cada c,
   score = compose_score(
     taste   = taste.context_score(c.uri, text),
     tag     = tag_similarity(_track_tags(c), _context_tags(text)),  ← _track_tags REAL
     decade  = decade_match(...),
     bpm     = bpm_proximity(...),
   )
   if degraded:
     score -= anti_tag_penalty(_track_tags(c), set(parsed.negative), degraded=True)
  │
  ▼
max_per_artist
  │
  ▼
return (tracks[:count], queries_used, sources_used)
```

### Invariantes críticos

- **`parsed` é construído uma vez por `curate()`** e passado como parâmetro; nunca global.
- **`_track_tags` é chamado N vezes no scoring loop (hot path)** — depende de cache populado por `enhance_many`; `filter_lastfm_tags` memoizado por URI.
- **Dois lugares independentes tratam negação:**
  - `_apply_negative_filter` (pré-scoring): filtra quando possível.
  - `anti_tag_penalty` (durante scoring): ativo só quando `degraded=True`.
- **Re-rank permanece como único lugar de composição de score** — novos componentes só alimentam ou filtram antes.

## Tratamento de erros e degradação

### Parser

| Cenário | Comportamento |
|---|---|
| Texto vazio | `ParsedContext(text="", …)` com campos vazios. Curator trata como sem contexto e usa `DEFAULT_CONTEXT="foco"`. |
| Só negações, sem positivos | `negative` preenchido, resto vazio. `_build_informed_query` → `None`. Cascade cai pra SEMANTIC_MAP. Negações ainda filtram. |
| Unicode / acentos | Normalização NFKC + casefold antes do match. `"não"` e `"nao"` funcionalmente iguais. |
| Texto ambíguo | Janela greedy esquerda→direita. Documentado no docstring. |
| Conflito positivo/negativo (mesmo token) | Negativo vence. Testado. |
| Input degenerado (null bytes, 10k chars) | Sem crash. Testado. Sem try/except — parser é regex puro, falha seria bug. |

### Cache external e `_track_tags`

| Cenário | Comportamento |
|---|---|
| Nenhuma source ativa | `_track_tags` → `set()`. Hard filter no-op. Log INFO uma vez por `curate()` quando há negações: "negações do contexto não serão aplicadas — nenhuma fonte external ativa". |
| MB ativo, LF inativo | Só tags MB. Sem filter LF. |
| `enhance_many` falha parcial | Já tratado (log warning existente). Cache pode ficar incompleto. Best-effort. |
| Track sem tags no cache | `set()`. Não contribui para scoring nem para filter. |

### Hard filter adaptativo

| Cenário | Comportamento |
|---|---|
| `len(filtered) >= MIN_CANDIDATES` | `filtered` usado. `degraded=False`. |
| `len(filtered) < MIN_CANDIDATES` | Candidatos originais usados. `degraded=True`. Warning: `"hard filter on %s would leave %d candidates (< %d); degrading to soft penalty"`. `anti_tag_penalty` ativa. |
| Todos com tag negativa | `filtered=[]`. Degraded path. Faixa com menor overlap sobe no re-rank. Não ideal mas melhor que fila vazia. |

### Memoização

| Cenário | Comportamento |
|---|---|
| `.set()` → cache invalidado | `set()` reseta `_parsed_cache=None`. Próximo `.parsed()` reparseia. |
| TTL expirado | `.show()` → `None`. `.parsed()` também. |
| Texto idêntico em chamadas consecutivas | Identidade preservada: `p1 is p2`. |

### `_build_informed_query`

| Cenário | Comportamento |
|---|---|
| Parser vazio + taste vazio | `None`. |
| Só taste | Query com top genre do taste + bpm qualifier. |
| Top taste está em `parsed.negative` | Pula top, tenta próximo. Se todos top-5 negados → `None`. |

### Logging

- **Parser**: silencioso. DEBUG com campos extraídos.
- **Hard filter adaptativo**: WARNING quando degrada.
- **`_track_tags` sem sources**: INFO uma vez por `curate()`, só se há negações.
- **`_build_informed_query`**: DEBUG com query construída (reaproveitar logging existente).

**Nenhum `raise` novo no caminho de `curate()`.** Filosofia: degradar com telemetria, nunca derrubar.

## Testing strategy

### Ordem TDD (bottom-up)

1. `context_parser.parse()` — puro, primeiro.
2. `tag_filter.filter_lastfm_tags()` — puro, paralelo.
3. `ContextState.parsed()` — consome parser.
4. `_track_tags` real — consome cache + tag_filter.
5. `_apply_negative_filter` — consome parser + cache.
6. `anti_tag_penalty` em scoring.
7. `_build_informed_query` real — consome parser + taste.
8. Integração em `curate()`.

Cada camada: teste primeiro, red confirmado, fix, green. Se camada N não for testável sem mock pesado da camada M, refatorar camada M primeiro.

### Cobertura estimada

- `test_context_parser.py` — ~25 testes (happy path, unicode, multi-marker, conflitos, edge, frozen/hash).
- `test_tag_filter.py` — ~10 testes (remoção de meta, normalização, top_n).
- Extensão de `test_context.py` — ~6 testes (memoização, invalidação, TTL, bpm repass).
- Extensão de `test_curator.py`:
  - `_track_tags` real — ~8 testes.
  - `_apply_negative_filter` — ~8 testes.
  - `_build_informed_query` real — ~10 testes.
  - Integração em `curate()` — ~5 testes novos + regressão dos existentes.
- Extensão de `test_scoring.py` — ~5 testes pra `anti_tag_penalty`.

**Total estimado: ~77 testes novos.** Alvo: 770 → ~847 passed.

### Metas de cobertura

- Novos módulos (`context_parser`, `tag_filter`): ≥ 95%.
- `curator.py`: ≥ 90% (manter baseline atual).
- `scoring.py`: ≥ 90%.

### Casos críticos (que **têm** de estar cobertos)

- Parser: unicode fold, multi-marker, conflito positivo/negativo, input degenerado.
- Hard filter: exatamente na fronteira `MIN_CANDIDATES` (caso borderline).
- Memoização: identidade preservada, invalidação via `.set()`, TTL.
- `_build_informed_query`: todos os 5+ branches listados (empty, só taste, só positive, conflito, todos top negados).
- Integração: contexto "evitar X" + taste com X → track sem X no resultado.

### Casos explicitamente **não** testados

- Integração live MB/LF (fica em `tests/integration/…live.py` existentes).
- Performance em carga 10k+ candidatos.
- Parser EN (issue #13).

## Critérios de aceite

- [ ] Os três gaps da issue #8 resolvidos, com testes de regressão.
- [ ] `ParsedContext` cobre os 5 campos especificados, frozen e hashable.
- [ ] Contexto `"rock denso, sem ballads"` via `play-context` retorna tracks sem tag "ballad".
- [ ] Contexto `"metal tribal evitar ambient"` NÃO retorna tracks com tag "ambient" (salvo degradação com warning).
- [ ] `_track_tags` retorna tags reais do cache external, mergeando MB (canônico) + LF filtrado.
- [ ] `_build_informed_query` retorna query construída quando há sinal; `None` apenas em degenerados explícitos.
- [ ] Fallback adaptativo loga warning quando hard filter esvazia; não entrega fila vazia.
- [ ] Suite total ≥ 840 passed, 0 failed (baseline 770 + ~77 novos – talvez alguns ajustados).
- [ ] Sem breaking changes: todos os consumidores de `Curator.curate()` (cli/playlist.py, cli/curate.py, mcp/tools.py) continuam funcionando sem mudança.
- [ ] Cobertura ≥ 95% nos módulos novos, ≥ 90% em `curator.py` e `scoring.py`.

## Próximos passos

1. **writing-plans** gera plano de implementação task-por-task com TDD hard.
2. Implementação em branch `feat/issue-8-query-informada-negacoes` baseada em `main` pós-merge das PRs #11, #12.
3. Release `v0.13.0` (semver minor — novo comportamento visível, sem breaking change).
4. CHANGELOG entry referenciando #8 como fechado e #13 como aberto pra v0.14+.

## Referências

- Issue #8 — descrição empírica do problema.
- Issue #13 — backlog de upgrades futuros.
- `packages/maestra-ai/src/maestra_ai/core/curator.py` — onde os stubs vivem (linhas 48, 177).
- `packages/maestra-ai/src/maestra_ai/core/external/cache.py` — cache que `_track_tags` vai consumir.
- `packages/maestra-ai/src/maestra_ai/core/external/mood_mappings.py` — `MOOD_TAG_KEYWORDS` usado em `_context_tags` (já funciona).
- `packages/maestra-ai/src/maestra_ai/core/scoring.py` — onde `anti_tag_penalty` vai ser adicionada.
