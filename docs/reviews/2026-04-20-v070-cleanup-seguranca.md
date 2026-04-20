# Code review v0.7.0 — limpeza + segurança
**Data:** 2026-04-20
**Escopo:** dead code + security scan pós-v0.7.0-alpha.0
**Commit base:** 69d6573 (tag v0.7.0-alpha.0)
**Ferramentas:** ruff 0.15.11, pytest 9.0.3 (507 passed), grep semântico, leitura manual de 40 módulos.

## Sumário

- **Dead code encontrado:** 14 achados (6 remover / 6 talvez / 2 manter com justificativa).
- **Segurança:** 10 achados (1 CRÍTICO, 3 IMPORTANTES, 6 MENORES).
- **Ruff base:** 26 erros reportados (14 I001, 6 F401, 1 F821, 1 F841, 1 N806, 1 N818, 1 UP017, 1 UP037) — a maioria auto-fixable.

---

## Dead code

### D1 🔴: TypedDicts exportados em `onboard_types.py` sem consumidor real

- **Arquivo:** `packages/maestra-ai/src/maestra_ai/core/onboard_types.py:38-99`
- **Achados individuais:**
  - `SelectedPlaylist` (linha 38) — nunca importada; `onboard.py` constrói o dict inline em `expansion_info["selected_playlists"].append({"id": ..., "name": ...})` sem referenciar o tipo.
  - `FailedPlaylist` (linha 43) — idem; inline em `expansion_info["failed_playlists"].append({"id": pid, "reason": str(fetch_err)[:80]})`.
  - `ExpansionReason` (Literal, linha 48) — usado só como anotação de `ExpansionInfo.reason` (dentro do mesmo módulo); nenhum consumidor externo.
  - `OnboardSignals` (linha 68) — docstring e release notes dizem que é retornado por `_derive_suggestions`, mas a assinatura real retorna `tuple[list[str], list[dict], dict]` sem anotação. Nem `onboard.py` nem `cli/onboard.py` nem `tools.py` importam.
  - `TrackRationale` (linha 83) — idem: definida, documentada em plans, nunca importada.
  - `RationaleEntry` (linha 94) — idem: `_build_rationale` retorna `dict` não anotado; `rationale_entries` em `run()` é `list[dict]`.
- **Evidência:** `rg "OnboardSignals|TrackRationale|RationaleEntry|SelectedPlaylist|FailedPlaylist|ExpansionReason" packages/` retorna matches apenas em `onboard_types.py`, em CHANGELOG/docs/plans, e ZERO em outros arquivos `.py` de produção ou testes.
- **Impacto:** module tem 103 linhas, das quais ~60 são definições mortas. Documentação promete contratos que o código não exerce — agentes externos que acreditassem na release note v0.7.0 importariam nomes que não refletem a API real.
- **Ação:** ou (a) remover `SelectedPlaylist`/`FailedPlaylist`/`ExpansionReason` e aplicar os tipos restantes onde fazem sentido (`_derive_suggestions` retorno, `expansion_info.selected_playlists`/`failed_playlists` item type), ou (b) remover todos os seis. Recomendo (a) — custo baixo e dá valor real ao plan v0.7.0 e ao contrato do onboard. Se escolher (b), atualizar o CHANGELOG v0.7.0-alpha.0 retirando a menção a `OnboardSignals`/`TrackRationale`/`RationaleEntry` na seção "Adicionado".
- **Severidade:** 🔴 remover ou aplicar (escolha consciente; manter como está é pior que ambos).

### D2 🔴: `_stub` em `cli/config.py`

- **Arquivo:** `packages/maestra-ai/src/maestra_ai/cli/config.py:29-33`
- **Evidência:** `rg "_stub" packages/` retorna apenas a própria definição. O comentário diz "argparse já exige subparser (required=True) — mas manter por segurança". Mas `sub = config_parser.add_subparsers(dest="config_command", required=False)` — não exige. O fallback real é `group_help_handler(config_parser)` setado na linha 100.
- **Ação:** remover.
- **Severidade:** 🔴 remover — 5 LoC, sem callers.

