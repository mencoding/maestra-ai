# v0.10 — Last.fm + GetSongBPM + curadoria enriquecida

**Status:** Design aprovado 2026-04-20
**Pré-requisito:** v0.9.0 estável (commit 6584b36) — fechada.
**Issues relacionadas:** mencoding/maestra-ai#3 (este escopo), #4 (guias interativos, absorvido aqui).
**Supersede parcial:** Seções "v0.10.0 — curadoria enriquecida" e "Last.fm/GetSongBPM"
do design `2026-04-20-v090-external-sources-design.md`, que cobriu v0.10
apenas em alto nível.

---

## Objetivo

Ativar o ganho real de curadoria dinâmica adicionando duas fontes externas
opcionais (Last.fm e GetSongBPM), mudando o `Curator` de busca por queries
fixas para query informada por metadata real, e introduzindo scoring
composto no re-rank. Entrega em 3 alphas sequenciais para calibrar com
dados reais antes da próxima etapa.

## Escopo

**Dentro:**
- Fonte `lastfm.py` (via pylast) — tags folksonômicas ricas e artistas similares.
- Fonte `getsongbpm.py` (via `urllib.request`) — BPM, key, time signature.
- Seed expansion on-demand (`lastfm.get_similar_artists`) com cache TTL 60d.
- Scoring composto no `Curator` (taste + tag + decade + bpm) com weights
  configuráveis em `config.json` e degradação graciosa.
- Curate em modo cascade (query informada → fallback SEMANTIC_MAP).
- Contexto ativo vira objeto `{text, bpm}` com migração automática.
- `maestra context set "<texto>" --bpm <min>-<max>` e `context clear-bpm`.
- Guias interativos de criação de API key (padrão `_flow_A_collect_credentials`).
- Atribuição OSC 8 estendida para as 3 fontes.

**Fora:**
- BPM dinâmico por contexto (sugerir faixa automaticamente) — v0.11+.
- CLI dedicada para weights (edição manual no `config.json` basta; regra
  de negócio documentada).
- Pré-computação de similaridade no `maestra init`.
- Reescrita de SEMANTIC_MAP com vocabulário Last.fm (v0.11+).

## Decisões estruturantes aprovadas no brainstorming

| Decisão | Escolha |
|---------|---------|
| Cliente HTTP | `pylast` (Last.fm) + `urllib.request` (GetSongBPM) — híbrido pragmático |
| Papel Last.fm no curate | Cascade: query informada primeiro, complementa com SEMANTIC_MAP se < 10 candidatos |
| Shape do contexto | Objeto `{text: str, bpm: {min, max} \| null}` com migração automática |
| Weights | `config.json` com edição manual; regra de negócio documentada, sem CLI dedicada |
| Seed expansion | On-demand com cache TTL 60d (sem pré-computação no init) |
| Ordem de entrega | 3 alphas incrementais (Last.fm → scoring → BPM) |

## Arquitetura

### Módulos novos

```
core/external/
  lastfm.py           — LastfmSource(EnhancementSource).
                          _lookup(track_info) -> LastfmData
                          get_similar_artists(artist_key, limit=N)
                        Rate limit: 5 req/s via Lock + monotonic.
                        Via pylast.LastFMNetwork.

  getsongbpm.py       — GetSongBpmSource(EnhancementSource).
                          _lookup(track_info) -> BpmData
                        Rate limit: 60 req/min (janela deslizante).
                        Via urllib.request + json.loads.

  seed_expander.py    — SeedExpander(lastfm_source, cache).
                          expand(artist_keys, limit_per_artist) -> list[str]
                        Consulta cache.similar_artists primeiro;
                        fetched_at + TTL 60d; fallback silencioso
                        quando LF não configurado.

  setup_guides.py     — guide_lastfm() -> (enabled, api_key)
                        guide_getsongbpm() -> (enabled, api_key)
                        Padrão de passos numerados, validação leve,
                        Enter vazio = pular.
```

### Módulos modificados

