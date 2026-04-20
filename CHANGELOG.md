# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.9.0-alpha.0] — 2026-04-20

### Adicionado
- **Fontes externas de metadata** (v0.9: MusicBrainz-only; arquitetura
  preparada para Last.fm + GetSongBPM em v0.10):
  - Novo pacote `core/external/` com `EnhancementSource` Protocol,
    `Enhancer` (cache + orquestração), fonte `MusicBrainzSource` via
    `musicbrainzngs`, cache persistente `external_cache.json`, e
    `attribution` com links clicáveis (OSC 8).
  - Opt-in no `maestra init`: nova etapa "Melhorar curadoria com fontes
    externas" com opções `[2]` Pular / `[3]` Usar MusicBrainz.
  - `maestra config external status/enable/disable` — controle explícito
    em qualquer momento.
  - `maestra cache refresh [--source X] [--uri Y]` — força re-fetch na
    próxima ação.
  - `maestra profile show --human` — bloco "Melhoramento externo" com
    contagem de faixas por fonte.
  - `maestra curate --human` — bloco de atribuição clicável ao fim
    quando fontes externas foram usadas.
  - Migração no state C: usuários já com perfil completo são oferecidos
    a habilitar fontes externas ao entrar no sub-menu de update (só uma
    vez, até decidirem).
- Lookup MB primário via ISRC (`track.external_ids.isrc`); fallback para
  `name+artist` quando ISRC ausente ou sem match.
- Graceful degradation: `musicbrainzngs.NetworkError` e 404 não bloqueiam
  a análise; o pipeline segue com os dados do Spotify.
- Atribuição unificada com OSC 8 hyperlinks para as três fontes (Last.fm
  e GetSongBPM em v0.10), seletiva — só lista as efetivamente usadas.

### Alterado
- `onboard.run` ganha parâmetro `enhance_external: bool = True` e duas
  novas chaves no report: `external_enhanced_count`, `external_sources_used`.

### Dependências
- `musicbrainzngs>=0.7.1` (nova, obrigatória).
- `responses>=0.25` já estava em dev-deps.

