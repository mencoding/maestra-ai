# v0.9 — Fontes externas de metadata (design)

**Data:** 2026-04-20
**Status:** Aprovado (brainstorming)
**Autor:** Leonardo Menzani + Iris (Claude Opus 4.7)

---

## Contexto

Em 2025, a Spotify depreciou silenciosamente o campo `genres` nos endpoints
`GET /v1/artists/{id}` e `GET /v1/artists` (batch). A chamada ainda responde
200 OK, mas entrega `genres: []` para praticamente todos os artistas. A
maestra detectou esse comportamento em v0.8.0-alpha.6 e passou a emitir
warning específico, caindo no modo "sugestões baseadas em décadas e
artistas dominantes".

Sem gêneros/mood/BPM, a curadoria dinâmica fica limitada: não há vocabulário
semântico rico para refinar queries, nem sinais para re-ranking local, nem
base para expansão inteligente de seeds. Além disso, a Spotify já havia
depreciado o endpoint de Audio Features (valence/energy/danceability) em
novembro/2024 e o de Recommendations (`GET /v1/recommendations`) no mesmo
período. Os sinais nativos da plataforma, que antes cobriam bem a camada de
curadoria, foram sendo removidos progressivamente.

Este spec define como a maestra passa a usar fontes externas (MusicBrainz +
opcionalmente Last.fm e GetSongBPM) para recuperar e ampliar essa camada de
metadata, e como esses dados alimentam a curadoria dinâmica.

---

## Objetivo

Substituir a dependência do campo `genres` da Spotify por fontes externas
públicas, e aproveitar a adição para habilitar curadoria dinâmica enriquecida:
- gêneros canônicos (MusicBrainz, obrigatório)
- tags folksonômicas ricas e artistas similares (Last.fm, opcional)
- BPM, tonalidade e time signature (GetSongBPM, opcional)

Tudo que exige configuração manual por parte do usuário (criação de API key)
é **opcional**. MusicBrainz (sem key) é o núcleo que garante gêneros mesmo
para quem não quer configurar nada.

---

## Arquitetura

### Módulos novos

```
packages/maestra-ai/src/maestra_ai/core/external/
  __init__.py
  types.py              # EnhancedTrack, MusicBrainzData, LastfmData, BpmData
  musicbrainz.py        # EnhancementSource obrigatória
  lastfm.py             # EnhancementSource opcional
  getsongbpm.py         # EnhancementSource opcional
  enhancer.py           # agregador: orquestra fontes, merge, cache
  cache.py              # read/write atômico de external_cache.json
  attribution.py        # monta bloco "Fontes usadas" com links clicáveis
```

### Interface comum

```python
class EnhancementSource(Protocol):
    name: str                         # "musicbrainz" | "lastfm" | "getsongbpm"

    def is_configured(self) -> bool: ...

    def enhance_track(
        self, track: TrackInfo,
    ) -> SourceResult | None: ...

    def enhance_artist(
        self, artist_name: str, mbid: str | None,
    ) -> ArtistResult | None: ...
```

Cada fonte implementa o protocolo. `enhancer.py` conhece apenas o protocolo
e faz orquestração agnóstica.

### Modelo de dados

```python
class MusicBrainzData(TypedDict):
    mbid: str
    genres: list[str]         # canônicos (ex: "rock", "electronic")
    tags: list[str]           # folksonômicos do MB (ex: "chill", "90s")

class LastfmData(TypedDict):
    top_tags: list[str]       # top 5-10 por peso
    playcount: int
    listeners: int
    similar_artists: list[str]  # apenas nomes

class BpmData(TypedDict):
    bpm: float
    key: str                  # ex: "C minor"
    time_signature: str       # ex: "4/4"

class EnhancedTrack(TypedDict):
    uri: str                  # chave do cache
    isrc: str | None
    artist_mbid: str | None
    musicbrainz: MusicBrainzData | None
    lastfm: LastfmData | None
    bpm: BpmData | None
    sources: list[str]
    enhanced_at: str          # ISO 8601
    match_method: Literal["isrc", "name"]
```

### Cache