```
core/curator.py       — Cascade + score composto.
                        curate() retorna (tracks, queries_used, sources_used).

core/context.py       — active_context: dict (text + bpm).
                        load(): migração automática (str → {text, bpm: None}).
                        set_bpm(min, max) / clear_bpm().

core/config.py        — curate_weights com defaults + validação.
                        external_sources com shape nested.

core/init.py          — _prompt_external_sources_optin com 3 opções.
                        Orquestra setup_guides.

cli/config.py         — set-key/clear-key aceitam 'lastfm'/'bpm'.
                        'maestra config external guide <source>' re-roda guia.

cli/context.py        — 'context set' aceita --bpm X-Y.
                        'context clear-bpm' novo subcomando.

core/external/cache.py — schema 2: + similar_artists.
                         Migração automática 1 → 2 no load.

core/external/attribution.py — 3 fontes (MB, LF, GSB) com URLs.

core/external/enhancer.py — aceita múltiplas sources (já aceita em v0.9,
                            só preenche lastfm/bpm quando presentes).
```

## Estrutura de dados

### `config.json` após v0.10

```json
{
  "active_context": {
    "text": "foco profundo",
    "bpm": { "min": 60, "max": 90 }
  },
  "external_sources": {
    "musicbrainz": { "enabled": true },
    "lastfm":      { "enabled": true,  "api_key": "..." },
    "getsongbpm":  { "enabled": false, "api_key": null }
  },
  "curate_weights": {
    "taste":  0.4,
    "tag":    0.3,
    "decade": 0.2,
    "bpm":    0.1
  }
}
```

### Migrações automáticas no load

- `active_context: str` → `{text: <str>, bpm: null}`.
- `external_sources` ausente → `{musicbrainz: {enabled: true}, lastfm: {enabled: false, api_key: null}, getsongbpm: {enabled: false, api_key: null}}`.
- `external_sources` flat `{enabled: bool}` (shape v0.9) → nested com campos novos.
- `curate_weights` ausente → defaults (0.4 / 0.3 / 0.2 / 0.1).

### Validação de `curate_weights`

- Soma deve fechar `1.0 ± 0.01`.
- Cada valor em `[0, 1]`.
- Falha → log warning, aplica defaults.

### Cache estendido (`~/.cache/maestra/external_cache.json`)

```json
{
  "schema": 2,
  "tracks": { "<isrc>": { ... EnhancedTrack ... } },
  "similar_artists": {
    "<mbid_or_name_normalized>": {
      "similars": ["artist1", "artist2", ...],
      "fetched_at": "2026-04-20T15:54:38-03:00"
    }
  }
}
```

- Migração `schema: 1 → 2`: adiciona `similar_artists: {}`.
- TTL `similar_artists`: 60 dias (stale → re-fetch).

## Scoring composto

### Fórmula

```
score = w_taste  * taste_score      # [-1, 1]
      + w_tag    * tag_similarity   # [0, 1]
      + w_decade * decade_match     # {0, 1}
      + w_bpm    * bpm_proximity    # [0, 1]
```

### Componentes

- **`taste_score`** — `TasteProfile.context_score(uri, context.text)` clamped a [-1, 1]. Já existe.
- **`tag_similarity`** — Jaccard entre tags do candidato (Last.fm top_tags do artista; fallback MB tags+genres) e tags do contexto (derivadas de mood_mappings). `intersection / union`. Vazio → 0.
- **`decade_match`** — `1.0` se década da faixa ∈ décadas dominantes **globais** do perfil (já calculadas no `maestra init` e gravadas em `profile.json`), senão `0.0`. Não usa décadas do contexto — o sinal aqui é "música compatível com a era musical do usuário", não "era musical desse contexto específico".
- **`bpm_proximity`** — quando contexto tem `bpm` target e faixa tem `track_bpm`:
  ```
  center = (min + max) / 2
  half = (max - min) / 2 + 10     # tolerância fora da janela
  bpm_proximity = max(0, 1 - abs(track_bpm - center) / half)
  ```
  Sem target ou sem BPM → 0.

