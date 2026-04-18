# v0.3.0 — Auth & Onboard (Design Spec)

**Data:** 2026-04-18
**Versão alvo:** v0.3.0
**Origem:** adaptação do plano original
`~/.claude/iris/docs/superpowers/plans/2026-04-16-maestra-ai-v03-auth-onboard.md`
ao estado atual do código pós-v0.2.5.
**Revisor:** Iris (Claude Opus 4.7) + Léo
**Status:** draft — aguardando aprovação do Léo.

---

## Goal

Transformar o maestra-ai de "pré-alpha com stubs de auth" em "sistema
operacional na máquina do usuário sem custo recorrente". Após v0.3.0:

- `maestra auth setup` registra credenciais do Spotify App no config.
- `maestra auth login` obtém `refresh_token` via fluxo OAuth paste-back e
  salva via `TokenStore` (keyring preferencial; file fallback com chmod 600).
- `maestra onboard` popula `taste_profile` inicial em 6 etapas
  (top tracks × 3 janelas, saved até 1000, recently played, derivação de
  contextos sugeridos), cria playlist privada, semeia faixas.
- `maestra help <tópico>` renderiza guias conceituais (começando pelo
  `onboarding.md`).
- `SpotifyController` consome automaticamente o `refresh_token` persistido
  — fecha o gap em que `auth login` salvava mas o client não usava.

## Non-goals

Fora do escopo desta versão (ficam para Plano 4 / v0.4.0 e seguintes):

- Daemon com IPC (unix socket em `state_dir()/director.sock`).
- MCP server (`maestra` exposta como tool para agentes).
- `skip_deps=True` para comandos read-only (`taste show`, `context show`,
  `doctor` sem exigir OAuth). É dívida separada.
- Dashboard web (Plano 5).
- `auth logout` (revogação remota) — `storage.delete_refresh_token()`
  entra se for trivial, mas não é critério de conclusão.
- Device Code Flow (Spotify não expõe esse grant no momento da redação).

## Contexto: divergências do plano original

O plano original (escrito antes de v0.2.2) usa APIs que foram removidas
ou mudadas. Divergências resolvidas neste spec:

1. **`@handle_errors` morto** (removido em v0.2.2). Padrão atual:
   handler levanta `MaestraError`, `cli/__init__.py::main` serializa
   com redact (v0.2.4).

2. **`client.get_client()` inexistente**. Substituir por DI — `onboard.run`
   recebe `sp: spotipy.Spotify` como parâmetro (DI do P1-4 em v0.2.5).

3. **`SpotifyController` não lê keyring**. `__init__` atual usa
   `cache_path=config_dir/.cache`. Gap bloqueante: `auth login` salva no
   keyring e o client não consome. **Task 0 desta versão** (não existia
   no plano original).

4. **`taste.record_global_positive` inexistente**. Plano sugeria criar
   como fallback. Aqui vira work item explícito.

5. **Redirect URI política Spotify**. Spotify não aceita mais
   `localhost`/`127.0.0.1` em apps novos. Plano original assumia servidor
   HTTP local. Substituído por fluxo paste-back (zero servidor local).

## Decisões arquiteturais

### D1. Fluxo OAuth: paste-back, não server-local

Justificativa: apps Spotify criados após política de 2025 exigem redirect
URI HTTPS não-loopback. Fluxo paste-back funciona com qualquer redirect
válido pro Spotify (inclui o "callback de exemplo" `https://example.com/...`
pré-preenchido no dashboard).

Sequência:

```
1. `auth login` lê config (client_id/secret/redirect_uri).
2. Constrói URL de autorização via SpotifyOAuth.get_authorize_url().
3. Tenta webbrowser.open(); sempre imprime a URL como fallback.
4. Prompt: "Cole a URL completa de volta aqui:"
5. Parse do code via SpotifyOAuth.parse_response_code(url).
6. Troca code por token via SpotifyOAuth.get_access_token(code, as_dict=True).
7. TokenStore.save(refresh_token).
8. Retorna status ok + scopes + access_token_len.
```

Código de referência (spotipy 2.26):

```python
from spotipy.oauth2 import SpotifyOAuth

oauth = SpotifyOAuth(
    client_id=cfg["client_id"],
    client_secret=cfg["client_secret"],
    redirect_uri=cfg["redirect_uri"],
    scope=SCOPES,
    cache_handler=NoopCacheHandler(),  # não usar cache spotipy
    open_browser=False,                # nós controlamos
)
url = oauth.get_authorize_url()
# ...abrir + pedir paste...
code = oauth.parse_response_code(pasted_url)
token_info = oauth.get_access_token(code, as_dict=True, check_cache=False)
```

