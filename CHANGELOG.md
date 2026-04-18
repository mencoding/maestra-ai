# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
