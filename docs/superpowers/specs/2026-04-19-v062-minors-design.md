# Design — v0.6.2-alpha.0: narrowing de exceções + hardening

**Data:** 2026-04-19
**Versão alvo:** v0.6.2-alpha.0
**Origem:** review pós-v0.6.0-alpha.0 (`docs/reviews/2026-04-19-v060-post-release.md`)
**Itens fechados:** M1, M2, M3, M4, M5, M6, M7, M8 (todos os 8 Minors)
**Escopo:** correção de pipeline de exceções (5 itens) + hardening (2) + docstring (1). Zero feature nova. Pre-1.0; aceita mudança de contrato de output do CLI para erros.

---

## 1. Objetivo

Consolidar o pipeline de tratamento de erros do CLI ao fluxo central
(`MaestraError` → `redact_error_dict` → `_print_rich_error` em
`cli/__init__.py:246`). Handlers intermediários que hoje capturam
`Exception` e retornam mensagens não-redactadas sabotam esse caminho.
Além disso, fechar 2 itens de hardening (singleton reset do rate
limiter, cap anti-loop em paginação) e 1 docstring.

## 2. Contexto

### 2.1 Pipeline atual (funcionando)

`_call_spotify` (`core/client.py:42`) já traduz exceções do `spotipy` em
subclasses de `MaestraError`:
- `SpotifyOauthError` → `AuthError`
- HTTP 401 → `AuthError`
- HTTP 429 → `RateLimitError` (com `retry_after`)
- HTTP 5xx → `SpotifyAPIError`
- Demais: re-raise cru

`main()` em `cli/__init__.py:246` catcha `MaestraError`, aplica
`redact_error_dict` e imprime via `_print_rich_error` com
`suggested_actions` + `agent_hint`. Output padronizado, PII redactada.

### 2.2 O problema (call sites M1-M3, M7, M8)

Cinco call sites capturam `Exception` genérico e tratam localmente:

- **M1** `core/onboard._resolve_playlist_name:244-247` — `except Exception: return desired`. Silencia AuthError/Rate/Network; usuário vê "playlist criada" e o passo seguinte explode com a mesma causa, sem cadeia visível.
- **M2** `core/onboard.run:471-480` — `except Exception: own_playlists, empty_count = [], 0`. Engole AuthError durante listagem de playlists. Usuário recebe "sem playlists próprias" mesmo quando a causa foi rede/auth.
- **M3** `cli/basic.cmd_status:164-167` — `except Exception: playlist_id = None`. Engole qualquer coisa além de `ConfigError`.
- **M7** `cli/basic.cmd_play/pause/next/queue_add/play_context` — `except Exception as e: error(str(e), "PLAYBACK_ERROR")`. Retorna JSON `{"error": str(e), "code": "PLAYBACK_ERROR"}` sem `suggested_actions`, `agent_hint`, redaction — derrota o pipeline central.
- **M8** `cli/onboard._interactive_choose:324-328` — `print + SystemExit(1)` sem redaction, sem código estruturado.

### 2.3 Hardening (M4, M6)

- **M4** `core/client.py:20-21` — `_bucket`, `_breaker` são globals mutáveis. Testes que usam `monkeypatch.setenv("MAESTRA_STATE_DIR", ...)` após a primeira chamada batem na instância grudada ao `db_path` antigo. Frágil.
- **M6** `core/onboard._fetch_own_playlists:122-145` — `while True` só quebra por `next is None` ou `items == []`. Se a API retornar `next` fixo por bug de servidor ou mock quebrado, loop infinito. `_fetch_saved` já tem guarda numérica; aqui não tem.

### 2.4 Docstring (M5)

`core/audit.py:20-21` define `_SECRET_KEYS` como set usado em
`_redact`. A comparação é `k.lower() in _SECRET_KEYS` — exact match
lowercase. Não é óbvio lendo; um comentário de uma linha resolve.