- **Arquivo:** `~/.local/share/maestra/external_cache.json`
- **Schema:** `{"version": 1, "tracks": {uri: EnhancedTrack}}`
- **Concorrência:** `atomic_write_json` com `fcntl.LOCK_EX` (mesmo mecanismo
  de `config.json` e `taste_profile.json`)
- **Permissão:** 0644 (sem secrets)
- **TTL:** permanente. Refresh manual via
  `maestra cache refresh [--source X] [--uri Y]`
- **Tamanho estimado:** ~500 bytes por faixa; 2000 faixas ≈ 1 MB

### Matching key

- **Primário:** ISRC (extraído de `track.external_ids.isrc` do Spotify).
  Cobertura ~99% em catálogo comercial. Match exato.
- **Fallback:** query `track:"Name" artist:"Artist"` no MB. Gera ruído; campo
  `match_method: "name"` fica registrado para debug.

### Rate limits e atribuição

| Fonte | Rate limit | User-Agent | Atribuição |
|-------|-----------|------------|------------|
| MusicBrainz | 1 req/s | obrigatório (`maestra-ai/{version} ({contact})`) | cortesia |
| Last.fm | ~5 req/s | recomendado | cortesia |
| GetSongBPM | 60 req/min | recomendado | **obrigatório** (TOS) |

### Paralelismo controlado

- `ThreadPoolExecutor(max_workers=3)` dentro do `enhancer`
- Token bucket interno por fonte para respeitar rate limits
- Para 100 faixas: ~100s só MB; ~30s MB+LF+BPM em paralelo
  (MB continua sendo o gargalo de 1req/s)

---

## Data flow

### Init (melhoramento eager das top 100)

1. `onboard.run` executa análise normal até obter `signals` — inalterado.
2. **Nova etapa opt-in** antes de `_print_onboard_results`:
   - "Quer melhorar a curadoria com fontes externas?"
   - 3 opções: configurar agora / pular tudo / usar só MusicBrainz
   - Se "configurar agora": prompts sequenciais pedindo keys opcionais.
3. Identifica top 100 faixas do perfil (maior peso combinado de
   `top_long_term` + `saved_tracks` + `recently_played`).
4. `enhancer.enhance_many(top_100_tracks, progress_cb)` — chama fontes
   ativas, aplica cache.
5. Grava cache. Relatório final (`_print_onboard_results`) inclui:
   - Contagem de faixas melhoradas por fonte
   - Bloco de atribuição clicável

### Curate (melhoramento incremental + scoring estendido)

1. **Expansão de seed** (se Last.fm configurado):
   - top artists do contexto → `lastfm.get_similar_artists(artist)` → seed_pool
   - Limita a N similares por artist (default 3)
2. **Query única informada** (sem relaxamento iterativo):
   - Template: `"{tag_dominante} {mood} {decade}"`
   - `tag_dominante` = top tag do perfil do contexto (do Last.fm se
     disponível; do MB caso contrário)
   - `mood` = subset das top tags do Last.fm que bate com lista canônica
     `MOOD_TAGS = {chill, energetic, melancholic, uplifting, dark, ...}`.
     Se Last.fm não configurado, `mood` vira string vazia e o template
     colapsa para `"{tag_dominante} {decade}"`.
   - Se sem tags no cache para o contexto, cai para a query atual da
     maestra (comportamento pré-v0.9).
3. `spotify.search(query)` → pool de candidatos (N=50 default)
4. **Melhoramento incremental dos candidatos faltantes no cache**:
   - `enhancer.enhance_many(faltantes, deadline=10s)`
   - Se estourar deadline: usa só o que conseguiu, segue
5. **Re-ranking com scoring estendido**:

```
   score = 0.4 * taste_weight
         + 0.3 * tag_similarity      (0 se sem tags)
         + 0.2 * decade_match         (binário ou proximity)
         + 0.1 * bpm_proximity        (0 se sem BPM ou sem alvo)
```

   Pesos configuráveis em `config.json` → `curate_weights: {...}`.

6. Top K faixas vão para a playlist (K vem de `--count` ou default 20).
7. Atualiza cache com tudo que foi melhorado.
8. Imprime bloco de atribuição das fontes usadas.

### Degradação por fonte indisponível

- **MusicBrainz** 500/timeout → gêneros ausentes; pipeline segue com
  `top_genres` originais do perfil como fallback.