### Referências
- Spec: `docs/superpowers/specs/2026-04-20-v090-external-sources-design.md`
- Plano: `docs/superpowers/plans/2026-04-20-v090-musicbrainz.md`
- Issues: [#2](https://github.com/mencoding/maestra-ai/issues/2)

## [0.8.0-alpha.7] — 2026-04-20

### Adicionado
- `maestra profile show [--human]` — visão agregada do perfil atual:
  estado do init, total de faixas analisadas, contadores de feedback,
  contextos registrados, sugestões da última análise (com gêneros,
  décadas, artistas que as embasam) e timestamp. Default JSON; `--human`
  imprime narrativa legível.
- Módulo `core.profile_view.build_profile_view()` agrega
  `taste_profile.json` + `onboard_rationale.json` + `detect_state()` em
  um dict read-only (sem side effects).

## [0.8.0-alpha.6] — 2026-04-20

### Corrigido
- `init`: callback de progresso do fallback item-a-item em `_fetch_artists_genres`
  não era conectado ao console (progresso silencioso). Agora emite
  `"lendo gênero N/M..."` a cada 5 artistas.
- `init`: `_print_onboard_results` lia chave `"suggestions"` mas o report de
  `onboard.run` usa `"context_suggestions"` — sugestões nunca apareciam ao final.

### Adicionado
- Warning específico quando o fallback item-a-item retorna gêneros vazios para
  todos os artistas. Motivo: Spotify deprecou silenciosamente o campo `genres`
  em `GET /v1/artists/{id}` ao longo de 2025 (ref. community.spotify.com).
  Sugestões passam a ser baseadas em décadas e artistas dominantes.

## [0.8.0-alpha.5] — 2026-04-20

### Corrigido
- Regressão em v0.8.0-alpha.4: `_derive_suggestions` fazia lookup de gêneros
  por nome de artista, mas `_fetch_artists_genres` passou a chavear por ID.
  Resultado: `top_genres` sempre vazio em runtime real. Fix: lookup agora
  por `artist.id` em ambos os sites (linhas ~460 e ~606 de `core/onboard.py`).

## [0.8.0-alpha.4] — 2026-04-20

### Corrigido
- `_fetch_artists_genres` agora tenta batch primeiro; em falha (Dev Mode
  Spotify bloqueia `/v1/artists?ids=...` em alguns apps), cai em loop
  item-a-item via `/v1/artists/<id>` que funciona em todos os modos.
  Trade-off: +1 request por artista (~30-50 extras), mas gêneros ficam
  disponíveis. 3 falhas consecutivas item-a-item abortam com warning.
- Progresso visível no fallback item-a-item (evento `artists_fallback`
  a cada 5 artistas).

## [0.8.0-alpha.3] — 2026-04-20

### Corrigido
- `_fetch_artists_genres` em `core/onboard.py` agora é tolerante a 403 do
  Spotify (Dev Mode bloqueia `GET /v1/artists` em alguns apps mesmo sendo
  endpoint público). Em erro, retorna dict vazio e append mensagem em
  `report["warnings"]`; a análise segue com décadas e top artistas
  (gêneros ficam ausentes). Antes a análise completava sem sinal visível
  de falha — user via "Décadas dominantes" mas não "Gêneros dominantes"
  e não sabia por quê.

### Alterado
- `onboard.run` passa a incluir `warnings: list[str]` no report final.
- `maestra init` (flows B e C) conecta `progress_cb` de `onboard.run` e
  imprime progresso ao longo dos fetches (top tracks, biblioteca
  paginada, recently played, análise). Antes a CLI ficava silenciosa
  durante dezenas de segundos em bibliotecas grandes.
- `_print_onboard_results` exibe bloco "Avisos" ao final quando
  `report["warnings"]` não está vazio.

## [0.8.0-alpha.2] — 2026-04-20

### Alterado
- `maestra init` agora **sempre pede ao usuário que crie a playlist manualmente
  no app Spotify** e cole o link. Motivo: Spotify retorna 403 em
  `POST /users/.../playlists` para muitos apps em Development Mode mesmo
  com User Management correto; pular a criação automática vira o fluxo
  padrão em vez de caso-de-exceção. Instrução didática passo-a-passo
  surge antes do prompt.
- `maestra init --auto` em estado B agora exige `--playlist-id` explícito
  (antes tentava criar automaticamente). Mensagem de erro aponta o fix.

## [0.8.0-alpha.1] — 2026-04-20

### Adicionado
- Flag `--playlist-id` em `maestra init` — aponta playlist existente e pula
  a criação. Útil quando o app Spotify está em Development Mode e retorna
  403 em `POST /users/.../playlists` (limitação conhecida; User Management
  + email correto não resolve em todos os casos).
- `run_interactive` e `run_auto` aceitam `playlist_id` (normalizado via
  `config.normalize_playlist_id`).

## [0.8.0-alpha.0] — 2026-04-20

### Adicionado
- `maestra init` — wizard guiado de configuração unificado. Detecta estado
  (A / A2 / B / C) e apresenta menu contextual. Linguagem sem jargão,
  tom caloroso, retry loop com smart exit após 3 falhas consecutivas do
  mesmo tipo.
- Flags `--auto` (sem prompts, requer estado B ou C) e `--json` (saída
  estruturada, implica `--auto`).
- Help topic `maestra help init`.
- Módulo `core/init.py` + `core/init_types.py` com `InitState` e `InitReport`.
- Kwargs `skip_library`, `skip_long_term`, `skip_medium_term`,
  `skip_playlist_creation` em `onboard.run` (usados por `init --auto` e
  `_flow_C_update`).

### Depreciado
- `maestra onboard` — warning em stderr ao rodar. Será removido em v0.9.
  Migração: `maestra init` (interativo) ou `maestra init --auto` (scripts).
  `maestra help onboarding` ganhou banner de depreciação no topo.

### Contratos preservados
- `taste_profile.json`, `onboard_rationale.json` inalterados.
- Tool MCP `onboard_rationale` continua funcionando (lê artefato gerado por
  `init` do mesmo jeito que antes por `onboard`).

## [0.7.0-alpha.1] - 2026-04-20

Cleanup + segurança pós-v0.7.0-alpha.0. Fecha 10 itens S* (segurança)
e 14 itens D* (dead code / refactor) identificados no review, com
suíte ruff zerada.

### Fixed
- **CRÍTICO (S1):** MCP boundary redige secrets antes de retornar
  erros ao cliente (`redact_error_dict` + `redact_str` em todos os
  caminhos de erro). Antes, tokens Bearer do spotipy podiam vazar
  via `str(e)` para o agente LLM.
- **S2:** `PlaybackObserver._append_events` usa `append_jsonl_locked`
  para prevenir intercalação sob writes concorrentes.
- **S3:** `maestra help <topic>` valida topic com regex âncora
  (`^[a-z][a-z0-9_-]*$`) — defesa-em-profundidade contra traversal.
- **S4:** `director.start` envolve `open(log_path)` em context
  manager — fecha o fd no pai após `Popen` (fix fd leak em MCP
  long-lived).
- **S5:** chave `authorization` adicionada ao redactor de audit.
- **S8:** IDs de snapshot usam UTC puro (sem `.astimezone()`) —
  ordenação lexicográfica determinística entre TZs.
- **S9:** tool MCP `onboard_rationale` valida shape (dict com chave
  `suggestions`) e converte `JSONDecodeError` em `UserError`.
- **S10:** `normalize_playlist_id` prefere URIs/URLs canônicas do
  Spotify; fallback permissivo mantido.

### Removed
- `_stub` em `cli/config.py`, `_pid_running` e `_signal_weight` em
  `cli/_common.py` (shims obsoletos).
- Alias `_prune_candidates_fn` em `core/taste.py` (parâmetro de
  `review()` renomeado para `prune_candidates_override`).
- `_flag_keyring_used` e `_flag_keyring_used_get` em `core/storage.py`
  (flag file sem consumidor).
- `_keyring_backend_ok` duplicado em `core/storage.py` (consolidado
  em `core/token_store.py`; doctor usa a versão mais robusta que
  reconhece `null.Keyring`).
- Shims `_prune_candidates` e `_context_review` em `cli/_common.py`
  (inlined em `cli/taste.py`).

### Refactored
- `core/onboard.py` aplica TypedDicts exportados (`SelectedPlaylist`,
  `FailedPlaylist`, `OnboardSignals`, `TrackRationale`,
  `RationaleEntry`).
- `core/curator.curate` usa `TasteProfile.filter_with_artist_info`
  em vez do segundo loop inline.
- `_context_query_candidates` marcado para rework v0.8 + guard
  `len(genres) < 3 → {}`.
- `core/security.py`: docstring documenta limite do regex JWT (S6).

### Style
- Suíte ruff de 26 → 0 erros. `ruff check --fix` + ajustes manuais
  em N806, N818 (noqa justificado), F821 (`from pathlib import Path`
  movido para topo).

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
- `test_total_23_tools` → `test_total_24_tools` (nova tool).

## [0.6.2-alpha.1] - 2026-04-19

Patch cosmético — fecha os 5 Nits do review pós-v0.6.0-alpha.0.

### Fixed
- **N1** — `core/onboard.py`: removidos imports `FailedPlaylist` e
  `SelectedPlaylist` (nunca usados no arquivo).
- **N2** — `core/storage.py`: removidas constantes `_SERVICE`/`_USER`
  (duplicadas e não-usadas; implementação real vive em `token_store.py`).
- **N3** — `core/onboard.py`: docstring de `run()` atualizada
  (referências envelhecidas a "v0.5.3" em `total_cap`, `playlist_selector`
  e seção de expansão removidas; comentários de código inalterados).
- **N4** — `core/client.py`: comentário justifica
  `SPOTIFY_SEARCH_PAGE_LIMIT = 10` (Spotify aceita 50; 10 é escolha
  conservadora para UX do CLI).

### Tests
- **N5** — cobertura de MCP: +3 testes em `test_tools.py` para
  `clear_context` (registry, round-trip, shape de retorno). `onboard`
  já tinha cobertura prévia.

## [0.6.2-alpha.0] - 2026-04-19

Release só de correção — fecha os 8 Minors do review
pós-v0.6.0-alpha.0. Foco no pipeline central de erros:
`MaestraError` propaga para `main()` em `cli/__init__.py:246` onde
`redact_error_dict` + `_print_rich_error` produzem saída estruturada
com `suggested_actions` e `agent_hint`. Zero feature nova.

### Changed (breaking — output de erros no CLI)
- Handlers `cmd_play`, `cmd_pause`, `cmd_next`, `cmd_queue_add`,
  `cmd_play_context` em `cli/basic.py` não engolem mais
  `MaestraError` em `{"error": str(e), "code": "PLAYBACK_ERROR"}`.
  Erros agora seguem o schema `to_human_dict` (`{"error": {"code":
  "RateLimitError", "title": ..., "suggested_actions": [...],
  "agent_hint": ...}}`). **Zero consumidor externo conhecido
  (pre-alpha); impacto restrito à UX de CLI.**
- `cli/onboard._interactive_choose`: `print` + `SystemExit(1)`
  substituído por propagação de `MaestraError` / tradução para
  `SpotifyAPIError`.
- `core/client.py` — `_bucket`/`_breaker` globals → `_BUCKETS` /
  `_BREAKERS` dict keyed por `db_path`. API pública do módulo
  inalterada (`_get_bucket`/`_get_breaker` permanecem).

### Fixed
- **M1** — `onboard._resolve_playlist_name` agora propaga
  `MaestraError` (AuthError/RateLimit/API) em vez de silenciar.
  Fallback `except Exception: return desired` mantido apenas para
  shape inesperada da API.
- **M2** — mesmo padrão em `onboard.run` no bloco de
  `_fetch_own_playlists`: AuthError propaga; fallback reservado
  para erros de parse.
- **M3** — `cli/basic.cmd_status` captura apenas `ConfigError`
  em vez de `Exception` genérico.
- **M4** — rate limiter resets corretamente quando
  `MAESTRA_STATE_DIR` muda entre testes (dict cache por `db_path`).
- **M6** — `onboard._fetch_own_playlists` tem cap de 200 páginas
  (10_000 playlists, hard limit Spotify). Defense-in-depth contra
  loop infinito por `next` fixo de servidor bugado.
- **M7** — ver Changed.
- **M8** — ver Changed.

### Docs
- **M5** — `audit._redact` docstring explicita exact-match
  lowercase em `_SECRET_KEYS` (variantes como `"user_email"` NÃO
  casam).

### Added
- `cli/basic.cmd_queue_context` output agora inclui campo `failed`
  listando tracks que não puderam ser adicionadas à fila (cada
  entry: `{uri, error: to_human_dict(...)}`). Batch não é mais
  abortado pela primeira falha.

## [0.6.1-alpha.0] - 2026-04-19

Release só de correção — fecha os 7 itens Important do review
pós-v0.6.0-alpha.0 (ver `docs/reviews/2026-04-19-v060-post-release.md`).
Zero feature nova, zero breaking no CLI, zero breaking no output
do MCP para clientes válidos. Suite: ~506 (maestra-ai + maestra-mcp).

### Fixed
- **I1** — `storage.write_config` agora usa `atomic_write_json`
  (rename atômico via `os.replace`). Elimina janela de lost-update
  entre daemon director e CLI manual.
- **I2** — `director._record` usa `storage.append_jsonl_locked`
  com `fcntl.LOCK_EX`. Payloads de decisão com `tracks[]` passam
  de PIPE_BUF (~4KB), e o lock evita intercalação de bytes entre
  daemon e `director_once` via MCP.
- **I3** — `audit.log` idem. MCP server + CLI + daemon podiam
  corromper o audit.jsonl em paralelo; agora são serializados.
- **I4** — `snapshot.create` usa `atomic_write_json`. Crash
  mid-write deixa no máximo um `.tmp` residual, nunca um `.json`
  parcial (importante porque `rollback.py` cria safety-snapshot
  justamente quando algo já está dando errado).
- **I6** — `FeedbackPrompter._in_cooldown` guarda `fromisoformat`
  contra state corrompido (edição manual, valor inválido, chave
  ausente). Antes crashava com `ValueError`; agora retorna `False`
  (cooldown expirou). Mesmo padrão de `context.py:44`.

### Added
- **I5** — validação de args MCP contra `inputSchema`. Dep nova
  `jsonschema>=4.0` em maestra-mcp. `tools.call_tool` valida antes
  de invocar o handler; `ValidationError` é traduzido em
  `MCPInvalidArgsError(UserError)` com `agent_hint` específico por
  tipo (minimum, required, additionalProperties, type, enum).
- **`MCPInvalidArgsError`** em `core/errors.py` — subclasse de
  `UserError` com hint per-instance (override do agent_hint de classe).
- **`core.storage.append_jsonl_locked(path, entry)`** — helper
  público para append JSONL serializado com `fcntl.LOCK_EX`.

### Changed (breaking — renames em taste, pre-1.0)
- **I7** — promove 3 símbolos privados para API pública em
  `core/taste.py`:
  - `TasteProfile._is_rejected` → `TasteProfile.is_rejected`
  - `_prune_candidates` → `prune_candidates`
  - `_signal_weight` → `signal_weight`
  Callers atualizados em `core/curator.py`, `core/history.py` e
  `cli/_common.py`. Sem deprecation alias — zero consumidores
  externos conhecidos.

### Tests
- +2 em `TestAppendJsonlLocked` (serialização + concorrência 2×50).
- +1 em `TestCreateAtomicity` (crash simulado em `os.replace`).
- +2 em `TestCooldownCorrupcao` (fromisoformat inválido + chave ausente).
- +4 em `TestValidacaoArgs` (MCP: additionalProperties, minimum, required, válido).
- 1 teste existente atualizado (`test_history_import_outside_rejeita_signal_invalido`)
  para refletir que validação agora é no boundary MCP.

## [0.6.0-alpha.0] - 2026-04-19

Primeiro bump de minor desde v0.5.0. Formaliza contrato do
`playlist_selector` e do `expansion_info` do onboard via TypedDict.
**Hard break** do contrato antigo (1-arg → 2-arg) — pre-1.0, 1 caller
interno, zero agentes externos conhecidos. Sub-projeto A do backlog
consolidado (itens #27, #29). Suite: ~462 (maestra-ai).

### Breaking
- `playlist_selector` agora é
  `Callable[[list[OwnPlaylist], ExpansionContext], list[str]]` — 2
  argumentos. Selectors antigos com 1 argumento levantam `TypeError`
  em runtime. Sem deprecation path.

### Added
- **`core/onboard_types.py`** com `OwnPlaylist`, `ExpansionContext`,
  `SelectedPlaylist`, `FailedPlaylist`, `ExpansionReason`,
  `ExpansionInfo`, `PlaylistSelector`. Contratos centralizados para
  consumo por core, CLI, MCP futuro e agentes externos via stubs.
- **`ExpansionContext` passado ao selector** — `total_cap`,
  `current_total`, `remaining`. Selector programático não precisa
  mais descobrir esses valores fora de banda.
- **Prompt interativo mostra current_total real**: antes caía em 0
  porque CLI não tinha como saber; agora `_interactive_selector` usa
  `ctx["current_total"]`.

### Changed
- `_fixed_selector` e `_interactive_selector` em `cli/onboard.py`
  aceitam `(playlists, ctx)`. `_fixed_selector` ignora `ctx`
  (IDs fixos via `--expand-playlists`).
- `expansion_info` formalmente anotado como `ExpansionInfo`. Estrutura
  runtime inalterada (flat, 7 campos).
- `_fetch_own_playlists` retorna `tuple[list[OwnPlaylist], int]` com
  tipo formal.

### Tests
- +3 em `TestExpansionContextShape` (total_cap, current_total, remaining).
- +1 regressão de hard break (selector 1-arg → TypeError).
- +1 em `TestPromptUsaCtxReal` (prompt recebe valores do ctx).
- 23+ testes existentes atualizados para assinatura 2-arg (mesma
  contagem).

## [0.5.7] - 2026-04-19

Terceiro lote do backlog consolidado — polimento de UX, docstrings
e observabilidade. Itens 15-22 fechados; #23 já tinha sido feito
com #11 em v0.5.6. Suite: 457 (maestra-ai).

### Changed
- **#17 distinção "zero playlists" vs "todas vazias"**:
  `_fetch_own_playlists` agora retorna tupla `(usable, empty_count)`.
  Novo `reason="only_empty_playlists"` + campo
  `own_playlists_empty_count` em `expansion_info`. Mensagem humana
  em `_print_report` adapta o texto conforme contagem.
- **#19 `selected_playlists` com `{id, name}`**: em vez de só IDs,
  `expansion_info.selected_playlists` guarda dicts com nome. Relatório
  humano mostra nomes (primeiras 3) em vez de só contagem.
- **#16 fallback texto do checkbox com cap**: quando `questionary`
  cai em runtime e o usuário tem >20 playlists, mostra top 20 por
  `track_count` em vez de imprimir a lista inteira. `"all"`/índices
  operam sobre o subset mostrado.

### Added
- **#20 `progress_cb` em `_fetch_own_playlists`**: CLI pode atualizar
  Rich Progress com "listando N playlists" em bibliotecas grandes,
  elimina silêncio de 10s+ em usuários com 500+ playlists.

### Docs
- **#15 + #21 docstring expandida de `onboard.run()`**: seções
  "Parâmetros", "Expansão por playlists próprias", "Semântica de
  pesos" (explicita dedup do peso "playlist"=2 em múltiplas playlists),
  "expansion_info no report" (vocabulário fechado de `reason`).
- **#18 docstring de `_prompt_expansion_confirm`**: avisa que caller
  precisa ter pausado Rich Progress antes da invocação.
- **#22 doc explícita das 3 env vars XDG no README**: tabela com
  variável, default, conteúdo; aviso de independência;
  comando completo de limpeza total.

### Já fechado em outra release (anotação)
- **#23 `_rotate` do audit sem lock**: resolvido junto com #11 em
  v0.5.6 (mesmo commit `a6ef3a7`).

## [0.5.6] - 2026-04-19

Segundo lote do backlog consolidado (itens 10-14 + testes 24-26).
Item #12 descoberto como falso positivo do relatório Explore (já
resolvido em v0.4.4 com cobertura de teste). Suite: 442 unit + 13
E2E = 455 passed (maestra-ai).

### Fixed
- **#11 FileLock em `_rotate` de snapshot e audit**: daemon + CLI
  concorrentes podiam duplicar ou perder arquivos no archive durante
  rotação. Adiciona `<dir>/.rotate.lock` em ambos. audit re-verifica
  existência do ativo após o lock para o caso de outra rotação ter
  corrido em paralelo.
- **#13 side-effect de `os.makedirs` removido do import de
  `cli/_common.py`**: `import` não modifica mais o filesystem.
  `storage.ensure_dirs()` continua sendo chamado on-demand pelos
  callers que escrevem. BASE_DIR segue como string avaliada no
  import (sem efeito no fs).

### Changed
- **#10 `expansion_info.reason` com vocabulário fechado**:
  `"selector_not_provided"` / `"cap_already_reached"` (novo) /
  `"no_own_playlists"` / `"selector_returned_empty"` (substitui
  `"user_skipped"`) / `"ok"` (substitui `None` em sucesso). Campo
  sempre preenchido — consumidores JSON não tropeçam mais em
  `if reason:`. CLI `_print_report` traduz valores técnicos para
  humanos. Breaking change mínimo: nada interno chamava
  `"user_skipped"`.

### Tests
- **#14 redação end-to-end em `error()`**: TestErrorEndToEndRedact
  valida que Bearer/access_token embutidos em mensagem passam pelo
  redator antes de stderr. Substitui teste antigo tautológico que
  validava `_redact()` em isolamento.
- **#24 fluxo interativo real do selector**: TestInteractiveSelectorFluxoReal
  mocka `questionary.confirm`/`checkbox` via `sys.modules` e exerce
  confirmar+escolher, confirmar+vazio, negar confirmação, lista
  vazia dispara mensagem humana.
- **#25 edge cases do selector**: exceção do selector propaga (core
  não swallow); IDs fora da lista oferecida viram entrada em
  `failed_playlists`.
