# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
