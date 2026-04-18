# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