- **#26 E2E ampliado**: +5 cenários (quickstart banner, `taste` sem
  sub-sub, `config list` redactando secret, help topics). Total
  E2E: 13 (era 8).

### Descartado (falso positivo do relatório Explore)
- **#12 `datetime.fromisoformat` sem guard em `context.show`**: já
  resolvido em v0.4.4 (HIGH-1) com `try/except (ValueError, KeyError,
  TypeError)` e `self.clear()`. Teste
  `test_show_limpa_state_com_iso_malformado` cobre o cenário.

## [0.5.5] - 2026-04-19

Primeiro lote do backlog consolidado (itens 1-9) — altos + médios de
alto ROI. Ver `docs/reviews/2026-04-19-backlog-consolidado.md`.
Suite: 429 (maestra-ai).

### Fixed
- **#1 `DeviceError(MaestraError)`** substitui `RuntimeError` em
  `SpotifyController.ensure_active_device`. Contrato padronizado
  com `probable_causes` e `suggested_actions` (abrir Spotify, rodar
  doctor, listar devices). Painel Rich correto em vez de genérico.
- **#2 `safe_call` redacta str(e)**: complementa o fix P0-R1 de
  `error()` (v0.5.0). Usado em `cmd_status`; antes podia vazar token
  Bearer em exceções de spotipy.
- **#5 `taste.save/restore` limpam `.tmp` órfão**: helper
  `_write_atomic` com `try/except OSError + os.unlink` e tradução
  para `StorageError` com `where={path, tmp_path}`. Antes, falha de
  `os.replace` (disco cheio, permissão) deixava `.tmp` preso e
  memória diverge do disco.

