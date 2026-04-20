# Code review — maestra-ai v0.6.0-alpha.0 (pós-release)

**Data:** 2026-04-19
**Escopo:** codebase completo (core + CLI + MCP) no estado da tag v0.6.0-alpha.0.
**Reviewer:** superpowers:code-reviewer subagent.
**Base:** 462 testes maestra-ai + 35 MCP. Todos verdes no pacote.

> Revisão complementar aos três reviews anteriores (2026-04-17 fases 1-2, pós-v0.2.3, backlog consolidado de 2026-04-19). Foca no que não foi coberto e não repete itens já fechados.

Nota de contexto: `pytest` do root falha com "errors during collection" — rootdir/conftest, não código. Testes passam rodados de dentro de cada pacote.

---

## Critical

Nenhum. Não há bloqueador para release.

---

> **Status v0.6.1-alpha.0 (2026-04-19):** todos os 7 itens Important
> (I1-I7) foram fechados. Detalhes no CHANGELOG [0.6.1-alpha.0].

## Important (7)

### I1. Tornar `storage.write_config` atômico

**Arquivo:** `packages/maestra-ai/src/maestra_ai/core/storage.py:143-146`

`write_config` usa `p.write_text(...)` direto. `atomic_write_json` existe no mesmo arquivo mas só o `FileTokenStore` usa. `onboard.run` escreve config em paralelo a leituras do director daemon → janela de JSON truncado → `ConfigError`.

**Fix:** trocar por `atomic_write_json(p, data)`. Uma linha.

### I2. `Director._record` escreve JSONL sem lock

**Arquivo:** `packages/maestra-ai/src/maestra_ai/core/director.py:189-198`

`open(log_path, "a") + write` concorrente entre daemon e `director_once` via MCP/CLI intercala bytes. POSIX append atômico só até PIPE_BUF (~4KB); payloads de decisão ultrapassam.

**Fix:** `fcntl.flock(f, LOCK_EX)` no write. Padrão já existe no projeto (`update_json_under_lock`).

### I3. `audit.log` escreve JSONL sem lock

**Arquivo:** `packages/maestra-ai/src/maestra_ai/core/audit.py:49-52`

Mesmo problema que I2. MCP server + CLI + daemon append em paralelo no `audit.jsonl`. `_force_rotate` já tem lock, mas a escrita normal não. Audit corrompido derrota o propósito forense.

**Fix:** `fcntl.flock` no append; idealmente extrair helper `append_jsonl_under_lock`.

### I4. Snapshot `create()` grava sem rename atômico

**Arquivo:** `packages/maestra-ai/src/maestra_ai/core/snapshot.py:50`

`path.write_text(json.dumps(...))` não atômico. Crash mid-write deixa arquivo parcial → `list_snapshots` vê, `load` falha. Pior: `rollback.py:27` cria safety-snapshot antes de rollback; falha ali inutiliza recuperação justamente quando é necessária.

**Fix:** `atomic_write_json(path, payload)`.

### I5. MCP não valida args contra `inputSchema`

**Arquivos:** `packages/maestra-mcp/src/maestra_mcp/tools.py:40-59`, `server.py:73-110`

`call_tool` passa `args` direto para o handler. Schemas com `additionalProperties: false`, `minimum`, `required` são declarativos — enviados ao cliente MCP em `list_tools` mas nada no servidor valida. Boundary menos confiável dos três (agentes IA).

Exemplos hoje passam:
- `queue({"track_uri": 123})` → TypeError genérico do spotipy.
- `search({"query": ""})` → query Spotify inútil.
- `director_start({"interval": 5})` → abaixo do mínimo do schema; rate-limit.

**Fix:** no `call_tool`, antes de `await td.handler(args)`, `jsonschema.validate(args, td.schema)`. Traduzir ValidationError para `UserError` do core.

### I6. `FeedbackPrompter._in_cooldown` não trata `fromisoformat`

**Arquivo:** `packages/maestra-ai/src/maestra_ai/core/feedback_prompt.py:91`

`datetime.fromisoformat(entry["last_prompt_at"])` crash cru com ValueError se state JSON tiver valor inválido (edição manual, corrupção parcial). Item #12 do backlog foi descartado como falso positivo em `context.py` — aqui o bug é real. UX ruim (traceback cru em vez de MaestraError estruturado).