`NoopCacheHandler` é implementação simples para impedir spotipy de
escrever/ler cache em disco — a persistência é inteiramente nossa via
`TokenStore`.

### D2. TokenStore abstrato

Por que não só `keyring.set/get_password`: Fase 4 (MCP server) pode
precisar de backends não-keyring (testes E2E, containers sem DBus,
máquinas compartilhadas). Interface hoje, implementações depois.

```python
# core/token_store.py
from typing import Protocol

class TokenStore(Protocol):
    def save(self, refresh_token: str) -> None: ...
    def load(self) -> str | None: ...
    def delete(self) -> None: ...

class KeyringTokenStore:
    """Backend preferencial. Usa python-keyring (Secret Service/DBus)."""
    _SERVICE = "maestra-ai"
    _USER = "spotify-refresh-token"
    def save(self, refresh_token): keyring.set_password(...)
    def load(self): return keyring.get_password(...)
    def delete(self): keyring.delete_password(...)

class FileTokenStore:
    """Fallback. config_dir()/token.json com chmod 600."""
    def save(self, refresh_token):
        path = config_dir() / "token.json"
        # usa storage.atomic_write_json (v0.2.5) para evitar TOCTOU
        atomic_write_json(path, {"refresh_token": refresh_token})
        path.chmod(0o600)
    ...

def default_token_store() -> TokenStore:
    """Keyring se disponível, senão FileTokenStore.

    Migra de storage.save_refresh_token (v0.2.x) — função mantida como
    shim que delega para default_token_store().save().
    """
```

Shim em `core/storage.py`:

```python
def save_refresh_token(token):  # mantido por retrocompat
    from maestra_ai.core.token_store import default_token_store
    default_token_store().save(token)

def load_refresh_token():  # mantido
    from maestra_ai.core.token_store import default_token_store
    return default_token_store().load()
```

### D3. SpotifyController consome TokenStore

Pós-v0.2.5 o controller tem DI via `sp` e `auth_manager`. Nova lógica:

```python
class SpotifyController:
    def __init__(self, sp=None, auth_manager=None, token_store=None):
        if sp is not None:
            self.sp = sp
            return
        if auth_manager is None:
            cfg = storage.read_config()
            store = token_store or default_token_store()
            refresh_token = store.load()
            auth_manager = SpotifyOAuth(
                client_id=cfg.get("client_id"),
                client_secret=cfg.get("client_secret"),
                redirect_uri=cfg.get("redirect_uri"),
                scope=" ".join(self.DEFAULT_SCOPES),
                cache_handler=_InMemoryCacheHandler(refresh_token),
                open_browser=False,
            )
        self.sp = spotipy.Spotify(auth_manager=auth_manager)
```

`_InMemoryCacheHandler` injeta o refresh_token no spotipy via API de
cache handler (spotipy chama `.get_cached_token()`/`.save_token_to_cache()`).
Implementação: guarda em dict in-process, popula a partir do refresh_token
do `TokenStore`, spotipy renova o access_token automaticamente.

**Remove `load_dotenv(cfg / ".env")`** — legado do monorepo antigo.
Credenciais lidas exclusivamente de `storage.read_config()`.

### D4. onboard.run recebe sp via DI

```python
# core/onboard.py
def run(sp, *, playlist_name, seed_count=30, dry_run=False, progress_cb=None):
    ...
```

Caller em `cli/onboard.py`:

```python
def _handle(args, controller, taste, **_):
    report = onboard.run(controller.sp, playlist_name=..., ...)
```

Elimina `_get_spotipy()` problemático do plano original.

### D5. Paste-back UX

O prompt de paste precisa ser robusto:

- Aceita URL inteira OU só o `code` (alguns browsers escondem a URL após
  erro de carregamento — usuário pode colar só o fragmento).
- Validação: se URL, extrai `code` via `parse_response_code`; se não
  parece URL, assume ser o code puro.
- `state` parameter: spotipy gera por default. Validar em `parse_response_code`
  evita CSRF (mesmo em CLI, boa higiene).
- Timeout: sem timeout. Usuário pode demorar (precisar logar, etc.).

Erros previstos com mensagem humana:
- Code inválido → `AuthError("Code não reconhecido. Rode novamente.")`
- `state` mismatch → `AuthError("State mismatch; possível CSRF. Rode novamente.")`
- Token exchange falhou → `AuthError(str(e))` com redact (já coberto por v0.2.4).

## Componentes (visão geral)