### D3 🔴: `_pid_running` em `cli/_common.py:90-95`

- **Arquivo:** `packages/maestra-ai/src/maestra_ai/cli/_common.py:90`
- **Evidência:** `rg "_pid_running" packages/` — duas definições. A de `_common.py` nunca é importada (todos os callers — `cli/doctor.py`, `core/director.py` — usam `core.director._pid_running`).
- **Ação:** remover de `_common.py`.
- **Severidade:** 🔴 remover — duplicata legado.

### D4 🔴: `_signal_weight` shim em `cli/_common.py:156-159`

- **Arquivo:** `packages/maestra-ai/src/maestra_ai/cli/_common.py:156`
- **Evidência:** o rename v0.6.1 (`_signal_weight` → `signal_weight`) deixou o shim como bridge; todos os callers atuais (`cli/_common.py` módulo próprio + `core/history.py:179`) usam `taste_mod.signal_weight` direto ou `from maestra_ai.core.taste import signal_weight`. O shim `_signal_weight` nunca é chamado.
- **Ação:** remover.
- **Severidade:** 🔴 remover — compatibility shim obsoleto.

### D5 🟡: `_prune_candidates` e `_context_review` shims em `cli/_common.py:123,150`

- **Arquivo:** `packages/maestra-ai/src/maestra_ai/cli/_common.py:123,150`
- **Evidência:** `_prune_candidates` é usado em `cli/taste.py:10,29`. `_context_review` usado em `cli/taste.py:25`. Ambos poderiam ser substituídos por imports diretos de `maestra_ai.core.taste`.
- **Ação:** manter como shim OU inline em `cli/taste.py`. O shim adiciona 6 LoC por função para economizar 2 LoC de import — não vale. Sugiro inline: `from maestra_ai.core import taste as taste_mod` em `cli/taste.py` e chamar `taste_mod.prune_candidates(...)`/`taste_mod.review(...)` direto.
- **Severidade:** 🟡 talvez — não é morto, mas é gordura de abstração.

### D6 🔴: `_prune_candidates_fn` alias em `taste.py:554`

- **Arquivo:** `packages/maestra-ai/src/maestra_ai/core/taste.py:553-554`
- **Evidência:** comentário diz "Alias para uso interno em `review`, onde o parâmetro homônimo ocultaria a função". Usado uma vez em `taste.py:614`. A solução mais limpa é renomear o parâmetro `prune_candidates=None` de `review(...)` para `prune_candidates_override=None` (ou similar) e chamar `prune_candidates(...)` direto no corpo, eliminando o alias.
- **Ação:** remover o alias, renomear parâmetro. Alternativa: renomear a variável local que recebe o override (hoje é `prunable` após a v0.6.1).
- **Severidade:** 🔴 remover — é exatamente o "compatibility shim criado para contornar problema" mencionado no brief.

### D7 🟡: `_flag_keyring_used` e `_flag_keyring_used_get` em `storage.py:194,202`

- **Arquivo:** `packages/maestra-ai/src/maestra_ai/core/storage.py:194-203`
- **Evidência:** `rg "_flag_keyring_used" packages/` retorna apenas as duas definições. Zero callers em código ou testes. Produziam o arquivo `token.keyring.flag` — atualmente nem escrito nem lido por ninguém.
- **Ação:** remover as duas funções (10 LoC). Considerar se há código legado em outro repo que dependia do flag file (unlikely após a migração para `default_token_store`).
- **Severidade:** 🟡 talvez — sem callers hoje, mas o flag file pode aparecer em instalações antigas. Se remover, não há lógica de cleanup — o arquivo fica órfão até o usuário apagar `~/.config/maestra/`. Considerar adicionar cleanup em `auth login` seguinte OU deixar arquivo esquecido (inofensivo).

### D8 🟡: `_keyring_backend_ok` duplicado (`storage.py:168` vs `token_store.py:36`)

