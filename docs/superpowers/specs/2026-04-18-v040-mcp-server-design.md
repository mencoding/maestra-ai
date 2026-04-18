# v0.4.0 — MCP Server (Design Spec)

**Data:** 2026-04-18
**Versão alvo:** v0.4.0
**Origem:** adaptação do plano original
`~/.claude/iris/docs/superpowers/plans/2026-04-16-maestra-ai-v04-mcp-server.md`
ao estado atual pós-v0.3.2.
**Revisor:** Iris (Claude Opus 4.7) + Léo
**Status:** draft — aguardando aprovação do Léo.

---

## Goal

Transformar o maestra-ai em ferramenta integrada a agentes de IA via
**MCP stdio server**. Após v0.4.0:

- Instalar `maestra-mcp` expõe 23 tools que espelham a CLI.
- Claude Code, Cursor, Codex e qualquer agente compatível com
  [Model Context Protocol](https://modelcontextprotocol.io) podem usar
  as tools sem código adicional.
- Léo (ou qualquer usuário) passa de "abrir terminal e digitar
  `maestra curate`" para "Iris, coloca foco denso e popula a playlist"
  dentro do próprio fluxo de trabalho.
- Cada chamada MCP passa por audit log com redact (reuso de v0.2.4),
  rate limit persistente (v0.2.5) e permite desabilitar tools via
  `config.json` (`mcp.disabled_tools`).

## Non-goals

Fora do escopo desta versão:

- **Daemon com IPC unix socket** (`director.sock`, reload hot, status
  detalhado vivo). Fica para v0.5.0 se surgir demanda.
- **Progress notifications** em `onboard` e `curate` via MCP. O plano
  original marca como opcional condicional ao SDK; deixamos deferred
  para v0.5+ porque `onboard` roda em <10s.
- **Dashboard web** (era o Plano 5 original — agora renumerado).
- **Publicação no PyPI**. Plano 6 (release) cuida disso. Aqui só
  empacotamento local via `uv tool install`.
- **HTTP/SSE transport**. MCP também suporta transports além de stdio,
  mas stdio é suficiente para uso local e não requer hospedagem.

## Contexto: divergências do plano original

O plano original foi escrito em 2026-04-16 assumindo que o Plano 2
criaria API **funcional** em `core.*` (funções livres tipo
`playback.play(track_uri=...)`, `context.set_context(description)`,
`director.start(interval=...)`). Na prática o Plano 2 entregou API
**orientada a objetos**: `SpotifyController`, `ContextState`, `Curator`,
`MusicDirector`, `FlowAnalyzer`, `HistoryAnalyzer`, `TasteProfile`.

**Impacto:** 6 das 23 tools precisam de adaptação para usar as classes
existentes ou de API nova em `core.*`. Detalhado na seção "Catálogo de
tools".

Outras divergências menores:

1. **MCP SDK atual é 1.27.0**; plano assumia >=1.0. API pode ter mudado
   (ex: `list_tools`/`call_tool` decorator names). Fica como trigger
   de revisão.
2. **`onboard.run` signature** — v0.3.0 implementou como
   `run(sp, taste, *, playlist_name, seed_count, dry_run, progress_cb)`
   (DI explícita). Plano 4 assume `run(playlist_name=..., seed_count=...)`.
   Wrapper do MCP instancia `sp` e `taste` internamente.
3. **`audit.log(tool, args, result)`** — API bate com o que o plano 4
   assume. Sem divergência.

## Decisões arquiteturais

### D1. `maestra-mcp` adapta, não funcionaliza `core.*`

**Escolha:** wrappers de tool instanciam as classes `core.*` existentes
(ex: `SpotifyController()`, `ContextState(path)`) via helper
`_build_deps_mcp()` análogo ao `_build_deps()` do CLI. Não criamos
funções livres em `core.*` só para o MCP.

**Justificativa:** criar API funcional dobra a superfície pública sem
benefício imediato. YAGNI. O CLI já prova que DI via classes funciona.

**Exceções** (tools que requerem API nova em `core.*` porque a lógica
hoje está dentro do CLI, não em classes reutilizáveis):

- `playlist_prune` — lógica em `cli/playlist.py` via helper
  `_prune_candidates` de `cli/_common.py`. Mover para `core/curator.py`
  como função `prune(scope, context, confirm)` ou método
  `Curator.prune(...)`.
- `history_import_outside` — lógica no `MusicDirector.run_once`.
  Extrair para `HistoryAnalyzer.import_outside(...)`.
- `director_start/stop/status` — hoje via CLI que usa `subprocess.Popen`
  e PID file. Promover para `core/director.py` como funções livres
  `start/stop/status` que manipulam PID file + spawn subprocess. CLI
  e MCP compartilham.
- `taste_review` — lógica em `cli/_common.py::_context_review`. Mover
  para `core/taste.py` como método `TasteProfile.review(top, context)`
  ou função livre `taste.review(profile, playlist_tracks, context, top)`.

Cada refactor vem com teste que exercita o core diretamente (o CLI
já fica coberto porque consume a API movida).

### D2. Pacote workspace `maestra-mcp` depende de `maestra-ai`

Estrutura:

```
packages/
├── maestra-ai/              (existente)
└── maestra-mcp/             (novo)
    ├── pyproject.toml       (depende de maestra-ai, mcp>=1.0)
    ├── README.md
    ├── src/maestra_mcp/
    │   ├── __init__.py
    │   ├── server.py        (stdio bootstrap + decorators)
    │   ├── tools.py         (registry + 23 handlers)
    │   └── deps.py          (_build_deps_mcp)
    └── tests/
        ├── test_tools.py
        └── test_server.py
```

`uv.workspace` já aponta para `packages/*`, então o novo pacote é
detectado automaticamente. Script `maestra-mcp` vira entry_point do
pacote novo.

### D3. Tool handlers sempre retornam JSON serializável

Formato de retorno padronizado em `list[types.TextContent]` (exigência
MCP), com `type="text"` e `text=json.dumps(dict, ensure_ascii=False)`.
Em caso de erro, o dict é `{"error": MaestraError.to_human_dict()}`
(reusa a hierarquia de v0.2.0 + redact de v0.2.4).

### D4. `disabled_tools` via config.json

Estrutura:

```json
{
  "client_id": "...",
  "mcp": {
    "disabled_tools": ["playlist_prune", "director_start"]
  }
}
```

O server lê `cfg["mcp"]["disabled_tools"]` em dois pontos:

- `list_tools()` — filtra da resposta.
- `call_tool()` — rejeita com `UserError` mesmo se o agente tentar
  chamar tool bloqueada (defesa em profundidade).

### D5. Audit log em toda chamada MCP

Wrapper `_audit_and_call(name, args)` em `server.py`:

1. Chama handler.
2. Se sucesso, `audit.log(name, args, result)`.
3. Se erro, `audit.log(name, args, {"error": {...}})`.

Reuso do `_redact` de `core.audit` (v0.2.4) garante que args e result
têm secrets redactados no disco. Falha de audit não impede retorno
(warning em logger).

### D6. Versão do MCP SDK

Fixar `mcp>=1.0,<2.0` no pyproject para evitar breaking majors.
A API específica (Server, list_tools, call_tool, stdio_server,
types.Tool, types.TextContent) é estável entre 1.0 e 1.27 pelo que se
sabe. Se diff aparecer, trigger de revisão.

### D7. Testing strategy

- **Unit**: mock de `core.*` para cada handler; valida que tool chama
  o core certo com os args certos.
- **Integration**: inicia o server em subprocess, fala JSON-RPC via
  stdio pipe, confirma round-trip de 2-3 tools representativas (`now`,
  `set_context`, `doctor`).
- **Asyncio**: `pytest-asyncio>=0.23` com `asyncio_mode="auto"`.

Sem teste de "23 tools registradas" tautológico — o contador é um
count do registry, passa por construção.

## Componentes

### Novo pacote `maestra-mcp`

```python
# src/maestra_mcp/server.py
def create_server() -> Server:
    server = Server("maestra")

    @server.list_tools()
    async def _list_tools() -> list[types.Tool]:
        from maestra_ai.core import storage
        cfg = storage.read_config()
        disabled = set((cfg.get("mcp") or {}).get("disabled_tools", []))
        return [types.Tool(name=t.name, description=t.description,
                           inputSchema=t.schema)
                for t in iter_tool_defs() if t.name not in disabled]

    @server.call_tool()
    async def _call_tool(name: str, args: dict) -> list[types.TextContent]:
        # ... (inclui disabled check + audit + error wrapping)
        return [types.TextContent(type="text", text=json.dumps(result))]
    return server
```

### Helper `deps.py`

```python
# src/maestra_mcp/deps.py
from functools import lru_cache

@lru_cache(maxsize=1)
def build_deps():
    """Instancia cores uma vez por processo (stdio = longa vida)."""
    from maestra_ai.core.client import SpotifyController
    from maestra_ai.core.context import ContextState
    # ... (análogo a cli/__init__.py::_build_deps)
    return {...}
```

Cache é seguro porque processo MCP é longo e `SpotifyController` é
thread-safe via rate limit persistente (v0.2.5). Primeira chamada
trigga OAuth se necessário (via TokenStore).

### Registry de tools `tools.py`

Cada tool decorada com `@tool(name, description, schema)` e
auto-registrada em `_REGISTRY: dict[str, ToolDef]`. Handler sempre
`async` por contrato MCP; decorator wrapa sync handlers em coroutine.

## Catálogo das 23 tools

Organização em 6 categorias (mantida do plano original):

### Playback (7) — todas diretas

| Tool | Core |
|------|------|
| `now` | `controller.now()` |
| `play` | `controller.play(uri=track_uri or context_uri)` |
| `pause` | `controller.pause()` |
| `skip` | `controller.next_track()` (renomeia do plano) |
| `queue` | `controller.queue_add(uri)` |
| `search` | `controller.search(query, type='track', limit)` |
| `devices` | `controller.devices()` |

### Contexto (3) + Curadoria (1)

| Tool | Core |
|------|------|
| `set_context` | `context_state.set(description)` |
| `get_context` | `context_state.show()` |
| `clear_context` | `context_state.clear()` |
| `curate` | `curator.curate(context, count=max_tracks, max_per_artist)` |

**Divergência do plano:** `curate` schema original tinha
`max_artist_share`. Removido porque não existe em `Curator.curate` —
vive em `Director.run_once`. Se `max_artist_share` for essencial no
MCP, tool `curate` poderia chamar `director.run_once` em vez — decisão:
**manter simples**, `curate` = `Curator.curate`. `max_artist_share` via
`director_once` se precisar.

### Análise (3)

| Tool | Core | Status |
|------|------|--------|
| `flow_review` | `flow_analyzer.review(context, window)` | direto |
| `taste_review` | **API nova** — `core/taste.py::review()` | refactor |
| `history_outside_playlist` | `history_analyzer.outside_playlist(playlist_id, recent_limit)` | direto |

**`taste_review` refactor:** extrair `cli/_common.py::_context_review`
para `core/taste.py`:

```python
# core/taste.py
def review(profile, playlist_tracks, context, *, top=10): ...
```

CLI migra para consumir `taste.review(...)`. Zero regressão.

### Manutenção (3)

| Tool | Core | Status |
|------|------|--------|
| `playlist_prune` | **API nova** — `core/curator.py::prune()` | refactor |
| `history_import_outside` | **API nova** — `core/history.py::import_outside()` | refactor |
| `rollback` | `rollback.rollback_to(snap_id, current_state_fn)` | direto |

**`playlist_prune` refactor:** extrair lógica de `cli/playlist.py` e
`cli/_common.py::_prune_candidates` para método
`Curator.prune(scope, context, confirm)`. Snapshot automático antes
de execução real (plano 4 Step 1 já especifica).

**`history_import_outside` refactor:** extrair `MusicDirector.run_once`
bloco de import-outside para método `HistoryAnalyzer.import_outside(
confirm, count, min_plays, context)`.

### Director (4)

| Tool | Core | Status |
|------|------|--------|
| `director_start` | **API nova** — `core/director.py::start()` | refactor |
| `director_stop` | **API nova** — `core/director.py::stop()` | refactor |
| `director_status` | **API nova** — `core/director.py::status()` | refactor |
| `director_once` | `director.run_once(count)` | direto |

**`director_start/stop/status` refactor:** promover lógica de
`cli/director.py::cmd_director_start/stop/status` para
`core/director.py` como funções livres que manipulam PID file em
`state_dir()/director.pid`, usando `atomic_write_json` (v0.2.5) para
persistência. CLI vira thin wrapper.

### Onboard/Doctor (2)

| Tool | Core | Status |
|------|------|--------|
| `onboard` | `onboard.run(sp, taste, playlist_name, seed_count)` | direto (wrapper instancia) |
| `doctor` | `doctor.run_all()` | direto |

## Refactors de `core/*` como pré-requisito

4 refactors pequenos antes das tools dependentes:

1. **R1 — `taste.review`**: mover lógica de `cli/_common.py::_context_review`.
   ~60 LoC, 3 testes. Caller em `cli/taste.py` atualiza.
2. **R2 — `curator.prune`**: mover lógica de `cli/playlist.py::cmd_playlist_prune`
   + `_prune_candidates`. ~80 LoC, 4 testes. Snapshot automático dentro.
3. **R3 — `history.import_outside`**: extrair de `MusicDirector.run_once`.
   ~70 LoC, 3 testes.
4. **R4 — `director.start/stop/status` funções livres**: mover de
   `cli/director.py`. ~100 LoC, 5 testes. CLI vira wrapper.

Total estimado: ~310 LoC + 15 testes de refactor **antes** de começar
as tools. Representa ~1 sessão extra vs plano original.

## Data flow — JSON-RPC stdio

```
Agent (Claude Code, Cursor, Codex)
    │ stdin/stdout via JSON-RPC 2.0
    ▼
maestra-mcp subprocess (Python, stdio)
    │
    ├─ initialize (handshake MCP)
    ├─ list_tools → 23 tools (menos disabled_tools do config)
    └─ call_tool(name, args)
           │
           ├─ check disabled_tools (defesa em profundidade)
           ├─ _REGISTRY[name].handler(args)  (async)
           │      │
           │      └─ instancia SpotifyController, Curator, etc. via deps.build_deps()
           │            │
           │            └─ core.*.method(...)  (síncrono; IO via spotipy)
           │
           ├─ audit.log(name, args, result)  (best-effort)
           │
           └─ return TextContent(json.dumps(result))
```

## Error handling

Reuso de v0.2.0+ + v0.2.4:

| Caso | Retorno |
|------|---------|
| Tool desconhecida | `{"error": {"code": "UserError", "title": "Tool 'X' não existe"}}` |
| Tool desabilitada via config | `{"error": {"code": "UserError", "title": "Tool desabilitada"}}` |
| MaestraError (Auth, Config, RateLimit, SpotifyAPI, Storage, User) | `{"error": e.to_human_dict()}` (redactado) |
| Exceção inesperada | `{"error": {"code": type(e).__name__, "title": "Erro inesperado", "what_happened": str(e)}}` com redact |
| JSONDecodeError do SDK | propagado (MCP framework responsabilidade) |

Todos retornam via `types.TextContent` — agente recebe string JSON que
consegue parsear. Exit code do processo só via SIGTERM/Ctrl+C.

## Security

- **Audit log** — toda chamada registrada em
  `state_dir()/audit/audit.jsonl`. Retenção 15d ativos + 30d gzip
  (v0.2.0). Redact por chave (client_secret, access_token, etc.) e
  regex (Bearer tokens) via `core.security` (v0.2.4).
- **Rate limit compartilhado** — `PersistentTokenBucket` /
  `PersistentCircuitBreaker` em SQLite (v0.2.5). Daemon + CLI + MCP
  compartilham budget 60 req/min automaticamente.
- **`disabled_tools`** — usuário pode bloquear tools destrutivas em
  ambientes sensíveis. Operações com `confirm=false` já são
  dry-run por padrão (plano 4).
- **Snapshot automático** em `playlist_prune`, `history_import_outside`,
  `rollback` — usuário pode desfazer mesmo se MCP agir em excesso.
- **Stdio local** — servidor não expõe porta de rede. Comunicação
  restrita ao subprocess do agente.

## Triggers for revision

- **MCP SDK 2.x release** com breaking changes.
- **`@server.list_tools()` / `@server.call_tool()` decorator signatures
  mudam** — ajustar `server.py`.
- **Agente popular (Cursor, Codex) espera formato diferente** de
  error/result — documentar em `docs/MCP.md`.
- **`disabled_tools` como string em vez de lista** — validar e
  documentar erro claro em `ERRORS.md`.
- **Performance de `build_deps()` em cada chamada tool** — se
  `SpotifyController()` ficar lento, trocar `@lru_cache` por padrão de
  singleton lazy com invalidação em `auth login`.

## Backward compatibility

Nenhuma API existente da v0.3.x muda. Os 4 refactors (R1-R4) **movem**
código de `cli/*` para `core/*` — CLI continua funcionando porque
consome a API movida. Nenhum caller público externo é afetado (o CLI é
a única interface pública até v0.4.0).

`pyproject.toml` de `maestra-ai` **não** ganha dependência de `mcp`
— fica opcional via `maestra-mcp` separado.

## Tasks (resumo executivo)

1. **R1** — `taste.review()` extraído de `cli/_common.py`.
2. **R2** — `Curator.prune()` extraído de `cli/playlist.py`.
3. **R3** — `HistoryAnalyzer.import_outside()` extraído de Director.
4. **R4** — `director.start/stop/status` funções livres; CLI vira wrapper.
5. **Setup `maestra-mcp`** — pacote workspace, pyproject, README, __init__.
6. **`deps.py`** — `build_deps()` com lru_cache.
7. **`server.py`** — stdio server + list_tools + call_tool + disabled check + audit.
8. **`tools.py` (3 arquivos de commit)** — 23 tools divididas:
   - Playback (7) + Contexto (3) + Curadoria (1) → commit "mcp-tools-basic"
   - Análise (3) + Manutenção (3) + Rollback → commit "mcp-tools-review"
   - Director (4) + Onboard + Doctor → commit "mcp-tools-director-onboard"
9. **Tests** — `test_tools.py` (mock core) + `test_server.py` (subprocess roundtrip de 3 tools).
10. **Docs** — `docs/MCP.md` (por agente) + `topics/mcp.md` (maestra help mcp).
11. **Bump + CHANGELOG + tag v0.4.0** + ambos pacotes (`maestra-ai` + `maestra-mcp`).

Ordem de execução: R1-R4 primeiro (preparação), depois 5-11 (pacote MCP).

## Critérios de conclusão

- [ ] `packages/maestra-mcp/` no workspace, instalável via `uv tool install`.
- [ ] 23 tools registradas e com schema JSON estrito.
- [ ] `maestra-mcp` inicia via stdio e responde à `initialize` +
      `tools/list` + `tools/call`.
- [ ] Smoke test subprocess: `echo '{"jsonrpc":"2.0","method":"tools/list",...}' | maestra-mcp`
      retorna lista válida.
- [ ] Integração real com Claude Code: adicionar em
      `~/.claude/mcp.json` e verificar que aparecem 23 tools no `/mcp` list.
- [ ] Allow-list `disabled_tools` respeitada no list e no call.
- [ ] Audit log grava toda chamada com redact.
- [ ] Suite: 292 → ~350 passed (~60 testes novos: 15 refactor + 30 MCP tools + 10 server + 5 E2E).
- [ ] CHANGELOG `[0.4.0]` escrito.
- [ ] Tag `v0.4.0` pushada.
- [ ] README principal menciona `maestra-mcp` como segundo pacote.
- [ ] `docs/MCP.md` com exemplos Claude Code, Cursor, Codex.
- [ ] `maestra help mcp` renderiza topic.

---

## Próximo passo

Invocar `superpowers:writing-plans` para gerar
`docs/superpowers/plans/2026-04-18-v040-mcp-server.md` com steps
executáveis em checkbox, incluindo blocos de código por task.