### Degradação graciosa (`effective_weights`)

Regra única: sinal indisponível → seu peso migra para `w_taste`.

| Situação | Efeito |
|----------|--------|
| Last.fm OFF | `w_tag → 0`, `w_taste += 0.3` (ou valor configurado) |
| Contexto sem BPM target | `w_bpm → 0`, `w_taste += 0.1` |
| Faixa específica sem BPM | mesmo, por-faixa |
| Década não resolvível na faixa | `w_decade → 0`, `w_taste += 0.2`, por-faixa |

Motivo: taste é o único sinal sempre presente e específico do usuário; confiar nele quando o resto falha reflete a intuição pedida.

## `Curator.curate()` em modo cascade

```
1. Resolve contexto (text, mood derivado, década dominante).
2. Monta query informada:
     "{tag_dominante} {mood} {decade_str}"
   - `conjunto_positivo` = faixas da biblioteca onde `TasteProfile.context_score(uri, context.text) > 0`.
   - `tag_dominante` = tag Last.fm mais frequente agregada sobre os artistas de `conjunto_positivo`. Fallback quando LF indisponível: genre MB dominante do mesmo conjunto. Fallback final (conjunto vazio, ex. contexto novo): top genre global do perfil.
   - `mood` = subset das top tags Last.fm de `conjunto_positivo` ∩ `MOOD_TAG_KEYWORDS`. Fallback quando LF indisponível ou sem match: mood derivado via `mood_mappings` a partir do texto do contexto.
   - `decade_str` = década dominante de `conjunto_positivo` quando clara (ex: `"2010s"`); vazio caso contrário.
3. Busca com query informada (limit = count * 3).
4. Se len(candidates) < MIN_CANDIDATES (10):
     Complementa com queries do SEMANTIC_MAP até min ou esgotar.
5. Filtros existentes: is_rejected, context_score < 0, excludes.
6. Re-rank por score composto (com effective_weights).
7. max_per_artist se setado.
8. Retorna top-K.
```

Retorno ampliado: `(tracks, queries_used, sources_used)`.

## UX de opt-in e guias interativos

### Prompt estendido (`init.py::_prompt_external_sources_optin`)

```
━━━ Fontes externas de metadata ━━━

O melhoramento usa fontes públicas para preencher gêneros, mood e BPM
das faixas. Isso melhora muito a qualidade da curadoria.

Fontes:
  • MusicBrainz — gêneros e tags (grátis, sem chave, já ativo).
  • Last.fm — tags ricas + artistas similares (grátis, ~2 min para criar chave).
  • GetSongBPM — BPM e tonalidade (grátis, chave enviada por e-mail).

Escolha:
  [1] Só MusicBrainz (não preciso mexer em mais nada agora)
  [2] Configurar Last.fm e/ou GetSongBPM agora (guias passo-a-passo)
  [3] Pular tudo, configurar depois com 'maestra config external'
```

### Guia Last.fm (`setup_guides.guide_lastfm`)

```
━━━ Configurar Last.fm (opcional) ━━━
Last.fm fornece tags ricas e descobre artistas similares.

Passos:
  1. Abrir https://www.last.fm/api/account/create
  2. Preencher:
     • Application name:        Maestra
     • Application description: Uso pessoal
     • Callback URL:            deixar em branco
     • Application homepage:    deixar em branco
  3. Submeter. A próxima tela mostra a "API key" (32 chars).
  4. Cole aqui: <prompt>

Enter vazio pula. Configurar depois:
  maestra config external set-key lastfm <key>
```

### Guia GetSongBPM (`setup_guides.guide_getsongbpm`)

```
━━━ Configurar GetSongBPM (opcional) ━━━
GetSongBPM fornece BPM, tonalidade e time signature.

Passos:
  1. Abrir https://getsongbpm.com/api
  2. Preencher email + URL do projeto onde a atribuição ficará visível
     (pode usar https://github.com/mencoding/maestra-ai).
  3. Receber a API key por email (alguns minutos).
  4. Cole aqui quando receber: <prompt>

Atribuição obrigatória: 'maestra curate --human' mostra o link
para getsongbpm.com/about em toda execução que usa BPM.

Enter vazio pula. Configurar depois:
  maestra config external set-key bpm <key>
```

