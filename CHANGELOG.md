# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