### 2.5 Por que um bundle

Oito items pequenos do mesmo review. M1/M2/M3/M7/M8 são o mesmo
pattern (narrowing de `Exception`). M4/M6 são hardening defense-in-depth
que combina naturalmente. M5 é trivial. Um release coeso com narrativa
clara ("pipeline de erros unificado") vence 3-4 releases fragmentados.

### 2.6 Mudança de contrato aceitável

Remover os `try/except` em `cmd_play` etc. muda a shape do JSON de
erro no stdout. Antes:
```json
{"error": "Something went wrong", "code": "PLAYBACK_ERROR"}
```
Depois (via `main()`):
```json
{"error": {"code": "RateLimitError", "title": "...", "suggested_actions": [...], "agent_hint": "..."}}
```
Pre-alpha, zero consumidor externo. CHANGELOG documenta explicitamente.

---

## 3. Design

### 3.1 Padrão de narrowing (M1, M2)

Substituir `except Exception` por duplo-catch:

```python
try:
    existing = sp.current_user_playlists(limit=50).get("items", [])
except MaestraError:
    raise  # AuthError/RateLimit/API → pipeline central
except Exception:
    return desired  # shape inesperada da API → fallback benigno
```

A presença de `except MaestraError: raise` explícito é intencional —
documenta que o fallback `except Exception` é deliberadamente limitado
a erros não-estruturados (erros de parse, shape, AttributeError).

**M1** em `_resolve_playlist_name:244-247`: aplica o padrão. Corpo do
fallback `return desired` fica inalterado.

**M2** em `onboard.run:471-480`: mesmo padrão. Corpo do fallback
`own_playlists, empty_count = [], 0` fica inalterado.

### 3.2 Narrowing simples (M3)

`cli/basic.cmd_status:164-167`:

```python
# Antes:
try:
    playlist_id = resolve_playlist_id()
except Exception:
    playlist_id = None

# Depois:
try:
    playlist_id = resolve_playlist_id()
except ConfigError:
    playlist_id = None
```

`ConfigError` é o único caso esperado (config.json ausente/malformado).
Qualquer outra exceção propaga e vai para `main()`.

### 3.3 Remoção de wrappers (M7)

Em `cli/basic.py`, remover os `try/except Exception: error(str(e), ...)`
nos 5 handlers. Código simplificado:

```python
# Antes:
def cmd_play(args, controller, **_):
    try:
        controller.play(uri=args.uri if args.uri else None)
        result = controller.now()
        output(result or {"status": "playing"}, args.human)
    except Exception as e:
        error(str(e), "PLAYBACK_ERROR")

# Depois:
def cmd_play(args, controller, **_):
    controller.play(uri=args.uri if args.uri else None)
    result = controller.now()
    output(result or {"status": "playing"}, args.human)
```

Handlers afetados:
- `cmd_play` (linha 69-75)
- `cmd_pause` (78-83)
- `cmd_next` (86-93) — conservar `time.sleep(0.5)` antes do `controller.now()`
- `cmd_queue_add` (108-113)
- `cmd_play_context` (140-158) — o `try/except` em volta de `controller.play` vira sem-wrapper; o `except Exception as e: error(str(e), "PLAYBACK_ERROR")` sai
- `cmd_queue_context` (116-137) — contém loop com `try/except` por track. Decisão: **manter** o try/except por-track (faz sentido: uma track pode falhar sem abortar o batch inteiro), mas trocar o tipo de exceção capturada para `MaestraError` com registro granular de cada falha no output em vez de usar `error()` (que aborta). Ver §3.3.1.

#### 3.3.1 `cmd_queue_context` — tratamento por-track

Este handler é exceção à regra: o loop por tracks deve tolerar falhas
parciais. Alteração:

```python
# Antes:
for track in results:
    try:
        controller.queue_add(track["uri"])
        added.append(track)
    except Exception as e:
        error(str(e), "QUEUE_ERROR")  # aborta o loop!

# Depois:
failed = []
for track in results:
    try:
        controller.queue_add(track["uri"])
        added.append(track)
    except MaestraError as e:
        # Falha em uma track não aborta o batch; registra e segue.
        failed.append({"uri": track["uri"], "error": e.to_human_dict()})

_record_curated_tracks(taste, added, context, queries_used)
output({
    "status": "queued",
    "context": context,
    "context_source": context_source,
    "added": len(added),
    "tracks": added,
    "failed": failed,  # nova chave no output
}, args.human)
```

O campo `failed` é novo no output. Se vazio, lista vazia. Não quebra
consumidores que liam só `added`.

### 3.4 SystemExit → MaestraError (M8)

`cli/onboard._interactive_choose:324-328`:

```python
# Antes:
try:
    resp = controller.sp.current_user_playlists(limit=20)
except Exception as e:
    print(f"Erro ao listar playlists: {e}")
    raise SystemExit(1) from e

# Depois:
try:
    resp = controller.sp.current_user_playlists(limit=20)
except MaestraError:
    raise  # AuthError/RateLimit → pipeline central
except Exception as e:
    from maestra_ai.core.errors import SpotifyAPIError
    raise SpotifyAPIError(
        f"Falha ao listar playlists: {e}",
        where={"step": "interactive_choose"},
    ) from e
```

Sem mais `print` + `SystemExit`. `main()` pega e renderiza.

### 3.5 Singleton reset (M4)

`core/client.py:18-39`:

```python
# Antes:
_bucket: PersistentTokenBucket | None = None
_breaker: PersistentCircuitBreaker | None = None


def _get_bucket() -> PersistentTokenBucket:
    global _bucket
    if _bucket is None:
        _bucket = PersistentTokenBucket(
            capacity=60, refill_per_sec=1.0, db_path=_ratelimit_db_path()
        )
    return _bucket


def _get_breaker() -> PersistentCircuitBreaker:
    global _breaker
    if _breaker is None:
        _breaker = PersistentCircuitBreaker(
            max_failures=3, window_sec=60, cooldown_sec=300, db_path=_ratelimit_db_path()
        )
    return _breaker

# Depois:
_BUCKETS: dict[str, PersistentTokenBucket] = {}
_BREAKERS: dict[str, PersistentCircuitBreaker] = {}


def _get_bucket() -> PersistentTokenBucket:
    path = _ratelimit_db_path()
    if path not in _BUCKETS:
        _BUCKETS[path] = PersistentTokenBucket(
            capacity=60, refill_per_sec=1.0, db_path=path
        )
    return _BUCKETS[path]


def _get_breaker() -> PersistentCircuitBreaker:
    path = _ratelimit_db_path()
    if path not in _BREAKERS:
        _BREAKERS[path] = PersistentCircuitBreaker(
            max_failures=3, window_sec=60, cooldown_sec=300, db_path=path
        )
    return _BREAKERS[path]
```

Benefício em testes: cada `tmp_path` via `monkeypatch.setenv(
"MAESTRA_STATE_DIR", ...)` gera uma entrada nova no dict, sem
precisar resetar manualmente.

### 3.6 Anti-loop cap (M6)

`core/onboard._fetch_own_playlists`:

```python
# Antes:
def _fetch_own_playlists(sp, me_id, *, progress_cb=None):
    playlists = []
    empty_count = 0
    offset = 0
    while True:
        resp = sp.current_user_playlists(limit=50, offset=offset)
        items = resp.get("items", [])
        if not items:
            break
        # ... lógica ...
        if resp.get("next") is None:
            break
        offset += 50
    return playlists, empty_count

# Depois:
_PLAYLIST_PAGE_CAP = 200  # 200 × 50 = 10_000 playlists (Spotify hard limit)

def _fetch_own_playlists(sp, me_id, *, progress_cb=None):
    playlists = []
    empty_count = 0
    offset = 0
    for _ in range(_PLAYLIST_PAGE_CAP):
        resp = sp.current_user_playlists(limit=50, offset=offset)
        items = resp.get("items", [])
        if not items:
            break
        # ... lógica mesma ...
        if resp.get("next") is None:
            break
        offset += 50
    return playlists, empty_count
```