### Validação leve

- Last.fm: 32 chars hex, sem espaços.
- GetSongBPM: 8+ chars, sem espaços.
- Fora disso: "A chave parece estranha. Pular por ora e configurar depois?"

## CLI estendida

```
maestra context set "<texto>" [--bpm <min>-<max>]
maestra context clear-bpm

maestra config external status
maestra config external enable  <musicbrainz|lastfm|getsongbpm>
maestra config external disable <musicbrainz|lastfm|getsongbpm>
maestra config external set-key <lastfm|getsongbpm> <key>
maestra config external clear-key <lastfm|getsongbpm>
maestra config external guide <lastfm|getsongbpm>    # re-roda guia
```

## Rate limits e atribuição

| Fonte | Rate | Implementação | Atribuição |
|-------|------|---------------|------------|
| MusicBrainz | 1 req/s | Lock + monotonic (já existe) | cortesia |
| Last.fm | 5 req/s | Lock + monotonic | cortesia |
| GetSongBPM | 60 req/min | janela deslizante | **obrigatória (TOS)** |

Atribuição OSC 8 (linha única ao fim do `curate --human`):

```
Metadata: MusicBrainz · Last.fm · GetSongBPM
```

Cada nome é link clicável via OSC 8 / rich `[link=URL]nome[/link]`.

## Dependências novas

```toml
dependencies = [
    # ... existentes ...
    "pylast>=5.3",
]
```

Só `pylast`. GetSongBPM continua via stdlib.

## Flow por alpha

### v0.10.0-alpha.0 — Last.fm como fonte de enriquecimento

**Entrega:**
- `core/external/lastfm.py` completo.
- `core/external/seed_expander.py` com cache integrado.
- `core/external/setup_guides.py::guide_lastfm`.
- Sub-menu opt-in do init com 3 opções, orquestrando guia Last.fm.
- `maestra config external set-key/clear-key/enable/disable lastfm`.
- `maestra config external guide lastfm`.
- Cache schema `1 → 2` com migração.
- Atribuição OSC 8 estende para LF.
- `artists_tags` do onboard agora recebe Last.fm top_tags junto com MB tags.

**Não entra:**
- Scoring composto (próximo alpha).
- Query informada no curate (próximo alpha).

**Validação manual chave:** ativar Last.fm no `init`; relatório do onboard deve mostrar mais tags por artista do que apenas MB.

### v0.10.0-alpha.1 — scoring composto + cascade

**Entrega:**
- `core/scoring.py` (novo) com `compose_score`, `effective_weights` e componentes puros (`tag_similarity`, `decade_match`, `bpm_proximity`).
- `core/curator.py` em modo cascade.
- `curate_weights` em `config.json` com defaults + validação.
- `Curator.curate()` retorna `sources_used`.
- Atribuição no `curate --human` condicional às fontes efetivamente usadas na ação.

**Não entra ainda:**
- GetSongBPM (próximo alpha) — `bpm_proximity` fica sempre 0 e peso redistribui para taste.
- `--bpm` no context set.

**Validação manual chave:** rodar `curate` com e sem Last.fm; ordenação deve mudar; sem LF, `w_tag` deve migrar para `w_taste`.

### v0.10.0-alpha.2 — GetSongBPM + contexto BPM

**Entrega:**
- `core/external/getsongbpm.py` completo.
- `core/external/setup_guides.py::guide_getsongbpm`.
- `maestra config external set-key/clear-key/enable/disable bpm`.
- `maestra config external guide bpm`.
- Contexto ativo como objeto `{text, bpm}` com migração automática.
- `maestra context set --bpm X-Y` e `context clear-bpm`.
- `bpm_proximity` entra efetivamente no score.
- Guia BPM no opt-in estendido.
- Atribuição estende para GSB (obrigatória quando BPM usado).