```
core/
├── auth.py            [NOVO] setup(), login()
├── onboard.py         [NOVO] run(sp, ...)  — 6 etapas
├── token_store.py     [NOVO] Protocol + Keyring/File impls
├── client.py          [MODIFY] consome TokenStore
├── storage.py         [MODIFY] save/load_refresh_token viram shim
└── taste.py           [MODIFY] + record_global_positive()

cli/
├── auth.py            [REWRITE] setup, login (paste-back)
├── onboard.py         [REWRITE] rich UX
└── help.py            [NOVO] maestra help <tópico>

docs/topics/           [NOVO]
└── onboarding.md

tests/unit/
├── test_auth.py       [NOVO]
├── test_onboard.py    [NOVO]
├── test_token_store.py [NOVO]
├── test_help.py       [NOVO]
├── test_client.py     [EXPAND] (token_store injection)
└── test_storage.py    [EXPAND] (shim behavior)

tests/integration/
└── test_cli_e2e.py    [EXPAND] auth setup sem secret, help
```

## Data flow — Onboard

```
cli onboard --playlist-name "Maestra"
    │
    ├─ confirm prompt (rich) + preview de custo
    │
    ├─ onboard.run(controller.sp, playlist_name=..., seed_count=30)
    │    ├─ step 1: cria playlist (sp.user_playlist_create) + salva id em config
    │    ├─ step 2-4: top tracks (long/medium/short) via sp.current_user_top_tracks
    │    ├─ step 5: saved tracks paginado (cap 1000) via sp.current_user_saved_tracks
    │    ├─ step 6: recently played via sp.current_user_recently_played
    │    ├─ compute_weights: Counter com pesos long=3, medium=2, short=2, saved=1, recent=1
    │    ├─ taste.record_global_positive(uri, weight) para cada uri
    │    ├─ seed playlist com top_short[:seed_count]
    │    └─ derive_suggestions: top artists → 5 contextos textuais
    │
    └─ panel de relatório (rich) ou JSON
```

## Error handling

Todos os erros são `MaestraError` (hierarquia v0.2.0+). Redact
automático via `cli/__init__.py::main` (v0.2.4).

| Caso | Exceção |
|------|---------|
| `auth setup` sem args interativos e stdin não-tty | `UserError("Use --client-id/--client-secret em ambiente não interativo.")` |
| `auth login` sem config | `ConfigError` (já coberto por storage.read_config em v0.2.4) |
| `auth login` code inválido | `AuthError` |
| `auth login` state mismatch | `AuthError` |
| `onboard` sem token | `AuthError` (via SpotifyController → _call_spotify → 401) |
| `onboard` playlist já existe com mesmo nome | **Decisão:** criar com sufixo numérico. Não é erro. |
| `onboard` rate limited (429) | `RateLimitError` (já coberto) — usuário re-roda depois |
| `help` tópico inexistente | exit 1 + lista tópicos disponíveis (não é exceção) |

## Testing strategy

### Unit tests (pytest + pytest-mock + responses)

- `test_auth.py` (~8 testes):
  - `setup` grava config corretamente (client_id/secret/redirect_uri).
  - `setup` com env var override ainda funciona.
  - `login` sem config levanta `ConfigError`.
  - `login` fluxo paste-back happy path (mock `SpotifyOAuth`).
  - `login` code inválido levanta `AuthError`.
  - `login` state mismatch levanta `AuthError`.
  - `login` sem refresh_token na resposta levanta `AuthError`.
  - `login` persiste via `TokenStore` mockado.

- `test_token_store.py` (~6 testes):
  - `KeyringTokenStore.save/load/delete` round-trip (keyring mockado).
  - `FileTokenStore.save` cria arquivo com chmod 600.
  - `FileTokenStore.load` retorna `None` se ausente ou corrompido (reuso do P0-N1 de v0.2.4).
  - `default_token_store()` prefere keyring quando disponível.
  - `default_token_store()` cai para file quando keyring falha.
  - Shim `storage.save/load_refresh_token` delega.

- `test_onboard.py` (~10 testes):
  - Paginação respeita cap de 1000.
  - Biblioteca vazia retorna status ok com zeros.
  - `_compute_weights` com exemplos do plano original.
  - `_derive_suggestions` retorna 5 strings.
  - `run(dry_run=True)` não chama `playlist_create` nem `playlist_add_items`.
  - `run` salva `playlist_id` em config após criar.
  - `run` incrementa `taste.record_global_positive` para cada URI.
  - Progress callback recebe `{"step": N, ...}` em todas as 6 etapas.
  - Playlist nome duplicado ganha sufixo `(2)`.
  - Refresh_token ausente → `AuthError` via _call_spotify mock.

- `test_client.py` (expandir +3):
  - Controller sem args com refresh_token no TokenStore usa `_InMemoryCacheHandler`.
  - Controller com `token_store=MockStore` ignora default.
  - Controller sem `.env` não toca `load_dotenv` (remove dep).

- `test_help.py` (~3 testes):
  - `_list_topics` inclui `onboarding`.
  - `_topic_path("onboarding")` retorna conteúdo não-vazio.
  - `_topic_path("inexistente")` retorna None.