- **Arquivo:** `packages/maestra-ai/src/maestra_ai/core/storage.py:168-175` e `token_store.py:36-52`
- **Evidência:** duas implementações quase idênticas do mesmo check. A de `token_store.py` é mais recente (checa `null`/`fail` em `__module__`). A de `storage.py` é usada por `doctor.py:108`. Divergem na precisão do check ("fail in type name" vs "fail/null in module").
- **Ação:** `doctor.py` deveria chamar `token_store._keyring_backend_ok` (o mais robusto) e remover a de `storage.py`.
- **Severidade:** 🟡 talvez — duplicação técnica, `doctor` pode reportar "ok" em casos que `token_store` acertadamente descartaria.

### D9 🟢: `TokenBucket` e `CircuitBreaker` in-memory em `ratelimit.py:18,52`

- **Arquivo:** `packages/maestra-ai/src/maestra_ai/core/ratelimit.py:18-93`
- **Evidência:** `rg "TokenBucket\b|CircuitBreaker\b"` sem prefixo `Persistent` — só matches em `tests/unit/test_ratelimit.py`. Produção usa apenas `PersistentTokenBucket`/`PersistentCircuitBreaker`.
- **Ação:** manter — são exercidos por testes dedicados (`TestTokenBucket`, `TestCircuitBreaker`). Úteis como referência de algoritmo e como smoke test das versões Persistent*. Removê-los exigiria remover os testes também (regressão de cobertura).
- **Severidade:** 🟢 manter — documentados no docstring do módulo e servem para comparação/regressão.

### D10 🟡: `TasteProfile.filter` e `TasteProfile.filter_with_artist_info` em `taste.py:465,472`

- **Arquivo:** `packages/maestra-ai/src/maestra_ai/core/taste.py:465-478`
- **Evidência:** `rg "\.filter\(|\.filter_with_artist_info"` retorna apenas matches em `tests/unit/test_taste.py:340,350`. Zero callers em produção. `curator.curate` filtra inline via `is_rejected` + `get_rejected_artists`.
- **Ação:** ou remover (e seus testes), ou aplicar em `curator.py:76-89` para enxugar o loop. Prefiro aplicar — o test_taste.py testa exatamente o comportamento que `curator.curate` reimplementa à mão.
- **Severidade:** 🟡 talvez — API pública do `TasteProfile`, mas sem consumidor real; decide o dono.

### D11 🟡: `HistoryAnalyzer.analyze` e `_context_query_candidates`

- **Arquivo:** `packages/maestra-ai/src/maestra_ai/core/history.py:11,128,249`
- **Evidência:** `analyze` é chamado apenas por `cli/history.py::cmd_history_analyze` — subcomando CLI existente (`maestra history analyze`). Não há tool MCP equivalente. Retorna `suggestions.context_query_candidates` (`_context_query_candidates`) que só agrega gêneros em dois buckets ("foco" e "energia") — cobertura bem limitada e cliente não-descoberto.
- **Ação:** manter `analyze` (subcomando ativo), mas `_context_query_candidates` gera valor duvidoso — é heurística estática que nunca foi calibrada. Considerar simplificar/remover na v0.8.
- **Severidade:** 🟡 talvez — não é morto, é baixa utilidade.

### D12 🔴: F401 imports em produção (já detectados por ruff)

- **Arquivos/linhas:**
  - `core/audit.py:9` — `import json` não usado.
  - `core/director.py:2` — `import json` não usado.
  - `core/onboard.py:581` — `from pathlib import Path` dentro de `_persist_rationale` não usado (causa F821 porque a type hint `"Path"` do retorno se refere a um nome que não existe no escopo do módulo).
- **Ação:** remover os 3 imports + corrigir a anotação `-> "Path"` em `onboard.py:574` para `-> Path` com import no topo do módulo (ou trocar para `-> object`/remover).
- **Severidade:** 🔴 remover — trivial, auto-fixable por ruff.

### D13 🟡: `_NoopCacheHandler` em `core/auth.py:38`