Se chegar a 200 iterações sem `next=None` e sem `items=[]`, sai do
loop silenciosamente — é defense-in-depth contra bug de servidor/mock.

### 3.7 Docstring (M5)

`core/audit.py:_redact`:

```python
def _redact(data: Any) -> Any:
    """Redige valores de chaves sensíveis.

    Chaves em `_SECRET_KEYS` casam por igualdade exata (lowercase).
    Chaves como `"user_email"` ou `"refresh_token_ttl"` NÃO casam —
    se precisar redactar variantes, adicionar explicitamente ao set.
    """
    if isinstance(data, dict):
        return {k: ("REDACTED" if k.lower() in _SECRET_KEYS else _redact(v)) for k, v in data.items()}
    ...
```

---

## 4. Arquivos afetados

| Arquivo | Tipo | Mudança |
|---|---|---|
| `core/onboard.py` | Modify | M1 narrowing (L244-247), M2 narrowing (L471-480), M6 cap (L122-145) |
| `core/audit.py` | Modify | M5 docstring |
| `core/client.py` | Modify | M4 dict cache |
| `cli/basic.py` | Modify | M3 ConfigError, M7 remove wrappers em 5 handlers + adaptação em `cmd_queue_context` |
| `cli/onboard.py` | Modify | M8 SystemExit → SpotifyAPIError |
| `tests/unit/test_onboard.py` | Add | propaga AuthError em M1; cap 200 em M6 |
| `tests/unit/test_client.py` | Add | dict cache por db_path em M4 |
| `tests/unit/test_cli_basic.py` | Modify+Add | remove testes de `PLAYBACK_ERROR`/`QUEUE_ERROR` string; novo propaga RateLimitError; novo `failed` field em queue_context |
| `tests/unit/test_cli_onboard.py` | Add | propaga AuthError em `_interactive_choose` |
| `packages/maestra-ai/pyproject.toml` | Modify | bump 0.6.1a0 → 0.6.2a0 |
| `packages/maestra-mcp/pyproject.toml` | Modify | bump + pin |
| `CHANGELOG.md` | Add | seção [0.6.2-alpha.0] |
| `docs/reviews/2026-04-19-v060-post-release.md` | Touch | marcar M1-M8 fechados |

---

## 5. Testes

### 5.1 Novos

- `test_onboard.py::TestResolvePlaylistName::test_propaga_auth_error_e_nao_silencia` — mock `sp.current_user_playlists` levanta `AuthError`; confere que `_resolve_playlist_name` re-raise em vez de retornar desired.
- `test_onboard.py::TestFetchOwnPlaylistsCap::test_para_em_200_paginas_mesmo_com_next_infinito` — mock sempre retorna `{"items": [...], "next": "..."}`; `_fetch_own_playlists` para em <=200 iterações, não loop infinito.
- `test_client.py::TestBucketCache::test_get_bucket_instancia_nova_quando_db_path_muda` — dois `monkeypatch.setenv("MAESTRA_STATE_DIR", ...)` em sequência; `_get_bucket()` antes vs depois são instâncias diferentes (`id(a) != id(b)`).
- `test_cli_basic.py::TestCmdPlayPropagaMaestraError::test_rate_limit_nao_vira_string` — `controller.play` levanta `RateLimitError`; chamar `cmd_play` diretamente deve re-raise (não chamar `error(str(e), "PLAYBACK_ERROR")`).
- `test_cli_basic.py::TestQueueContextFailedField::test_falhas_por_track_registradas_em_failed` — 2 tracks, primeira ok, segunda levanta `SpotifyAPIError`; output inclui `added: [t1]` e `failed: [{"uri": t2.uri, "error": {...}}]`.
- `test_cli_onboard.py::TestInteractiveChoosePropaga::test_auth_error_nao_vira_system_exit` — `sp.current_user_playlists` levanta `AuthError`; `_interactive_choose` propaga em vez de `SystemExit`.