### Added
- **#6 + #7 `expansion_info.failed_playlists`**: lista
  `[{id, reason}]` (reason truncada em 80 chars) rastreando
  playlists que falharam durante fetch da expansão (race, timeout,
  401 parcial). Antes engolidas silenciosamente; agora visíveis no
  `--json` e resumidas no modo human ("+N faixas de K playlist(s)
  (X falhou/falharam)").
- **#8 `--expand-playlists` valida formato via `normalize_playlist_id`**:
  aceita ID puro, URI `spotify:playlist:...` ou URL
  `open.spotify.com/playlist/...?si=...`. ID malformado → `UserError`
  imediato em vez de falha silenciosa no core.
- **#9 mensagem dinâmica do prompt de expansão**: `_prompt_expansion_confirm`
  usa `total_cap` real vindo de `args.total_cap` (mostra gap se
  `current_total` conhecido). Antes hard-coded "5000 faixas" mentia
  quando usuário passava `--total-cap=1000`.

### Changed
- **#3 `sp.playlist_items` com `fields` restrito**:
  `"items(track(uri,name,artists(name))),next"` reduz payload em ~80%.
  Onboard acelera proporcionalmente em bibliotecas grandes e gasta
  menos rate limit.
- **#4 filtro `track_count=0` movido para o core**:
  `_fetch_own_playlists` já retorna apenas playlists utilizáveis.
  Selectors externos (MCP, scripts, testes) não precisam duplicar.

### Tests
- `test_client.py`: +3 em TestEnsureActiveDeviceError
- `test_cli_common.py`: +3 em TestSafeCallRedact
- `test_onboard.py`: +3 (filtro vazias, fields restrito, falhas parciais)
- `test_taste_restore.py`: +2 em TestAtomicWriteCleanup
- `test_cli_onboard.py`: +5 (validação --expand-playlists com URL/URI,
  UserError em malformado, TestPromptExpansionConfirmDinamico x2)
- Total 429 passed (era 414).

## [0.5.4] - 2026-04-19

Patch blocker pós code-review da v0.5.3: dois críticos e um de
segurança (PII). Suite: 414 (maestra-ai).

### Fixed
- **C1 — `KeyboardInterrupt` durante `questionary` abortava onboard
  inteiro**: Ctrl+C no prompt de expansão quebrava toda a execução,
  descartando top/saved/recent já buscados. Agora `_interactive_selector`
  captura `KeyboardInterrupt` em `_prompt_expansion_confirm` e
  `_prompt_playlists_checkbox` e degrada para `[]` — core persiste
  normalmente o que já coletou.
- **C2 — loop infinito potencial em `_fetch_own_playlists`**: se
  Spotify retornar `items=[]` com `next != None` (rate-limit soft,
  mesmo sintoma do bug 3 corrigido em `_fetch_saved`), offset ficava
  preso em 0. Guarda `if not items: break` adicionada, consistente
  com `_fetch_playlist_tracks`.
- **M7 (PII) — email não era redactado em audit logs nem em
  `MaestraError.where`**: `_SECRET_KEYS` não cobria `email`. Agora
  cobre. `country` e `product` permanecem visíveis (metadata útil
  para diagnóstico, não-PII).

### Tests
- `test_onboard.py`: +1 (test_guarda_contra_loop_infinito_items_vazio_com_next)
- `test_cli_onboard.py`: +2 (KeyboardInterrupt no confirm e no checkbox)
- `test_audit.py`: +1 classe TestRedactPII (+2 casos)
- Total 414 passed (era 409).

## [0.5.3] - 2026-04-19

Expansão do onboard: se Liked Songs + top tracks + recently played
deixam o total abaixo do teto desejado, oferece complementar com
playlists criadas pelo próprio usuário. Também consolida hotfix da
regressão do fix 6 (v0.5.2) encontrada na validação end-to-end sob
agente IA. Suite: 409 (maestra-ai).

### Added
- **Expansão opcional por playlists próprias** (solicitação do Léo):
  quando total de faixas únicas < `--total-cap` (default 5000),
  onboard pergunta se o usuário quer expandir e exibe checkbox
  interativo (questionary) com suas próprias playlists (filtro
  `owner.id == me.id` — seguidas ficam fora). Peso 2 para curadoria
  indireta (entre recent=1 e saved=3). Nova dep: `questionary>=2.0`.
- **Flags `--total-cap`, `--no-expand`, `--expand-playlists`** no
  onboard. `--expand-playlists "id1,id2"` desliga o prompt e aplica
  IDs fixos — ideal para agentes IA scriptarem o fluxo.
- **Mensagem calorosa** quando usuário não tem playlists próprias:
  "Você ainda não criou nenhuma playlist no Spotify — tudo bem, vou
  aprender seus gostos ao longo das nossas interações."
- **Novo campo `playlist_expansion`** no report de onboard
  (`{attempted, offered_playlists, selected_playlists, tracks_added,
  reason}`). `reason` é `no_own_playlists`, `user_skipped` ou `null`.

### Fixed
- **Regressão do fix 6 (v0.5.2)**: `set_defaults(skip_deps=True)` no
  parser de grupos vazava para sub-subparsers via herança de defaults
  do argparse. `maestra taste show` quebrava com
  "cmd_taste_show() missing 1 required positional argument: taste".
  Agora `group_help_handler` marca o próprio handler com atributo
  `_is_group_help=True`; main() detecta via `args.func._is_group_help`.

### Tests
- `test_onboard.py`: +4 em TestFetchOwnPlaylists, +3 em
  TestFetchPlaylistTracks, +1 em TestPlaylistWeight, +4 em
  TestPlaylistExpansion.
- `test_cli_onboard.py`: +5 em TestPlaylistSelector.
- `test_cli_smoke.py`: +1 regressão (grupo com sub-sub não pula deps).
- Total 409 passed (era 394).

## [0.5.2] - 2026-04-19

Polimento pós primeira instalação end-to-end. Foco: o que bloqueou o
Léo no first-run real e o que saiu silenciosamente errado. Fecha 6
bugs de código + 3 gaps de documentação. Usuários existentes precisam
rodar `maestra auth login` novamente para obter token com os novos
scopes. Suite: 393 (maestra-ai).

### Fixed
- **Paginação de Liked Songs via campo `next`** (bug 3): heurística
  antiga `len(items) < 50 → fim` podia parar cedo se Spotify mandasse
  página intermediária parcial (rate limit soft, jitter), perdendo
  resto da biblioteca silenciosamente. Agora usa `resp['next']`;
  fallback para heurística antiga quando campo ausente.
- **403 em create playlist traduzido para `PlaylistCreateForbiddenError`**
  (bug 2): antes bubblava stack trace cru do spotipy. Nova classe
  com 4 probable_causes (Development Mode, User Management,
  propagação, Premium) e `suggested_actions` apontando dashboard e
  contorno via `--playlist-id`.
- **JSON mode do onboard não polui stdout** (fix colateral do bug 4):
  Rich Progress é desligado em `--json` — antes escrevia "⠋
  Iniciando..." antes do JSON, quebrando parsing por agente.

### Changed
- **Scopes OAuth incluem `user-read-email` e `user-read-private`**
  (bug 1): sem eles, `/v1/me` retornava email/country/product como
  `None`, inviabilizando diagnósticos. **Tokens antigos continuam
  funcionando** mas com leitura restrita — refazer login recomendado.

### Added
- **Warning quando `--seed-playlist > 50`** (bug 4): Spotify limita
  `top_short_term` a 50 faixas via API. Pedir mais era silenciosamente
  clampeado. Warning Rich em modo human; campo `warnings` no report JSON.
- **`--playlist-id` + `--playlist-name` renomeia no Spotify** (bug 5):
  caso típico: usuário cria playlist vazia (Spotify nomeia como
  "My Playlist #N"), passa link, queria rebatizar para "Maestra".
  `playlist_change_details` é chamado se nome atual diferir. Falha
  do rename não bloqueia onboard.
- **Grupos sem sub-subcomando mostram help** (bug 6): `maestra taste`
  (e `auth`/`config`/`playlist`/`context`/`director`/`flow`) sem
  sub-subcomando agora imprime help formatado e retorna 0 em vez de
  argparse error cru "required: taste_command" e exit 2. Novo helper
  `cli.group_help_handler()`.
- **Troubleshooting em `help onboarding`** (docs 7): seção com 3 casos
  reais — 403 Forbidden + contorno, env legadas no `.bashrc`, token
  antigo sem scopes.
- **Aspas simples nos exemplos de `--playlist-id`** (docs 8): URLs do
  Spotify contêm `&` e `?` que o shell consome sem aspas.
- **Bloco Troubleshooting no README** (docs 9).

### Tests
- `test_auth.py`: +1 classe `TestScopes` (2 casos).
- `test_onboard.py`: +1 classe `TestPlaylistCreate403` (2 casos),
  +1 classe `TestPlaylistRename` (3 casos), `TestFetchSaved`
  reescrita com `next`-aware fixtures (+2 casos novos).
- `test_cli_onboard.py`: +2 casos de warning de seed.
- `test_cli_smoke.py`: +1 parametrizado com 7 grupos.
- Total 393 passed (era 374).

## [0.5.1] - 2026-04-19

Polimento de primeira impressão. Cinco achados da simulação de usuário
novo: README raso, `doctor` mentindo sobre Config, erro enganoso de
`auth setup` sem TTY, `--help` de `auth setup` sem pré-requisitos
Spotify, e ausência de quickstart ao rodar `maestra` sem args.
Suite: 374 passed (maestra-ai).

### Fixed
- **`doctor.check_config` detecta placeholders e campos incompletos**:
  antes reportava "Config ✓ ok" mesmo com apenas `client_id` presente,
  ou com `redirect_uri=https://example.com/callback`. Agora valida os
  três campos obrigatórios e reconhece placeholders óbvios copiados
  de docs (`your_client_id`, `example.com`, `localhost`, `xxx`, etc.).
- **Erro de `auth setup` sem TTY tem categoria apropriada**: nova classe
  `NonInteractiveError` (subclasse de `UserError`) com title
  "Entrada interativa indisponível" e causes apontando TTY/pipe em vez
  de "flag fora do range permitido".

### Added
- **`maestra` sem subcomando mostra quickstart banner**: painel Rich
  compacto apontando `maestra help onboarding`, `maestra doctor` e
  `maestra onboard`. Substitui o wall-of-text do argparse help, que
  deixava usuário novo perdido entre os subcomandos.
- **`maestra auth setup --help` lista pré-requisitos Spotify**:
  description com os 3 passos (criar app no dashboard, copiar
  credenciais, registrar redirect HTTPS) + explicação de por que
  `localhost` é rejeitado.
- **README expandido**: instalação via `uv sync`, fluxo de 5 passos
  do primeiro uso, tabela dos 2 pacotes do monorepo, ponteiros para
  docs internas.

### Tests
- `test_doctor.py`: +4 casos (placeholder redirect, placeholder client_id,
  secret ausente, redirect_uri ausente).
- `test_auth.py`: +1 classe `TestAuthSetupCLINonTTY`.
- `test_cli_main.py`: +1 classe `TestQuickstartBanner` (2 casos).
- `test_cli_smoke.py`: +1 caso (`test_auth_setup_help_cita_dashboard_e_redirect_https`);
  teste antigo `test_help_sem_subcomando_falha` substituído por
  `test_sem_subcomando_mostra_banner_e_retorna_zero`.

## [0.5.0] - 2026-04-19

Polimento pós-v0.4.5. Fecha os 6 achados HIGH/MEDIUM remanescentes
do code review. Sem quebra de API pública (apenas SNAP_ID ficou mais
restritivo — mas o formato já era o canônico gerado pelo próprio
código). Suite total: 374 (maestra-ai) + 35 (maestra-mcp) = 409 passed.

### Fixed
- **`taste.restore` valida schema antes de sobrescrever** (HIGH-2):
  payload malformado levanta `ValidationError`; perfil em memória e
  em disco permanecem intactos.
- **`_SNAP_ID_RE` estrita** (HIGH-4): só aceita formato canônico
  `YYYY-MM-DD-HHMMSS-uuuuuu-<operation>`. Rejeita `../`, espaços,
  strings curtas — defesa em profundidade contra IDs maldosos em
  `snapshot.load()`.
- **Redação de secrets contextual** (MEDIUM-1): URIs de track,
  playlist IDs e nomes longos não são mais mascarados. Mantém
  redação de `Bearer ...`, `access_token=...`, `refresh_token=...`,
  `client_secret=...`, `api_key=...` e JWTs. Logs de debug ficam
  legíveis sem comprometer segurança.
- **Sonda de processo Spotify portável** (MEDIUM-2): novo
  `core/process.py::is_spotify_running()` com fallback
  pgrep → tasklist → None. `client.ensure_active_device` trata
  None como "desconhecido, prossegue e deixa API falar". Remove
  dependência hard em `pgrep` (Linux-only).

### Added
- **`maestra doctor --reset-breaker`** (HIGH-3): zera o circuit
  breaker persistente. Útil quando operador corrigiu a causa-raiz
  e não quer esperar o cooldown. `PersistentCircuitBreaker.reset()`
  exposto na classe; `ratelimit.reset_breaker()` livre para callers
  externos.
- **Rotação do audit.log por tamanho** (MEDIUM-3): `_MAX_SIZE_BYTES
  = 10MB` força rotação mesmo antes da idade. Evita crescimento
  descontrolado em uso intensivo via MCP.

### Tests
- Novos módulos: `test_taste_restore`, `test_ratelimit_breaker_reset`,
  `test_process`, `test_audit_rotation`. Acréscimos em
  `test_snapshot`, `test_security`, `test_cli_doctor`.
- `test_snapshot.test_load_rejects_malformed_snapshot` e
  `test_load_rejects_non_dict_snapshot` foram atualizados: IDs
  hardcoded `"fake-snap"` e `"bad"` trocados por IDs canônicos para
  não colidir com a regex mais estrita; intenção original do teste
  (validar detecção de conteúdo malformado) preservada.

## [0.4.5] - 2026-04-19

Melhorias de onboarding e configuração. Reforça o peso do sinal
explícito de curadoria (Liked Songs), permite apontar playlist
existente em vez de sempre criar nova, e adiciona subcomando
`maestra config` para setup sem edição manual de JSON.

### Added
- **`maestra config {get,set,list}`**: subcomando CLI para leitura e
  escrita do `config.json`. `set playlist_id` aceita ID puro, URI
  (`spotify:playlist:...`) ou URL (`open.spotify.com/playlist/...`)
  e normaliza automaticamente para o ID canônico de 22 chars. `list`
  redacta `client_secret`. Rejeita keys fora do whitelist.
- **Onboard interativo** (`maestra onboard` em TTY): menu `[1]` criar
  playlist nova ou `[2]` apontar existente. Opção 2 lista até 20
  playlists do usuário e aceita seleção por número OU paste de
  ID/URI/URL. Três tentativas inválidas → aborta com exit 1.
- **Flags `--playlist-id` e `--non-interactive`** em `onboard`:
  permitem fluxo não-interativo explícito (útil em scripts e MCP).
  `--non-interactive` sem `--name`/`--playlist-id` erra cedo.
- **`core.onboard.run(existing_playlist_id=...)`**: novo kwarg que
  pula a criação de playlist e usa a existente como destino de
  seed. Resolve nome via `sp.playlist(pid, fields="name")`.
- **`core.config.normalize_playlist_id(value)`**: função pública que
  consolida parsing de ID/URI/URL num único lugar. Levanta
  `ValueError` em formato inválido.

### Changed
- **Repesagem de sinais no onboard:** `WEIGHTS["saved"]` elevado de
  **1 → 3** (igual a `top_long_term`). Motivação: ❤️ é declaração
  explícita de curadoria, merece peso comparável ao hábito
  comportamental sustentado. `taste_profile` de usuários que já
  rodaram onboard será reponderado no próximo run (não é breaking —
  profile é regenerado).
- **Cap da Liked Songs:** `_MAX_SAVED` de 1000 → **5000**. Evita
  perda de sinal em bibliotecas médias/grandes. Flag nova
  `saved_cap` em `core.onboard.run` permite override.

### Tests
- +44 testes: `test_core_config` (normalize_playlist_id),
  `test_cli_config` (get/set/list + redação), `test_onboard`
  (existing_playlist_id paths), `test_cli_onboard` (TTY detection,
  interactive menu, paste paths, retry cap). Suite total: 350
  (maestra-ai) + 35 (maestra-mcp) = **385 passed**.

## [0.4.4] - 2026-04-19

Quarto hotfix da série v0.4. Fecha 2 BLOCKERs, 4 CRITICALs e 1 HIGH do
code review pós-v0.4.3. Suite continua 100% verde (347 testes).

### Segurança
- **Removido ID de playlist pessoal** commitado inadvertidamente em
  `cli/_common.py` (BLOCKER-1). O ID permanece no histórico git;
  usuários afetados devem considerar a exposição e, se aplicável,
  trocar a visibilidade da playlist no Spotify.
- **`FileTokenStore` fecha janela TOCTOU** (CRITICAL-3): antes, o
  token era gravado via `atomic_write_json` e só depois recebia
  `chmod 600` — deixando uma janela onde o arquivo era world-readable
  (ou o que o umask permitisse). Agora `atomic_write_json` aceita
  `mode=0o600` e o chmod acontece no `.tmp` antes do `os.replace`.

### Fixed
- **`cli/_common.py::PLAYLIST_ID` removido** (BLOCKER-1): substituído
  por `resolve_playlist_id()` que lê `storage.read_config()["playlist_id"]`
  e levanta `ConfigError` se ausente. Callers atualizados: `basic`,
  `playlist`, `taste`, `history`. `_build_deps` ignora `ConfigError`
  para subcomandos que não precisam (auth, doctor, onboard).
- **Director daemon respawn** (BLOCKER-2): `cmd_director_run` agora
  captura `MaestraError` (log warning) e `Exception` (log exception)
  com backoff exponencial limitado a `args.interval`. Antes, qualquer
  falha matava o daemon e deixava PID file órfão.
- **`director.pid` path unificado** (CRITICAL-1): `doctor.check_director`
  usava `state_dir()/director.pid` enquanto o daemon escreve em
  `data_dir()/director.pid`. Doctor reportava "parado" para daemon
  vivo. Agora doctor importa `_pid_file` de `core.director`.
- **MCP `director_once`** (CRITICAL-2): `deps.build_deps` construía
  `MusicDirector` com `playlist_id=None` hardcoded, crashando em
  `playlist_tracks(None)`. Agora usa `resolve_playlist_id()`;
  falha é tipada (via core), não `TypeError` surpresa.
- **Payloads degradados Spotify** (CRITICAL-4): `client.py` (now,
  search, top_tracks, top_artists, _track_summary) e
  `onboard._fetch_saved` acessavam `track['name']` /
  `track['artists'][0]['name']` direto. Agora usam `.get()` com
  defaults e pré-filtram `track=None` / `artists=[]`.
- **`ContextState.show()` ISO malformado** (HIGH-1): `datetime.fromisoformat`
  sem try/except crashava em state corrompido. Agora captura
  `(ValueError, KeyError, TypeError)` e limpa o state.

### Changed
- **`storage.atomic_write_json`**: novo kwarg `mode: int | None = None`
  para aplicar chmod ao arquivo temporário antes do rename atômico.
  Backward-compatible (kwarg opcional).
- **`cli/history outside-playlist --playlist-id`**: default agora é
  resolvido via config quando omitido, em vez de constante hardcoded.

## [0.4.3] - 2026-04-18

Terceiro hotfix da série v0.4. Fecha H2 do code review pós-v0.4.2:
refatora `HistoryAnalyzer.import_outside` para aceitar `signal` e
expõe esse controle via MCP. Centraliza a lógica de sinal contextual
no core, eliminando divergência silenciosa entre CLI e MCP. Suite
continua 100% verde.

### Changed
- **`HistoryAnalyzer.import_outside`** (H2): aceita kwarg
  `signal: str = "good"` validado contra `{"good", "bad", "skip"}`.
  Peso derivado de `core.taste._signal_weight(signal)`. Antes, signal
  era hardcoded `"good"` com peso fixo 1. Resultado ganha campos
  `signal` e `recorded_signals`.
- **CLI `history import-outside`** (H2): agora delega ao
  `core.HistoryAnalyzer.import_outside`, repassando `--signal`.
  Remove duplicação de `record_context_signal` que existia no CLI.
  Bookkeeping via `taste.record_added` permanece no CLI (preocupação
  distinta do sinal contextual).
- **`history_import_outside` MCP** (H2): schema expõe `signal`
  (enum `good/bad/skip`, default `good`). Handler propaga ao core.
  Antes, não era exposto para evitar divergência silenciosa com a
  constante `"good"` hardcoded no core.

### Tests
- `+3` em `test_history.py`: signal bad, signal inválido, default good.
- `+1` em `test_cli.py`: propagação de signal bad via CLI.
- `+2` em `test_tools.py` (MCP): propagação de signal, rejeição de
  signal inválido. `+1 assert` no teste de defaults.
- Total: 308 (maestra-ai) + 33 (maestra-mcp) = 341 passing.

## [0.4.2] - 2026-04-18

Segundo hotfix da série v0.4. Pendências não-críticas do code review
pós-v0.4.1 — dívidas de consistência, performance e observabilidade
no stack MCP. Suite continua 100% verde.

### Added
- **`playlist_prune` MCP** (H3): schema expõe `top` (1..100, default 20)
  e propaga ao `Curator.prune`. Alinha com o subcomando CLI.
- **Auditoria de exceção não-tratada** (H4): `server._build_call_tool_handler`
  envolve `call_tool` em try/except que converte qualquer exceção em
  dict `{error: {code: InternalError, ...}}` e garante `audit.log` no
  caminho de falha. Antes, erros fora do registry pulavam a trilha.
- **Validação de `disabled_tools`** (M5): `list_tools` loga warning
  quando `config.json::mcp.disabled_tools` contém nomes não presentes
  no registry (typo, tool removida). Não bloqueia.

### Changed
- **`history_outside_playlist` MCP** (M4): sem `playlist_id` configurado,
  retorna shape canônico com contadores em 0 e listas vazias, em vez
  do dict divergente `{outside, note}`. Elimina branch no consumidor.
- **`_disabled_tools`** (M3) agora cacheado por mtime de `config.json`.
  Reloads continuam automáticos quando o usuário edita o arquivo.
- **`deps._CACHE`** (M1): leitura/escrita protegidas por `threading.Lock`
  via double-checked locking. Hardening para SDKs MCP que despacham
  handlers em thread pool.
- **`audit._redact_result`** (M2): lista top-level vira `{items_count: N}`
  em vez de serializar payload inteiro. Fecha vazamento teórico em
  handlers MCP que retornam `list` (ex.: `devices`, `search`).

### Docs
- **CHANGELOG v0.4.0** (H1): nota retroativa sobre a regressão temporária
  dos flags `--count/--outside-*` em `director.start`. Corrigido em v0.4.1;
  nota preserva o registro histórico.

### Tests
- 6 testes novos: `test_tools.py` (+2 — `top`, shape consistente),
  `test_server.py` (+3 — audit em exceção, cache mtime, warning de
  nome inválido), `test_deps.py` (+1 — thread safety), `test_audit.py`
  (+1 — lista top-level).

## [0.4.1] — 2026-04-18

Hotfix baseado em code review do v0.4.0. Corrige um bloqueador no MCP,
uma regressão de propagação de flags no Director e alinha defaults para
reduzir risco operacional.

### Fixed
- **MCP rollback handler** (B1, blocker): `_rollback` chamava `rollback_to`
  sem `apply_state_fn`, quebrando qualquer rollback real que não fosse
  `list:true`. Handler agora replica a lógica do subcomando CLI, montando
  `current_state_fn` e `apply_state_fn` via `deps['taste']` e
  `deps['context_state']`.
- **Director `start()` ignorava 4 flags** (C1, critical): CLI aceitava
  `--count/--outside-min-plays/--outside-count/--outside-recent-limit`
  via argparse, mas `core.director.start()` descartava-as silenciosamente.
  Os parâmetros agora fazem parte da assinatura de `start()` e são
  propagados ao subprocess.

### Changed
- **MCP `onboard` default agora é `dry_run=True`** (M6): alinhamento com
  `playlist_prune` e `history_import_outside`. Chamada sem argumentos não
  cria mais playlist real. Para efetivar, passe `dry_run:false` explícito.
- **MCP `history_import_outside` defaults alinhados à CLI** (H2):
  `count=5` (era 10), `min_plays=1` (era 2). Adiciona `recent_limit=50`
  ao schema. `signal` não exposto (core não suporta; divergência
  documentada para follow-up).

## [0.4.0] — 2026-04-18

Fase 4 do roadmap. Transforma a Maestra em ferramenta integrada a agentes
de IA via MCP stdio server. Segue design em
`docs/superpowers/specs/2026-04-18-v040-mcp-server-design.md`.

### Added
- **Pacote `maestra-mcp`** (workspace) — MCP stdio server com 23 tools:
  - Playback (7): `now`, `play`, `pause`, `skip`, `queue`, `search`, `devices`
  - Contexto (3): `set_context`, `get_context`, `clear_context`
  - Curadoria (1): `curate`
  - Análise (3): `flow_review`, `taste_review`, `history_outside_playlist`
  - Manutenção (3): `playlist_prune`, `history_import_outside`, `rollback`
  - Director (4): `director_start`, `director_stop`, `director_status`, `director_once`
  - Onboard/Doctor (2): `onboard`, `doctor`
- Schema JSON estrito por tool (validação no server).
- Allow-list `disabled_tools` em `config.json::mcp.disabled_tools`.
- Audit log em toda chamada MCP (redact automático v0.2.4 + v0.3.0).
- `docs/MCP.md` — guia por agente (Claude Code, Cursor, Codex).
- `maestra help mcp` — topic conceitual.

### Changed (refactors R1-R4)
- **R1** `cli/_common.py::_context_review` movido para
  `core/taste.py::review(profile, tracks, context, top)`. CLI delega.
- **R2** `cli/playlist.py::cmd_playlist_prune` lógica extraída para
  `core/curator.py::Curator.prune(playlist_id, context, confirm, top)`.
- **R3** `MusicDirector._safe_outside_candidates` extraído para
  `core/history.py::HistoryAnalyzer.import_outside(playlist_id, context, confirm, count, min_plays, taste)`.
- **R4** `cli/director.py::cmd_director_start/stop/status` promovidos
  para funções livres em `core/director.py` (consumem PID file em
  `data_dir()/director.pid` via `atomic_write_json` v0.2.5). CLI vira
  thin wrapper.

### Tests
- ~60 testes novos distribuídos em test_taste (1), test_curator (2),
  test_history (2), test_director (5), test_deps (2), test_server (3),
  test_tools (15+). Suite: 292 → ~350 passed.

### Notes
- Fora de escopo: daemon IPC via unix socket (v0.5+), progress
  notifications em `onboard`/`curate` (SDK MCP-dependente, nice-to-have).
- Publicação PyPI de `maestra-ai` e `maestra-mcp` é v0.6.0 (Plano 6).

### Notas
- Refactor R4 (`director.start/stop/status`) introduziu regressão
  temporária onde os flags
  `--count/--outside-min-plays/--outside-count/--outside-recent-limit`
  eram aceitos pelo argparse mas silenciosamente ignorados. Corrigido
  em v0.4.1. Se você passou esses flags em v0.4.0, verifique que o
  comportamento esperado foi aplicado.

## [0.3.2] — 2026-04-18

Segundo hotfix revelado pela validação real (primeira execução de
`maestra auth login` em terminal TTY com credenciais reais).

### Fixed
- **`_NoopCacheHandler` em `core/auth.py`** não herdava de
  `spotipy.cache_handler.CacheHandler`. spotipy 2.26+ faz
  `assert issubclass(cache_handler.__class__, CacheHandler)` no
  `SpotifyOAuth.__init__` e crasha com `AssertionError` — bloqueando
  `maestra auth login`. Bug silencioso nas v0.3.0/v0.3.1 porque todos
  os testes de login mockavam `SpotifyOAuth` e nunca exercitavam o
  constructor real.

### Tests
- 2 testes novos em `test_auth.py::TestNoopCacheHandler` validando:
  (a) `_NoopCacheHandler` é subclasse de `CacheHandler`,
  (b) `SpotifyOAuth` real instancia sem assertion error. Esse segundo
  teste previne recorrência — nenhum mock, só o constructor real.
  Suite: 290 → 292 passed.

## [0.3.1] — 2026-04-18

Hotfix de dois bugs revelados na primeira validação end-to-end da v0.3.0
com credenciais reais.

### Fixed
- **`_InMemoryCacheHandler` em `core/client.py`** — dict do cache agora
  inclui `expires_at=0` (força refresh imediato) e `scope` (casa com
  DEFAULT_SCOPES). Em v0.3.0 populava só `{"refresh_token": ...}`,
  spotipy descartava no `validate_token` e caía em fluxo OAuth
  interativo que falha em ambiente não-TTY com `EOFError` — silenciando
  completamente o TokenStore. Controller ficava como se sem token.
- **`SpotifyOauthError` propagado cru em `_call_spotify`** — não tem
  atributo `http_status`, então o handler genérico não pegava.
  Agora capturado especificamente e convertido em `AuthError` com
  sugestão `maestra auth login`. Casos típicos: refresh token inválido
  (rotação de client_secret, client_id trocado, revogação remota).

### Tests
- 2 testes novos em `test_client.py`: validação de `expires_at` e
  `scope` no cache handler; `SpotifyOauthError` → `AuthError`.
- Teste existente de DI adaptado (era tautológico ao afirmar dict
  completo). Suite: 287 → 290 passed.

## [0.3.0] — 2026-04-18

Fase 3 do roadmap. Transforma o maestra-ai de pré-alpha com stubs de
auth em sistema operacional na máquina do usuário sem custo recorrente.
Segue design em `docs/superpowers/specs/2026-04-18-v030-auth-onboard-design.md`.

### Added
- **`core/token_store.py`** — Protocol `TokenStore` + `KeyringTokenStore`
  (preferencial) + `FileTokenStore` (fallback em `config_dir()/token.json`
  com chmod 600). `default_token_store()` escolhe em runtime.
- **`core/auth.py`** — `setup()` grava config.json; `login()` executa fluxo
  OAuth paste-back (zero servidor local; compatível com política Spotify
  que rejeita `localhost`/`127.0.0.1` em apps novos).
- **`core/onboard.py`** — `run(sp, taste, ...)` em 6 etapas: autenticação,
  playlist (com sufixo se nome duplicado), top tracks em 3 janelas
  (`long_term` peso 3, `medium_term` 2, `short_term` 2), saved tracks
  paginado (cap 1000, peso 1), recently played (50, peso 1), análise
  local que popula `global_signal` no taste_profile + semeia playlist
  + deriva 5 contextos sugeridos.
- **`core/taste.py::record_global_positive(uri, weight)`** — acumula
  sinais globais ponderados (distinto de `record_feedback(global=True)`
  que é binário).
- **`cli/auth.py`** — subcomandos reais `auth setup` (flags + prompt
  interativo via rich) e `auth login` (paste-back com instruções claras).
- **`cli/onboard.py`** — UX rich com preview de custo via
  `format_estimate`, progress com spinner, panel final colorido,
  flags `--dry-run`, `--yes`, `--json`.
- **`cli/help.py`** — `maestra help <tópico>` renderiza markdown via
  rich. Sem arg lista tópicos disponíveis.
- **`docs/topics/onboarding.md`** — guia completo com pré-requisitos,
  6 etapas, pesos, custo em req/bytes, próximos passos.
- **`_InMemoryCacheHandler`** em `core/client.py` — implementa spotipy
  `CacheHandler` sem escrever em disco; injeta refresh_token do
  `TokenStore` no fluxo OAuth do controller.

### Changed
- **`core/client.py::SpotifyController.__init__`** aceita `token_store`
  via DI. Default lê credenciais de `storage.read_config()` e
  refresh_token de `default_token_store()`. Fecha o gap bloqueante
  em que `auth login` salvava mas o client não consumia.
- **`core/storage.py`** — `save_refresh_token` / `load_refresh_token`
  viraram shims delegando para `default_token_store()`.
- **`pyproject.toml`** — `responses>=0.25` em dev deps;
  `tool.hatch.build.targets.wheel.force-include` empacota
  `maestra_ai/docs` no wheel.

### Removed
- **`from dotenv import load_dotenv` em `core/client.py`** — credenciais
  exclusivamente via config.json. `.env` em `config_dir` não é mais
  lido. Breaking para setups legados (provavelmente ninguém).
- Testes de keyring/file via `storage.save/load_refresh_token` em
  `test_storage.py` (cobertura equivalente em `test_token_store.py`).

### Fixed
- `_keyring_backend_ok` em `token_store.py`: checa `__module__`
  (onde "fail"/"null" aparecem) em vez de `__name__` que é sempre
  "Keyring". Fix silencioso de detecção quebrada que afetava a v0.2.x.
- `KeyringTokenStore.load/delete` defensivos contra `NoKeyringError`
  — retornam `None`/no-op em ambientes sem backend, em vez de crash.

### Tests
- 38 testes novos: `test_token_store.py` (11), `test_auth.py` (8),
  `test_onboard.py` (13), `test_client.py` (+2), `test_help.py` (3),
  `test_cli_e2e.py` (+3). Suite: 249 → 287 passed.

### Notes
- Fora de escopo (Plano 4 / v0.4.0): daemon IPC via unix socket,
  `skip_deps=True` para comandos read-only (`taste show`, `context show`,
  `doctor`), MCP server.
- Fluxo paste-back documentado no `help onboarding` e nos prompts do
  `auth login`. Sem fallback automático de servidor local.

## [0.2.5] — 2026-04-18

Fecha os dois P0 remanescentes do review pós-v0.2.3 (P0-3, P0-5) e os
dois pré-requisitos arquiteturais de Fase 3 (P1-4, P1-7). Após esta
versão, Fase 3 (OAuth real, daemon production-ready, MCP server) fica
desbloqueada.

### Added
- `core.storage.atomic_write_json(path, data)` — write atômico com
  `fcntl.LOCK_EX` + tmp + `os.replace`. Substitui padrão repetido em
  3 módulos.
- `core.storage.update_json_under_lock(path, mutator, default)` —
  read-modify-write atômico sob mesmo lock (elimina lost-update).
- `core.ratelimit.PersistentTokenBucket` — token bucket persistido em
  SQLite (WAL mode, `BEGIN IMMEDIATE`), usa `time.time()` wallclock
  para timestamps comparáveis entre processos.
- `core.ratelimit.PersistentCircuitBreaker` — circuit breaker com
  estado em SQLite. Failures como JSON array de timestamps.
- `core.client.SpotifyController(sp=..., auth_manager=...)` — DI via
  constructor. Backward compat: sem args usa OAuth default.
- `tests/integration/test_cli_e2e.py` — primeira bateria E2E do
  projeto. Subprocess real de `uv run maestra ...` com XDG paths
  isolados em tmp.

### Fixed
- **P0-3** — rate limit compartilhado entre daemon (`director run`) e
  CLI manual. Antes: dois processos tinham dois budgets de 60 req/min
  independentes, total real ultrapassava o limite Spotify.
- **P0-5 parcial** — writes atômicos em `context.set`,
  `playback._save_state`, `feedback_prompt.mark_prompted`. Antes:
  `open("w")` cru permitia corrupção por interleaving + `mark_prompted`
  tinha TOCTOU read-then-write que perdia marcas de outros contextos.

### Changed
- `core.client._bucket` e `_breaker` viraram lazy singletons via
  `_get_bucket()` / `_get_breaker()` — respeitam `MAESTRA_STATE_DIR`
  setado após import (essencial para testes).

### Tests
- 18 testes novos: `test_storage.py` (5), `test_ratelimit.py` (6),
  `test_client.py` (2), `test_cli_e2e.py` (5). Suite: 231 → 249 passed.

### Notes
- `playback._append_events` (append JSONL) **não** foi convertido: risco
  de truncamento acima de `PIPE_BUF` (4KB POSIX) é P1 teórico — tratar
  se surgir evidência empírica.
- `TokenBucket`/`CircuitBreaker` in-memory preservados para uso
  single-process e testes isolados.
- E2E cobre só comandos que não forçam `_build_deps`
  (`rollback --list`, `doctor`). `taste show`/`context set`/`status`
  exigem `SpotifyController()` mesmo em read-only — dívida arquitetural
  separada, não bloqueante.

## [0.2.4] — 2026-04-17

Fecha 1 P0-regressão e 3 P0-novos identificados no review pós-v0.2.3
(`docs/reviews/2026-04-17-pos-v023.md`). Não toca em P0-3/P0-5 (ratelimit
persistente, locks em context/playback/feedback_prompt) — fica para v0.2.5
antes da Fase 3.

### Added
- `core/security.py` — `redact_str` (regex p/ Bearer e tokens opacos) +
  `redact_error_dict` (cobre `what_happened`, `title`, `where`, `body`).

### Fixed
- **P0-R1** — bypass do redact do P0-2 em v0.2.3: `cli/_common.py::error()`
  recebia `str(SpotifyException)` cru de 8 pontos em `basic.py` e
  `cli/_build_deps` embute `str(e)` em `what_happened` via f-string.
  Agora `error()` aplica `redact_str` na mensagem e `main()` usa
  `redact_error_dict` no dict inteiro.
- **P0-N1** — `core/storage.py::load_refresh_token` retorna `None` em
  `token.json` corrompido (antes: `JSONDecodeError` cru quebrava reauth).
- **P0-N1.b** — `core/storage.py::read_config` levanta `ConfigError`
  estruturado em config malformado (antes: traceback cru em `doctor`,
  `auth setup`, `_build_deps`).
- **P0-N2** — `core/playback_processor.py::_read_events` pula linhas
  com JSON inválido ou não-dict em vez de abortar o loop. Linha
  corrompida no JSONL não paraliza o pipeline do director.
- **P0-N3** — `core/taste.py::_load` renomeia perfil corrompido para
  `.corrupt.<ms>` + warning em stderr antes de retornar vazio. Corrige
  regressão introduzida em v0.2.3: antes o fix silenciosamente
  sobrescrevia o arquivo com `{}` na próxima `save()`.

### Tests
- 15 testes novos: `test_security.py` (8), `test_storage.py` (4),
  `test_playback_processor.py` (2), `test_taste.py` (1). Suite:
  216 → 231 passed.

## [0.2.3] — 2026-04-17

Fecha 4 P0 de segurança do code review das Fases 1 e 2
(`docs/reviews/2026-04-17-fases-1-2.md`).

### Fixed
- **P0-1** — `core/snapshot.py::load` bloqueia path traversal via
  regex `_SNAP_ID_RE = r"^[\w:\-]+$"` + check `is_relative_to` pós
  `path.resolve()`. Vetor: `maestra rollback --snapshot ../../../etc/passwd`.
- **P0-2** — `cli/__init__.py::main` redacta `err_dict["where"]` via
  `core.audit._redact` antes de emitir JSON. Evita vazamento de
  `client_secret`/`access_token` em logs de CI/CD. **Nota:** fechado de
  forma incompleta nesta versão — o bypass em `cli/_common.py::error()`
  foi identificado no review seguinte e corrigido em v0.2.4 (P0-R1).
- **P0-4a** — schema validation em `core/snapshot.py`: `load()` valida
  `isinstance(data, dict)` + presença de `state`; `list_snapshots()`
  filtra entradas malformadas.
- **P0-4b** — schema validation em `taste`, `context`, `feedback_prompt`,
  `playback`: try/except `(JSONDecodeError, OSError)` + `isinstance dict`
  degrada para estado vazio em vez de traceback cru. **Nota:** em
  `taste._load` isto introduziu regressão (destruição silenciosa do
  perfil); corrigido em v0.2.4 (P0-N3).

### Tests
- 12 testes novos cobrindo os 4 P0. Suite: 204 → 216 passed.

## [0.2.2] — 2026-04-17

Fecha P1 do review de v0.2.0.

### Fixed
- `core/audit.py::_force_rotate` perde o parâmetro `age_days` (era
  ignorado silenciosamente); callers já passam sem argumento.
- `core/snapshot.py::create` usa granularidade de microsegundos no ID
  para evitar colisão lexicográfica entre snapshots no mesmo segundo
  (safety-before-rollback era particularmente exposto).

### Removed
- `cli/__init__.py::handle_errors` (código morto; try/except em
  `main()` já cobre `MaestraError`). Import de `functools.wraps`
  removido junto.

### Notes
- Débito da Fase 1 (`test_parity.py`) fechado por obsolescência:
  `cli/_monolith.py` foi removido na Fase 2, sem base para comparar.

## [0.2.1] — 2026-04-16

Hotfix baseado no code review da v0.2.0 — endereça os 4 P0 que bloqueariam a Fase 3.

### Fixed
- `cli/_common.py` e `core/client.py` agora consomem `core.storage`
  (`data_dir()`/`config_dir()`) em vez de paths hardcoded no workspace
  antigo. Usuários que setarem `MAESTRA_DATA_DIR`/`MAESTRA_CONFIG_DIR`
  deixam de ter estado partido entre módulos novos e antigos.
- `core/rollback.py::_apply_state` deixa de ser stub vazio: recebe
  `apply_state_fn` injetado pelo CLI que aplica `taste`/`context` reais
  (antes `maestra rollback` reportava ok mas não aplicava nada).
- `cli/rollback.py::_current_state` deixa de retornar `{}` — coleta
  snapshot vivo de `taste.data` + `context_state.show()` antes de aplicar
  o rollback (safety snapshot agora é real).
- `cli/__init__.py::main` encapsula `_build_deps()` no try/except
  `MaestraError`; `SpotifyController()` falho agora levanta `AuthError`
  em vez de `sys.exit(1)` direto, permitindo painel rich/JSON consistente.

### Added
- `TasteProfile.restore(data)` — overwrite sem merge, uso exclusivo de
  rollback (método regular `save()` mescla com disco, inadequado aqui).
- 2 testes unitários cobrindo `restore` e caminho sem snapshot.

## [0.2.0] — 2026-04-16

### Added
- `core.errors` — hierarquia `MaestraError` com 5 campos humanos + `agent_hint`
- `core.reporting.format_estimate` — total sempre calculado + `humanize_bytes`
- `core.storage` — XDG paths, env var overrides, keyring + fallback chmod 600
- `core.ratelimit` — `TokenBucket` (60 req/min) + `CircuitBreaker` (3 falhas/60s, cooldown 5min)
- `core.snapshot` — snapshots automáticos pré-operação, 20 ativos + gzip archive
- `core.rollback` + `maestra rollback --list/--last/--snapshot` com safety snapshot
- `core.audit` — audit log JSONL com redação de secrets, rotação 15d + 30d gzip
- `core.doctor` + `maestra doctor` com 6 checks (python, config, keyring, token, disk, director)
- `rich` e `rich-argparse` integrados no CLI (help colorido, painéis de erro)
- `--json` global no parser raiz para consumo programático
- Tratamento central de `MaestraError` em `main()` com painel rich ou JSON
- Decorador de conveniência `handle_errors` em `cli/__init__.py`

### Changed
- CLI monolítico (`_monolith.py`, 1211 linhas) decomposto em 12 módulos
  por subcomando + `_common.py`, com pattern `@register` para agregação.
- `core.client` — toda chamada à API do Spotify agora passa por
  `_call_spotify()` com rate limiter + circuit breaker + tradução de erros
  HTTP (429→`RateLimitError`, 401→`AuthError`, 5xx→`SpotifyAPIError`).
- CLI agregador usa `RichHelpFormatter` quando `rich-argparse` disponível.

### Infra
- `dev` deps: `freezegun>=1.4`, `ruff>=0.5`
- `runtime` deps: `rich>=13`, `rich-argparse>=1.5`, `keyring>=24`
- Lint config `ruff` (E, F, W, I, B, UP, N, RET; ignore E501)

## [0.1.1] — 2026-04-16

### Fixed
- `core/client.py` respeita `MAESTRA_CONFIG_DIR` para localizar `.env` e `.cache`
  do OAuth (antes lia de `__file__`, que em instalação editable apontava para o
  repo novo e quebrava autenticação). Reviewer flagou como bloqueio real.
- `MAESTRA_CONFIG_DIR` no `.bashrc` corrigido para apontar para o próprio
  `workspace/` (onde vivem `.env` e `.cache`), não para um subdir `config/` que
  não existia. Subdir vazio removido.

### Added
- `PROGRESS.md` adicionado ao `.gitignore`.

## [0.1.0] — 2026-04-16

### Added
- Monorepo skeleton with uv workspace
- Core modules ported from `iris_spotify` → `maestra_ai.core`
- CLI portado como `maestra_ai.cli._monolith` (agregador delega a ele)
- Stubs `auth setup/login` e `onboard` (implementação real em v0.3.0)
- Smoke tests para parser do agregador (27 casos)
- 122 testes unitários do antecessor portados e passando

### Changed
- Módulo `core.py` renomeado para `client.py` no novo namespace
- Namespace de imports: `iris_spotify.X` → `maestra_ai.core.X`
- `BASE_DIR` agora respeita `MAESTRA_DATA_DIR` (fallback para workspace antigo)

### Deferred (movido para planos seguintes)
- Decomposição real do monolito em `cli/<subcomando>.py` (planejado p/ v0.2.0,
  junto com introdução de `rich`, `@handle_errors` e `core/storage.py`)

[Unreleased]: https://github.com/mencoding/maestra-ai/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/mencoding/maestra-ai/releases/tag/v0.1.0