- **Arquivo:** `packages/maestra-ai/src/maestra_ai/core/auth.py:38-51`
- **Evidência:** usado uma vez, em `auth.login` linha 105. Vivo. Mas a classe é o tipo de helper que poderia morar inline via `cache_handler=type("_NoopCache", (CacheHandler,), {"get_cached_token": lambda self: None, "save_token_to_cache": lambda *_: None})()`. Manter como está é mais legível.
- **Ação:** manter.
- **Severidade:** 🟢 manter — limpo como está.

### D14 🔴: Variável `report` não usada em `test_onboard.py:1549`

- **Arquivo:** `packages/maestra-ai/tests/unit/test_onboard.py:1549` (F841)
- **Evidência:** ruff F841. `report = onboard.run(...)` sem nenhum assert posterior sobre `report`. O teste só verifica side effects do disco.
- **Ação:** substituir por `onboard.run(...)` direto.
- **Severidade:** 🔴 remover — 1 char.

---

## Segurança

### S1 [CRÍTICO] — MCP boundary não redige secrets antes de retornar ao cliente

- **Arquivo:** `packages/maestra-mcp/src/maestra_mcp/server.py:100-109`, `tools.py:86-97`
- **Problema:** a CLI passa toda saída de erro por `redact_error_dict` (redução de regex em `what_happened`/`title` e redução por chave em `where`/`body`) antes de `print` (veja `cli/__init__.py:246-255`). O MCP server NÃO aplica nada equivalente — `tools.call_tool` constrói `{"error": {"code": ..., "what_happened": str(e)}}` para exceções não-`MaestraError` (linhas 90-96) e `server.py:100-109` simplesmente faz `json.dumps(result)` na `TextContent`.

  Vetores concretos de leak:
  - `str(SpotifyException)` do spotipy embute Authorization Bearer <token> em 401/403 — o caminho da CLI trata via `redact_str`, o caminho MCP não.
  - `MaestraError.to_human_dict()` retorna `where` com campos não redijidos (o email já está em `_SECRET_KEYS`, mas `what_happened` construído via f-string — como `PlaylistCreateForbiddenError` — não passa por `redact_str`).
  - A linha 100-104 chama `audit.log(name, args, log_result)` que redige antes de gravar em disco — prova que o time já reconhece a necessidade, mas o lado do cliente é desprotegido.

- **Impacto:** agente MCP recebe tokens Bearer, client_secret ou refresh_token em claro em casos de erro — exatamente o cenário que `redact_error_dict` foi criado para evitar. Como o JSON vai direto para o agente LLM, o token entra no prompt de sistemas downstream (conversas salvas, logs de provedor).

- **Fix sugerido:** em `server.py:_build_call_tool_handler`, aplicar `redact_error_dict` quando `result` contém chave `"error"` (ou `redact_str` + `_redact` separado em campos sensíveis). Exemplo:
  ```python
  from maestra_ai.core.security import redact_error_dict
  if isinstance(result, dict) and "error" in result:
      result = {**result, "error": redact_error_dict(result["error"])}
  ```
  E em `tools.py:call_tool` — envolver o fallback `str(e)` (linha 94) com `redact_str`.

### S2 [IMPORTANTE] — `PlaybackObserver._append_events` escreve sem lock

- **Arquivo:** `packages/maestra-ai/src/maestra_ai/core/playback.py:130-137`
- **Problema:** abre `log_path` em modo `"a"` sem `fcntl.flock`. Payloads > PIPE_BUF (~4KB) podem intercalar entre processos. Contraste com `storage.append_jsonl_locked` (usado por `core.director._record`). O arquivo alvo `playback_events.jsonl` é lido por `PlaybackEventProcessor.process()` — leitura por linha, então corrupção por intercalação vira `json.JSONDecodeError` silenciosamente dropado (`playback_processor.py:65-66`), **causando perda de eventos sem aviso**.
- **Vetor:** não há daemon que chame `playback.observe()` hoje (só CLI manual), mas usuários com scripts pode rodar `maestra playback observe` em loop concorrente; o Director futuro + observador batem neste arquivo.
- **Fix sugerido:** substituir o loop inline por `storage.append_jsonl_locked(self.log_path, event)` por evento. O padrão já está documentado em `storage.py:118-138`.