### 5.2 Atualizados

- `test_cli_basic.py` — qualquer teste que asserta `code == "PLAYBACK_ERROR"` ou `code == "QUEUE_ERROR"` em response: adaptar para esperar `MaestraError` propagado.
- Verificar: nenhum teste assume silêncio de `_resolve_playlist_name` quando há erro de rede.

### 5.3 Regressão

Suite inteira:
- maestra-ai: 467 → ~473 (+6 novos; alguns atualizados).
- maestra-mcp: 39 (inalterado).

---

## 6. Critérios de aceite

1. `grep "except Exception" packages/maestra-ai/src/maestra_ai/cli/basic.py` retorna apenas ocorrências com justificativa explícita (comentário adjacente) ou zero.
2. `grep "SystemExit" packages/maestra-ai/src/maestra_ai/cli/onboard.py` retorna apenas ocorrências em bloco `if __name__ == "__main__"` (se houver) — não em handlers.
3. Cap de 200 páginas em `_fetch_own_playlists` documentado com comentário explicativo.
4. `_BUCKETS`, `_BREAKERS` são dicts — `grep "_bucket: PersistentTokenBucket | None" client.py` retorna zero.
5. Suite: ~473 + 39 = ~512 passed, zero falhas.
6. `pyproject.toml` bumped para `0.6.2a0`; pin atualizado em maestra-mcp.
7. CHANGELOG [0.6.2-alpha.0] com seção "Changed (breaking — output)" listando a mudança de shape em erros de CLI.

---

## 7. Não-objetivos

- Não tocar Nits N1-N5 (F401 em onboard.py, dead code SERVICE/USER, docstring envelhecida, SPOTIFY_SEARCH_PAGE_LIMIT, testes MCP faltantes).
- Não criar `cli/_errors.py` ou outro refactor mais amplo de error handling.
- Não unificar `error()` helper (utilizado por caminhos de UI sem exceção, ex: `error("Nenhum resultado encontrado.", "NO_RESULTS")` em `cmd_search`). Esses `error()` continuam — representam sinalização de estado, não tratamento de exceção.
- Não reformar `_call_spotify` ou adicionar novos tipos de erro.
- Não adicionar retry automático em RateLimitError do lado CLI.

---

## 8. Riscos e mitigações

| Risco | Prob. | Mitigação |
|---|---|---|
| Teste consumindo `"PLAYBACK_ERROR"` como string literal rompe | Alta | Inventariar via grep + atualizar todos; documentar mudança de contrato no CHANGELOG. |
| Usuário consumindo JSON do CLI em scripts lambda quebra | Zero (não existe) | Pre-alpha, user único é o Léo; CHANGELOG registra. |
| `raise SpotifyAPIError(from e)` perde `http_status` do original | Baixa | `from e` preserva traceback; `SpotifyAPIError` aceita `status` kwarg; se necessário, copiar `getattr(e, "http_status", 0)`. |
| Cap de 200 páginas vira bug se Spotify aumentar limite | Baixíssima | Spotify limit é 10k; 200×50 cobre exato. Comentário aponta a origem. |

---

## 9. Referências

- Review: `docs/reviews/2026-04-19-v060-post-release.md` (M1-M8).
- Pipeline central: `cli/__init__.py:238-255` (try/except MaestraError em main).
- `_call_spotify`: `core/client.py:42-71` (tradução para MaestraError).
- Exemplo de tratamento por-track: nenhum hoje; `cmd_queue_context` vira primeiro caso documentado.
