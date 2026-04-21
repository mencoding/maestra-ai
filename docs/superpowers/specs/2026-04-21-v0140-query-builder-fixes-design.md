# v0.14.0 — Query builder fixes (curadoria aderente)

**Data:** 2026-04-21
**Issue principal:** [#20](https://github.com/mencoding/maestra-ai/issues/20) (4 bugs catalogados)
**Issue dependente:** [#21](https://github.com/mencoding/maestra-ai/issues/21) — playlist TTL-aware (desbloqueia-se após v0.14)
**Autor:** Léo + Claude (diagnóstico empírico live em 3 curadorias, 2026-04-21)
**Status:** approved | **Branch:** `feat/issue-20-v0140-query-builder-fixes`

---

## Problema

Três curadorias live hoje mostraram aderência inaceitável ao contexto "metal tribal ritual com momentum operacional":

| Curadoria | Contexto | Query enviada ao Spotify | Aderência |
|---|---|---|---|
| 1ª (~15:58) | com `tipo The HU Heilung e Wardruna` | `"The HU Heilung"` | 1/6 = **17%** |
| 2ª (~16:50) | idem | `"The HU Heilung"` | 2/10 = **20%** |
| 3ª (~17:20) | reformulado com 6 artistas-guia | `"The HU"` | 2/20 = **10%** |

Isso é evidência empírica de bugs estruturais no pipeline de query building. O bug #20 original (polysemy lexical do `Heilung` → cura alemã) expandiu para **4 bugs distintos** ao longo do diagnóstico.

## Escopo

Atacar os 4 bugs numa release única. Eles são inter-dependentes: resolver só um não melhora a aderência de forma útil.

### Fora do escopo

- Playlist TTL-aware (issue #21) — requer #20 resolvido como pré-condição
- Parser bilíngue PT+EN (issue #13)
- Refactor completo do `_resolve_queries` (múltiplas camadas: SEMANTIC_MAP, DESCRIPTOR_MAP, learned, DIRECT_PREFIXES, informed) — apenas o path informed é tocado
- Rewrite do `_split_clauses` — correção cirúrgica, não refactor

## Bugs catalogados

### #20-1 — Polysemy lexical do artist_hint

**Sintoma:** `Heilung` (banda nórdica) no contexto → query `"The HU Heilung"` → Spotify retorna tracks "Heilung der Seele", "Klänge der Heilung" (therapeutic music alemã, `Heilung` = cura).

**Root cause:** `_extract_artists` em `context_parser.py:92` captura qualquer sequência capitalizada ASCII como artist_hint, sem validar que é uma banda real.

**Correção:** validação via MusicBrainz (T4). Camada de defesa secundária — o fix primário é o T3 (DSL Spotify).

### #20-2 — `str(context_dict)` vazando para query Spotify (CRÍTICO)

**Sintoma:** Quando contexto não tem marker positivo (`tipo/como/parecido com/mais`), a API Spotify recebe:
```
q={'text': 'metal tribal ritual, momentum operacional...', 'bpm': none}
```
E retorna **HTTP 400 Bad Request** (`Query exceeds maximum length of 250 characters`).

**Root cause (3 camadas):**

1. **`tools.py:208`** (MCP):
   ```python
   context_name = (ctx or {}).get("context", "default")
   ```
   `ctx["context"]` é o dict `{"text": "...", "bpm": null}` — **não** a string de texto. A variável `context_name` recebe o dict, não um nome/texto.

2. **`curator.py:414`** (`_normalize_context`):
   ```python
   context = str(context).strip()
   ```
   Converte o dict sem checar tipo. Resultado: string-repr-do-dict.

3. **`curator.py:396`** (fallback em `_resolve_queries`):
   ```python
   return [context_lower]
   ```
   Nenhum match em SEMANTIC_MAP/DIRECT_PREFIXES/DESCRIPTOR_MAP (óbvio — a string-dict não casa com nada), então devolve a string-dict literal como query.

**Correção:** defense in depth — fix nas 3 camadas (T1).

### #20-3 — Parser extrai apenas 1 artist após marker

**Sintoma:** Contexto `"tipo The HU, Wardruna, Nine Treasures, Tengger Cavalry, Eluveitie, Skáld"` → `queries_used = ["The HU"]`. Os outros 5 artistas são descartados silenciosamente.

**Root cause:** `_split_clauses` em `context_parser.py:62` usa `re.split(r"[,.;]", text)`. A vírgula fatia a lista em múltiplas clauses — apenas a primeira (`"tipo The HU"`) tem marker `tipo`, então `_extract_after_marker_pair` só dispara lá.

**Correção:** modificar `parse()` para, após detectar marker positivo numa clause, absorver clauses subsequentes como continuação até encontrar (a) clause com marker negativo, (b) clause sem letras capitalizadas iniciais (indicativo de trecho descritivo, não lista de artistas). Ver T2.

### #20-4 — Ausência de DSL Spotify `artist:"…"` no query builder

**Sintoma:** Query `"The HU"` (texto livre) faz o Spotify retornar tudo que começa com "The Hu": The Human League, The Hunter × 4, The Huntress, The Hustle, The Hub, The Hum, The Hunger, Hunger Games OST, etc.

**Root cause:** `_build_informed_query` em `curator.py:56-89` concatena `artist_hint + positive + bpm` como texto livre. A API Spotify search com `q="The HU"` faz matching por prefixo lexical em título/artista/álbum, sem distinguir nome-próprio.

**Correção:** quando `parsed.artists_hint` tem N > 0 itens, usar DSL: `artist:"X" OR artist:"Y" OR ...`. Escape de aspas internas. `positive` e `bpm` permanecem como texto livre concatenado (são descritores de gênero/ritmo). Ver T3.

## Arquitetura

### Unidades tocadas

| Arquivo | Mudança |
|---|---|
| `packages/maestra-mcp/src/maestra_mcp/tools.py` | `_curate`: extrair `ctx["context"]["text"]` antes de passar para `curator.curate()` |
| `packages/maestra-ai/src/maestra_ai/core/curator.py` | `_normalize_context`: aceitar ParsedContext/dict e extrair `.text`/`["text"]`; `_build_informed_query`: DSL Spotify quando há artists_hint; nova função de validação MB |
| `packages/maestra-ai/src/maestra_ai/core/context_parser.py` | `parse()`: absorver clauses subsequentes como continuação de lista de artistas após marker positivo |
| `packages/maestra-ai/tests/**` | testes novos cobrindo cada bug |

### O que NÃO muda

- Assinatura externa de `Curator.curate()` — continua `(tracks, queries, sources)`
- Schema persistido `context.json` — intacto
- Frozen dataclass `ParsedContext` + `BpmRange` — intactos
- Comportamento do parser quando marker NÃO é encontrado — intacto (só extends após marker detectado)

## Plano de tasks (TDD subagent-driven-dev)

| # | Task | Escopo | Model |
|---|---|---|---|
| T1 | Bug #20-2 (crítico, 3 camadas) | tools.py, curator._normalize_context, testes | Sonnet |
| T2 | Bug #20-3 (parser multi-artist) | context_parser.parse, testes | Sonnet |
| T3 | Bug #20-4 (DSL Spotify) | curator._build_informed_query, testes | Sonnet |
| T4 | Bug #20-1 (validação MB) | curator (novo helper), integração com external cache, testes | Sonnet |
| T5 | Release v0.14.0 | CHANGELOG, bump, PR, merge, tag | Haiku |

Ordem de execução: T1 → T2 → T3 → T4 → T5. Sequencial (branch única, evitar conflitos).

## Critério de sucesso

- Suite de testes verde (>=895 testes, +4 novos mínimo)
- `ruff check` verde
- Curadoria live pós-merge com mesmo contexto anterior deve produzir aderência > 70% (empírico — validar manual via MCP após release)
- CHANGELOG.md registra os 4 fixes explicitamente
- Tag v0.14.0 pushada, issue #20 fechada

## Validação empírica pós-release

Depois do merge + tag, rodar via MCP:

```
set_context(description="metal tribal, tipo The HU, Wardruna, Nine Treasures, evitar hip-hop, evitar ambient")
curate(max_tracks=20, max_per_artist=2)
```

Verificar:
- `queries_used` contém `artist:"The HU" OR artist:"Wardruna" OR artist:"Nine Treasures"`
- Tracks retornados são majoritariamente dos artists pedidos (>=60%)
- Nenhum "The Human League", "The Hustle", "Heilung der Seele" etc.

Só aí a issue #21 (playlist TTL-aware) fica desbloqueada.