### S3 [IMPORTANTE] — `help.py` aceita topic não sanitizado

- **Arquivo:** `packages/maestra-ai/src/maestra_ai/cli/help.py:10-17`
- **Problema:** `args.topic` vai direto para `resources.files("maestra_ai").joinpath(f"docs/topics/{topic}.md")`. Apesar de `importlib.resources` não ser um open direto, aceita `..` no path. Testei: `docs/topics/../../../../../etc/passwd.md` resolve mas `is_file()` retorna False (não existe `.md` sufixo). `docs/topics/../cli/__init__.md` idem (não existe). Mas `docs/topics/../cli/__init__.py.md`? Passa `.md` hardcoded — o sufixo bloqueia mas só por sorte. Se alguém adicionar `.md` em qualquer parte do pacote (e há: `docs/topics/*.md` e nada mais hoje), traversal vira possível.
- **Fix sugerido:** validar `topic` com regex `^[a-z][a-z0-9_-]*$` (mesmo shape de snapshot IDs) antes de construir o path, ou whitelist via `_list_topics()`.
- **Impacto hoje:** baixo (pacote não tem `.md` fora de `docs/topics/`), mas é defesa-em-profundidade barata.

### S4 [IMPORTANTE] — `director.start` vaza file descriptor

- **Arquivo:** `packages/maestra-ai/src/maestra_ai/core/director.py:276-284`
- **Problema:** `log_fd = open(log_path, "a", ...)` nunca é fechado no pai após `subprocess.Popen`. O filho herda o fd e segue gravando (OK); o pai permanece segurando o fd até o processo terminar. Em uso normal o CLI pai termina logo depois, mas o MCP server é long-lived — cada `director_start` chamado via MCP deixa um fd adicional pendente. Apenas 1-2 chamadas por sessão típica, mas em CI ou teste-stress é vazamento.
- **Fix sugerido:** `with open(...) as log_fd: proc = subprocess.Popen(cmd, stdout=log_fd, stderr=log_fd, start_new_session=True)` — o `with` fecha no pai após Popen dispatchar o fork, o filho segura sua cópia.

### S5 [MENOR] — `audit._redact` é case-insensitive no set mas case-sensitive no `.lower()`

- **Arquivo:** `packages/maestra-ai/src/maestra_ai/core/audit.py:42`
- **Problema:** `_SECRET_KEYS` é um set de strings em minúsculas, e a comparação é `k.lower() in _SECRET_KEYS`. Funciona. Mas o comentário linha 38 diz "Chaves em `_SECRET_KEYS` casam por igualdade exata (lowercase)". A igualdade é sobre a key input passada por `.lower()`. OK. Porém `"Authorization"` (variante usada em headers HTTP) NÃO está no set. Se spotipy um dia puser `{"headers": {"Authorization": "Bearer ..."}}` em `where`, `Authorization` passa por `.lower()` → `authorization` — que não está no set `{"refresh_token", "client_secret", "access_token", "password", "token", "email"}`.
- **Fix sugerido:** adicionar `"authorization"` ao `_SECRET_KEYS`. A proteção secundária via regex do `redact_str` aplicada em strings livres (`what_happened`, `title`) cobre o "Bearer ..." — mas não o valor isolado sob key "Authorization".

### S6 [MENOR] — Regex de `redact_str` não cobre JWT com header não-eyJ

- **Arquivo:** `packages/maestra-ai/src/maestra_ai/core/security.py:28-40`
- **Problema:** regex JWT começa com `eyJ[A-Za-z0-9_\-]+\.eyJ...`. Cobre o caso canônico (header `{"alg":...}` começa com `{`, que base64url é `eyJ`). Mas custom headers alternativos ou tokens opacos do Spotify (não-JWT) só são capturados via os outros braços (Bearer ou `known_key=...`).
- **Impacto:** cenário raro; spotipy usa Bearer. Mas se a lib emitir `authorization: "eyJ_outra_codificacao..."` sem Bearer prefix, passa.
- **Fix sugerido:** adicionar ramo genérico para long-base64 isolado após known-key indicator, ou aceitar e documentar limite.