**Fix:** `try/except (ValueError, KeyError, TypeError): return False`. Mesmo padrão que `context.py:44`.

### I7. `Curator.curate` acessa API privada de taste

**Arquivos:** `packages/maestra-ai/src/maestra_ai/core/curator.py:76`; `cli/_common.py:126, 159`

Uso de `taste._is_rejected`, `taste_mod._prune_candidates`, `_signal_weight` através de limites de módulo. Refatorar `taste.py` quebra curator silenciosamente. Testes cobrem, mas atrasa manutenção.

**Fix:** expor `taste.is_rejected(uri)` e `prune_candidates(...)` públicos; underscores ficam como alias internos.

---

## Minor (7)

### M1. `onboard._resolve_playlist_name` silencia `current_user_playlists`
`core/onboard.py:244-254` — `except Exception: return desired` engole AuthError/Rate/Network. Fix: deixar propagar exceções não-benignas.

### M2. `_interactive_selector` silencia `_fetch_own_playlists`
`core/onboard.py:472-480` — `except Exception` engole listagem. Similar ao M1.

### M3. `basic.py:cmd_status` captura `Exception` onde `ConfigError` basta
`cli/basic.py:165-167` — trocar por `except ConfigError`.

### M4. Singletons mutáveis `_bucket/_breaker`
`core/client.py:18-21` — globals sem reset. Testes passam por ordem de monkeypatch. Frágil. Fix: cache por `db_path` como ratelimit.

### M5. `_SECRET_KEYS` semântica não documentada
`core/audit.py:20-21` — comparação é exact-match lowercase. Sem docstring explicitando. Um comentário resolve.

### M6. `_fetch_own_playlists` sem cap anti-loop
`core/onboard.py:122-145` — `while True` só quebra por `next=None` ou `not items`. Sem guarda numérica (ao contrário de `_fetch_saved`). Defense in depth: `for _ in range(200): ...`.

### M7. CLI handlers capturam `Exception` com `str(e)` bruto
`cli/basic.py:74, 82, 92, 112, 149` — fora do padrão `MaestraError` centralizado no main(). Deixar propagar preserva `suggested_actions`.

### M8. `_interactive_choose` usa SystemExit direto
`cli/onboard.py:326-328` — `print` + `raise SystemExit(1)` em vez de MaestraError. Sem redaction, sem código, sem hint. Fix: deixar propagar.

---

## Nits (5)

- **N1.** Imports `SelectedPlaylist`/`FailedPlaylist` em `onboard.py:27-34` são runtime-only para TypedDict — ruff F401 pode reclamar.
- **N2.** `_SERVICE`/`_USER` duplicados em `storage.py` e `token_store.py`. `storage.py` só usa no shim. Dead code.
- **N3.** Docstring de `run()` em `onboard.py:310` ainda cita "v0.5.3" — envelheceu.
- **N4.** `SPOTIFY_SEARCH_PAGE_LIMIT = 10` em `client.py:74` sem justificativa (API aceita 50).
- **N5.** MCP sem teste direto de `clear_context` nem `onboard` tool.

---

## Veredicto

**Aprovado com ressalvas.** Nenhum bloqueador. Base sólida para alpha pre-release.

## Top 3 prioridades para v0.6.1

1. **I5 — validação MCP** (boundary mais frágil, fix barato com jsonschema).
2. **I1-I4 — atomicidade** (`write_config`, snapshot, director/audit JSONL). Mesmo padrão de fix em 4 call-sites.
3. **I6 — `_in_cooldown` guard** (3 linhas, equivale ao #12 que era real).

## Arquivos revisados

Core (22): onboard, onboard_types, client, errors, storage, taste, snapshot, audit, context, director, auth, security, token_store, curator, ratelimit, history, flow, feedback_prompt, doctor, rollback, config, plus helpers.
CLI (7): __init__, _common, basic, onboard, rollback, config, (taste/context/snapshot/feedback/playback amostrados).
MCP (4): server, tools, deps, config.
Testes: amostra de integration + mcp.