- **Last.fm** ausente/403 → sem expansão de seed; peso `tag_similarity`
  redistribuído para `taste_weight` e `decade_match`.
- **GetSongBPM** ausente/403 → `bpm_proximity` zera; peso redistribuído.

Toda falha é logada em `warnings[]` e não bloqueia a operação principal.

---

## UX

### Nova etapa opt-in no init

```
━━━ Melhorar curadoria com fontes externas (opcional) ━━━

A Maestra pode consultar bancos de dados públicos para identificar
gêneros, mood e BPM das faixas. Isso melhora a qualidade das sugestões
de contexto e permite filtrar por ritmo.

Fontes:
  • MusicBrainz — gêneros canônicos (sem configuração, sempre ativo
    se você aceitar).
  • Last.fm — tags ricas + artistas similares (grátis, 2 min para
    criar uma chave em https://www.last.fm/api/account/create).
  • GetSongBPM — BPM e tonalidade (grátis, 2 min em
    https://getsongbpm.com/api).

Custo: ~2–3 min extras no init (melhora as 100 faixas mais importantes).
Depois, melhoramento incremental durante o uso.

Escolha:
  [1] Configurar agora (posso pular Last.fm/BPM individualmente)
  [2] Pular tudo — curadoria segue só com dados do Spotify
  [3] Usar só MusicBrainz (sem keys, sem config)
```

- `[1]` → prompt sequencial pedindo cada key, `[Enter]` = pular.
- `[2]` → grava `external_sources_enabled: false`.
- `[3]` → grava `external_sources_enabled: true` só com MB ativo.

### Comandos CLI

```
maestra config external status
  → lista fontes ativas e se têm key configurada

maestra config external enable [--no-musicbrainz]
maestra config external disable

maestra config external set-key lastfm <key>
maestra config external set-key bpm <key>
maestra config external clear-key lastfm
maestra config external clear-key bpm

maestra cache refresh [--source X] [--uri Y]
  → força re-fetch; sem flags, refaz tudo
```

### profile show --human ganha bloco

```
Melhoramento externo:
  MusicBrainz: ativo (87 faixas com gêneros canônicos)
  Last.fm:     ativo (87 faixas com tags, 145 artistas com similar)
  BPM:         inativo (sem chave configurada)
```

### Atribuição

Ao final de `curate` e em `profile show --human`, quando fontes externas
foram usadas na ação corrente, um bloco dedicado (sem estilo dim):

```
Fontes usadas nesta curadoria:
  • MusicBrainz        → https://musicbrainz.org/doc/About
  • Last.fm            → https://www.last.fm/about
  • GetSongBPM.com     → https://getsongbpm.com/about
```

Links renderizados com OSC 8 via `[link=...]texto[/link]` do rich — clicáveis
em terminais modernos (gnome-terminal, iTerm2, Kitty, Alacritty, Windows
Terminal), fallback para texto simples em terminais antigos.

**Seletivo:** só lista fontes efetivamente usadas na ação corrente. Se o
usuário tem só MB ativo, só aparece MB.

---

## Testes

### Unit por fonte

- `tests/unit/external/test_musicbrainz.py`
- `tests/unit/external/test_lastfm.py`
- `tests/unit/external/test_getsongbpm.py`

Cada um cobre:
- Fixture JSON de resposta real (baixada e versionada em
  `tests/fixtures/external/`)
- Assert shape dos TypedDicts
- Lookup por ISRC (success)
- Lookup por name+artist (fallback)
- HTTP 404 → retorna `None` sem raise
- HTTP 500/timeout → `None` + warning
- Rate limit respeitado (usa `freezegun` + mock `time.sleep`)

### Unit do enhancer

`tests/unit/external/test_enhancer.py`:
- Merge de múltiplas fontes em `EnhancedTrack`
- Uma fonte indisponível → outras seguem sem afetar resultado
- Cache hit → não chama fonte
- `is_configured() == False` → skip sem erro
- ThreadPoolExecutor respeita rate limits por fonte

### Unit do cache

`tests/unit/external/test_cache.py`:
- Atomic write + lock
- Schema v1 load/save
- Refresh seletivo por `--source` e `--uri`
- Migração de cache corrompido (reseta ao default)