### S7 [MENOR] — `config_list` redige valores mas expõe key names

- **Arquivo:** `packages/maestra-ai/src/maestra_ai/cli/config.py:36-40`
- **Problema:** `_redact(cfg)` zera valores de chaves sensíveis, mas ainda imprime os nomes (`"client_secret": "REDACTED"`). Esperado. Porém `doctor.check_config` expõe `"keys": list(cfg.keys())` no campo `details` — mesmo comportamento, confirmação que é padrão assumido.
- **Impacto:** nenhum — key names são schema, não segredo.
- **Fix:** N/A, documentar como decisão explícita.

### S8 [MENOR] — Timestamp de snapshot usa `.astimezone()` sem offset consistente

- **Arquivo:** `packages/maestra-ai/src/maestra_ai/core/snapshot.py:41`
- **Problema:** `datetime.now(UTC).astimezone().strftime(...)` aplica o fuso local do processo no timestamp-string. Dois processos em TZ diferentes (container + host) podem gerar IDs com offsets ambíguos. IDs ainda são únicos por microsegundo, mas a ordenação lexicográfica pressupõe mesma TZ.
- **Fix sugerido:** usar apenas `datetime.now(UTC).strftime(...)` sem `.astimezone()`.
- **Impacto:** baixo — ambiente homogêneo.

### S9 [MENOR] — `_onboard_rationale` lê JSON sem validar schema

- **Arquivo:** `packages/maestra-mcp/src/maestra_mcp/tools.py:472-493`
- **Problema:** `data = _json.loads(path.read_text(...))` sem `_validate_restore_payload` (padrão já estabelecido em `taste.restore`). Se o arquivo `onboard_rationale.json` for corrompido (crash mid-write, edição manual), o handler retorna dict mal-formado ou propaga `json.JSONDecodeError` crua — o boundary `server.py:91-97` captura como InternalError e aí sim vaza `str(e)` para o cliente (ver S1).
- **Fix sugerido:** validar que `data` é dict com chave `"suggestions"` antes de indexar, ou `try/except json.JSONDecodeError` → `UserError("rationale corrompido, rode onboard de novo")`.

### S10 [MENOR] — `normalize_playlist_id` permite match substring

- **Arquivo:** `packages/maestra-ai/src/maestra_ai/core/config.py:12`
- **Problema:** `_PLAYLIST_ID_RE = re.compile(r"[a-zA-Z0-9]{22}")` + `.search` — pega o primeiro run de 22 base62 em qualquer string. Entrada maliciosa `"spotify:playlist:abcdefghij1234567890AB-OR-whatever_garbage"` retorna `"abcdefghij1234567890AB"` sem reclamar se houver conteúdo adicional. Entrada `"abcdefghij1234567890AA abcdefghij1234567890BB"` retorna o primeiro.
- **Impacto:** confusão UX, não elevação de privilégio (Spotify API valida). Mas o usuário pode pensar que passou "playlist X" e acabou passando "playlist Y".
- **Fix sugerido:** tornar âncora com `^.*playlist/([a-zA-Z0-9]{22})` OU exigir que o match seja isolado (regex com word-boundary). Pode virar breaking change — avaliar.

---

## Validações que passaram

Confirmei manualmente (grep semântico + leitura) os seguintes pontos:

- **Redactor cobre todos os paths do CLI:** `cli/__init__.py:246-255` passa MaestraError por `redact_error_dict`; `cli/_common.py::error` e `safe_call` aplicam `redact_str`.
- **Writes de JSON em produção usam `atomic_write_json`:** `taste.py:130` (via `_write_atomic`), `snapshot.py:50`, `storage.py:89` (função), `context.py:22`, `playback.py:124`, `token_store.py:97`. Exceções inventariadas: `taste.py:127,146,163`, `snapshot.py:65`, `storage.py:72,83,109`, `audit.py:106` — todas são `open(lock_path, "w")` de arquivos de lock (vazios, com fcntl.flock) ou tmp intermediários ANTES de `os.replace`. Nenhum write de dados bypassa atomic.
- **JSONL appends usam `append_jsonl_locked`:** `director.py:196` e `feedback_prompt.py:69` (via `update_json_under_lock`). Única exceção: `playback.py:134` — veja S2.
- **24/24 tools MCP com jsonschema:** `tools.py:63-82` aplica `jsonschema.validate(args, td.schema)` universalmente antes de chamar `td.handler`. Conferido por contagem: `rg '@tool\(' packages/maestra-mcp/ | wc -l` = 24 (se incluir `onboard_rationale` recém-criado).
- **Path traversal em snapshot bloqueado:** `snapshot.py:97-103` combina regex canônica + `is_relative_to(snap_dir.resolve())` — defesa em profundidade correta.
- **subprocess sem `shell=True`:** `director.py:277` e `process.py:22,34` passam lista de args, nunca string de shell.
- **Sem `eval`/`exec`/import dinâmico com input:** `rg "eval\(|\bexec\(|__import__"` nos `src/` não retorna nada relevante (só imports de `sys.exec_info` etc.).
- **File mode 600 para token:** `token_store.py:97` via `atomic_write_json(..., mode=0o600)`. `storage.atomic_write_json` aplica chmod ao `.tmp` antes do `os.replace` (fix CRITICAL-3 v0.4.4) — sem janela TOCTOU.
- **Keyring backend check:** `token_store._keyring_backend_ok` filtra `fail`/`null` em `__module__`. `default_token_store()` usa essa versão (robusta).
- **Testes verdes:** `uv run pytest` em `packages/maestra-ai` → 507 passed em 6.67s. Ambiente testado com Python 3.12.
- **Dependências sem CVEs conhecidas agora:** `spotipy 2.26.0`, `mcp 1.27.0`, `jsonschema 4.26.0`, `keyring 25.7.0`, `cryptography 46.0.7`, `httpx 0.28.1`, `rich 15.0.0`. Todas dentro da faixa de suporte ativa em 2026-04; nenhuma CVE aberta identificada.

---

## Prioridades sugeridas para v0.7.0-alpha.1

1. **S1 (CRÍTICO)** — aplicar `redact_error_dict` no MCP boundary antes de retornar ao cliente. Inaceitável ficar assim em qualquer release publicada externamente.
2. **D12 + F401/UP037/F821** — `uv run ruff check --fix packages/` resolve ~22 dos 26 erros automáticos. Três precisam fix manual (N806, F841, UP037 no `onboard.py:574`).
3. **S2** — `PlaybackObserver` usar `append_jsonl_locked`.
4. **D1** — decidir: aplicar TypedDicts (aproveitar o investimento v0.7.0) OU remover os mortos + atualizar CHANGELOG. Não deixar como está.
5. **D2, D3, D4, D6, D14** — remoções triviais, batch num commit de limpeza.
6. **S3, S4, S9** — fix em commits individuais.
7. **D5, D7, D8, D10** — avaliar no próximo ciclo (v0.7.1+); não bloqueiam release.
8. **S5, S6, S8, S10** — hardening incremental; entrar no backlog consolidado.

## Escopos não cobertos por este review

- **Auditoria dependency-tree profunda:** rodei `uv pip list` e revisei versões; não rodei `pip-audit`/`safety`/osv-scanner.
- **Fuzzing de entrada MCP:** a cobertura dos TypedDicts + jsonschema é formalmente boa, mas não rodei property-based tests contra payloads malformados.
- **Análise de timing side channels em OAuth:** spotipy/refresh é caixa-preta; confio no upstream.
- **Revisão da configuração GH Actions** (se existir CI) — não examinado.

Todos os caminhos de arquivo listados neste relatório são absolutos ou relativos à raiz do repo (`/home/menzani/Desenvolvimento/maestra-ai`).