**Validação manual chave:** configurar BPM target, rodar `curate`; faixas fora da janela devem cair no ranking mesmo quando taste neutro.

### v0.10.0 — consolidação

- CHANGELOG agrega os 3 alphas.
- Tag `v0.10.0`.
- Push + issue #3 fechada.

## Testes

### Unit (TDD estrito)

```
tests/unit/external/
  test_lastfm.py            — mock pylast.LastFMNetwork; valida
                              _lookup_by_isrc, _lookup_by_name,
                              get_similar_artists, rate limit 5 req/s.
  test_getsongbpm.py        — mock urllib.request.urlopen;
                              _lookup, parsing JSON, rate limit 60/min.
  test_seed_expander.py     — cache hit/miss, TTL 60d, fallback sem LF.
  test_setup_guides.py      — mock questionary; validação de chave,
                              Enter vazio = skip, string inválida reprompt.
  test_cache_migration.py   — schema 1 → 2 adiciona similar_artists.

tests/unit/
  test_scoring.py           — compose_score, effective_weights em
                              cada combinação de sources on/off,
                              redistribuição para taste.
  test_curator_cascade.py   — query informada sozinha com 10+ results;
                              complemento SEMANTIC_MAP quando abaixo;
                              retorno (tracks, queries, sources).
  test_context_migration.py — string → objeto no load;
                              --bpm parsing; clear-bpm;
                              validação min<max, min>=30, max<=220.
  test_config_weights.py    — defaults, validação soma = 1.0,
                              valor fora [0,1] cai para defaults.
```

### Integration (live, opt-in)

```
tests/integration/
  test_lastfm_live.py       — NOVO. Fleetwood Mac; valida tags.
                              Marker integration_live.
  test_getsongbpm_live.py   — NOVO. ISRC conhecido; valida BPM.
                              Marker integration_live. Requer env
                              MAESTRA_GETSONGBPM_KEY.
```

### Critério por alpha

| Alpha | Testes verdes | Validação manual |
|-------|---------------|------------------|
| alpha.0 | lastfm, seed_expander, setup_guides, cache_migration | `init` com LF: tags no onboard |
| alpha.1 | scoring, curator_cascade, config_weights + suíte completa sem regressão | `curate` com e sem LF mostra ordenação distinta |
| alpha.2 | getsongbpm, context_migration + suíte completa | BPM target afeta ranking |

### Regras de mocking

- Mock na fronteira (pylast, urllib, questionary, spotify client), nunca interna.
- Componentes de score testados puros; `compose_score` só soma.
- Cache: `tmp_path` fixture (padrão v0.9).
- Rate limit: `freezegun` para avançar `time.monotonic`.
- Spotify no curate: continua mockado explicitamente (regra v0.9 mantida).

## Riscos e mitigações

| Risco | Mitigação |
|-------|-----------|
| pylast bloqueante / rate limit confuso | Envelope com Lock + monotonic. Timeout por request (5s). Exceções são absorvidas — source falha, pipeline continua. |
| GetSongBPM response instável / TOS | HTTP direto + parsing defensivo. Atribuição sempre visível. Chave opcional — pipeline degrada sem ela. |
| Cache cresce indefinidamente | similar_artists TTL 60d; `maestra cache refresh` limpa. `.cache/maestra/` em HOME cache XDG. |
| Calibração de weights difícil | YAGNI: editar JSON à mão. Defaults foram derivados da spec v0.9 pós-brainstorming. Regra de negócio documentada aqui. |
| Migração de contexto/cache quebra existing users | Migração automática e silenciosa no load; testes cobrindo ambos os shapes. |

## Trabalho deixado para fora do escopo

- **Reescrita do SEMANTIC_MAP** com vocabulário Last.fm — v0.11+.
- **BPM dinâmico por contexto** (derivar automaticamente do perfil do contexto em vez de usuário passar range) — v0.11+.
- **CLI para weights** — só se evidência real aparecer.
- **Pré-computação no onboard** — só se cold cache virar queixa.