### Integration

`tests/integration/test_external_flow.py`:
- Init com `external_sources_enabled: true` → cache populado corretamente
- Curate com cache hit → zero chamadas externas
- Curate com cache miss → enhance incremental funciona
- Deadline estourado → usa o que tem, segue

### E2E

`tests/e2e/test_curate_with_enhancement.py`:
- Spotify mockado, todas as fontes externas mockadas
- Valida scoring final considera tags + BPM + década
- Valida bloco de atribuição sai no output

### Dependências novas

- `musicbrainzngs` (cliente MB oficial, mantido)
- `pylast` (cliente Last.fm maduro)
- `httpx` (GetSongBPM não tem cliente Python maduro → HTTP direto)
- `responses` (mocking HTTP, para testes)

---

## Versionamento e entrega

### v0.9.0 — núcleo MusicBrainz-only

- Arquitetura completa (`core/external/types.py`, `cache.py`,
  `enhancer.py`, `attribution.py`, `musicbrainz.py`)
- **Só MusicBrainz implementado e ativo** — módulos `lastfm.py` e
  `getsongbpm.py` não existem ainda
- Opt-in no init com **apenas uma opção implementada**: ativar MB.
  Sub-menu ainda não oferece Last.fm/BPM.
- Cache + `maestra cache refresh`
- `profile show` mostra metadata MB
- Atribuição clicável (MB apenas)
- Scoring do curate **não muda** em v0.9 — gêneros do MB populam
  `top_genres` no lugar dos gêneros perdidos da Spotify, o resto do
  pipeline continua igual.

**Valor entregue:** gêneros canônicos de volta, independente da Spotify.
Curadoria volta ao estado pré-depreciação.

### v0.10.0 — curadoria enriquecida

- **Adiciona `lastfm.py` e `getsongbpm.py`** (opcionais)
- Sub-menu do opt-in no init ganha as três opções completas
- Scoring estendido no curate com `tag_similarity` + `bpm_proximity`
- Seed expansion via `lastfm.get_similar_artists`
- Query única informada usando tags+mood+década
- Re-ranking completo com pesos configuráveis
- Contexto opcional com BPM alvo
  (`maestra context set "foco" --bpm 80-100`)

**Valor entregue:** curadoria dinâmica usando o vocabulário externo,
expansão inteligente, BPM targeting.

### Alphas durante desenvolvimento

`v0.9.0-alpha.N` e `v0.10.0-alpha.N` seguindo o padrão do projeto.

---

## Migração

- `external_sources_enabled: false` por default em perfis existentes.
- `maestra init` em state C (complete) detecta ausência do bloco e oferece
  a etapa de melhoria como opção no sub-menu de update.
- Sem migração destrutiva: quem não quer, simplesmente ignora.

---

## Escopo fora

Fica para depois, se fizer sentido:
- MCP tools expondo metadata externa aos agents
- Daemon `director` reagindo a mudanças no cache
- Export/import do cache entre dispositivos
- Integração com Discogs, ListenBrainz, Deezer
- BPM dinâmico por contexto (sugerir faixa automaticamente) — v0.10+
- Refresh automático de artistas novos no perfil (user faz manual)
- UI gráfica de gerenciamento do cache

---

## Decisões-chave registradas

- **Opt-in e opcional:** tudo que exige ação do usuário (criar API key) é
  opcional. MusicBrainz (sem key) é o piso.
- **Terminologia PT:** "melhorar", "melhoria", "melhoramento" em textos
  user-facing. Código em inglês (`enhancer`, `EnhancedTrack`, `enhance_many`).
- **Query simples, ranking rico:** query única sem relaxamento iterativo;
  peso do melhoramento entra no re-ranking local.
- **Híbrido eager+incremental:** init melhora top 100; curate completa o
  resto conforme os contextos são usados. Ação sempre completa antes do
  consumidor prosseguir (não é "lazy"; é "incremental").
- **Atribuição unificada:** bloco clicável listando todas as fontes usadas,
  não apenas GetSongBPM. Cumpre TOS do GSB e dá visibilidade honesta às
  fontes gratuitas que aceitam esse modelo.
- **Cache permanente:** metadata musical é estável; refresh é manual.