### Integration tests (subprocess real)

Expandir `test_cli_e2e.py`:

- `auth setup --client-id X --client-secret Y --redirect-uri Z` grava config
  em tmp isolado e retorna exit 0.
- `auth setup` sem args em stdin não-tty levanta exit != 0 com msg humana.
- `help onboarding` renderiza sem crash.
- `help` (sem arg) lista tópicos.

`auth login` e `onboard` não têm E2E porque dependeriam de token real —
cobertos por unit tests com mocks.

## Security considerations

- **Redirect URI user-provided** — não validamos formato além de ser string.
  Se usuário colar algo malicioso, só ele mesmo se prejudica (o URI sai no
  authorize_url). Não é vetor de injection.
- **Paste-back URL** — validamos `state` parameter contra CSRF. Se alguém
  enviar URL com code roubado mas state diferente, `parse_response_code`
  rejeita.
- **Keyring fallback para file** — chmod 600 + diretório config_dir
  (próprio do usuário) garantem isolamento. Token_store via `atomic_write_json`
  (v0.2.5) fecha janela de corrupção concorrente.
- **Redact em logs/errors** — já coberto por v0.2.4 (`redact_str`
  em `cli/_common.py::error` e `redact_error_dict` em `main`).
- **`open_browser=False` explícito** — spotipy não abre browser (nós controlamos).
  Evita situação de browser abrir durante `onboard` inesperadamente.

## Backward compatibility

- `storage.save_refresh_token` / `load_refresh_token` permanecem como
  shims delegando para `default_token_store()`. Callers existentes em
  `test_storage.py` (v0.2.x) e `client.py` continuam funcionando.
- `SpotifyController()` sem args mantém comportamento de instanciar OAuth
  default — agora com `TokenStore` automático. Callers em `basic.py`,
  `director.py`, etc. não mudam.
- `load_dotenv(cfg / ".env")` é **removido**. Documentado no CHANGELOG como
  breaking para quem usava `.env` (provavelmente ninguém — legado).

## Triggers for revision

Se qualquer um ocorrer durante implementação, revisar este spec antes de continuar:

- **spotipy 3.x released** com API de `SpotifyOAuth`/cache handler mudada.
- **Spotify mudou políticas de redirect URI novamente** (pode forçar mudança de fluxo).
- **Playlist já existe com mesmo nome** — design atual cria com sufixo numérico; revisar se
  feedback do Léo indicar preferência por reuso.
- **Escopo `user-library-read` bloqueado em Dev Mode** — reduzir escopos solicitados.
- **Keyring com backend alvo (secretstorage) indisponível na máquina alvo**
  — validar que FileTokenStore cobre antes de shipar.

## Critérios de conclusão

- [ ] `maestra auth setup --client-id X --client-secret Y --redirect-uri Z` grava config em tmp isolado.
- [ ] `maestra auth login` completa fluxo paste-back com mocks (unit) e real (manual).
- [ ] `maestra onboard --playlist-name X --yes` roda de ponta a ponta.
- [ ] `SpotifyController()` sem args consegue fazer `sp.current_user()` após `auth login` real.
- [ ] `maestra help onboarding` renderiza.
- [ ] Suite: 249 → ~285 passed (~36 testes novos distribuídos conforme a seção "Testing strategy").
- [ ] CHANGELOG `[0.3.0]` escrito e completo.
- [ ] Tag `v0.3.0` criada e pushada.
- [ ] README menciona `auth setup` / `auth login` / `onboard` como primeiros passos.

## Tasks (resumo executivo — detalhamento no plano de execução)

1. **Token store + client consumer (bloqueante):**
   - `core/token_store.py` com Protocol + `KeyringTokenStore` + `FileTokenStore`.
   - `core/storage.py` shim: `save/load_refresh_token` delegam para `default_token_store()`.
   - `core/client.py` consome `TokenStore` + `_InMemoryCacheHandler`; remove `load_dotenv`.
2. Adicionar `responses>=0.25` em dev deps.
3. `core/auth.py` (paste-back) + `cli/auth.py` reescrito + tests.
4. `core/onboard.py` + `taste.record_global_positive` + tests.
5. `cli/onboard.py` com rich UX + smoke test.
6. `cli/help.py` + `docs/topics/onboarding.md` + hatch config.
7. Bump v0.3.0 + CHANGELOG + tag.

Task 1 é bloqueante — qualquer coisa depois dela depende do client consumir
token persistido. Ordem acima é a ordem de execução sem reordenar.

---

## Próximo passo

Invocar `superpowers:writing-plans` para gerar `docs/superpowers/plans/2026-04-18-v030-auth-onboard.md` com steps executáveis checkbox.
