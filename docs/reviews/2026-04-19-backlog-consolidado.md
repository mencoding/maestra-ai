# Backlog consolidado — estado em v0.5.7

**Data:** 2026-04-19
**Versão de referência:** v0.5.7 (itens 1-26 fechados — exceto #12 descartado)
**Fontes:** `2026-04-17-fases-1-2.md`, `2026-04-17-pos-v023.md`, review inline da v0.5.3 (code-reviewer), varredura estática de v0.5.4.

Este documento é a **fonte autoritativa** do backlog técnico aberto. Os dois
reviews anteriores permanecem no repo como histórico, mas seus achados já
resolvidos (P0-1, P0-2, P0-4, P0-R1, P0-N1, P0-N2, P0-N3, P0-3, P0-5 em
módulos principais, P2-1, P2-4, PLAN-v050, PLAN-v040) não aparecem aqui.

**Total aberto:** 29 itens — ordenados por severidade e ROI de implementação.

---

## Severidade ALTA — contrato quebrado, performance ou consistência (5 itens)

### 1. `ensure_active_device` levanta `RuntimeError` em vez de `MaestraError`
- **Arquivo:** `packages/maestra-ai/src/maestra_ai/core/client.py:163,169,188`
- **Impacto:** Quebra o contrato da hierarquia de erros (sem `probable_causes`, `suggested_actions`, `agent_hint`). Callers usam `except RuntimeError` e perdem a UX padronizada.
- **Fix:** Criar `DeviceError(MaestraError)` em `core/errors.py` com causas e ações sugeridas (abrir Spotify, aguardar, ativar dispositivo).
- **Origem:** P1-6 do review de Fases 1-2.

### 2. `safe_call` não passa erro pelo redator
- **Arquivo:** `packages/maestra-ai/src/maestra_ai/cli/_common.py:73-78`
- **Impacto:** `{"error": str(e), "code": X}` sem `redact_str()`. Usado em `basic.py:170,176` no `cmd_status`. Se exceção contém `Bearer <token>` ou `access_token=...`, vaza no JSON de saída.
- **Fix:** Envolver com `redact_str()` como já faz `error()` em `_common.py:60-70`.
- **Origem:** Varredura v0.5.4 (não capturada nos reviews anteriores).

### 3. `sp.playlist_items` sem `fields` restrito — payload 3-5× maior
- **Arquivo:** `packages/maestra-ai/src/maestra_ai/core/onboard.py:_fetch_playlist_tracks`
- **Impacto:** Em bibliotecas grandes ou playlists pesadas, cada request carrega álbum, imagens, `available_markets` com ~180 países. Performance degrada onboard + rate limit mais caro.
- **Fix:** Passar `fields="items(track(uri,name,artists(name))),next"`.
- **Origem:** A1 do review da v0.5.3.

### 4. Filtro de playlists vazias só no CLI, não no core
- **Arquivo:** `packages/maestra-ai/src/maestra_ai/cli/onboard.py:72` (filtra `track_count > 0`)
- **Impacto:** Contrato do `playlist_selector` não garante filtro. Selectors fornecidos por MCP, scripts ou testes podem passar IDs de playlists vazias para `_fetch_playlist_tracks` — desperdício de request.
- **Fix:** Mover filtro para `_fetch_own_playlists` no core; CLI não precisa duplicar.
- **Origem:** A5 do review da v0.5.3.

### 5. `TasteProfile.restore` sem cleanup de `.tmp` em falha
- **Arquivo:** `packages/maestra-ai/src/maestra_ai/core/taste.py:125-129,142-146`
- **Impacto:** Se `os.replace()` falha (disco cheio, permissão), `.tmp` fica órfão e `self.data` em memória diverge do disco. Próxima `save()` pode quebrar.
- **Fix:** `try/except` envolvendo o bloco, com `os.unlink(tmp_path)` no except e re-raise como `StorageError`.
- **Origem:** P1-4 do review de Fases 1-2.

---

## Severidade MÉDIA — qualidade, observabilidade, UX (9 itens)

### 6. Race (playlist deletada entre listagem e fetch) silenciada
- **Arquivo:** `packages/maestra-ai/src/maestra_ai/core/onboard.py:396-404` (bloco `except Exception: continue`)
- **Impacto:** Se usuário deleta/renomeia playlist entre `_fetch_own_playlists` e `_fetch_playlist_tracks`, o fetch falha silenciosamente e o relatório diz "tracks_added" sem indicar que `p2` falhou.
- **Fix:** Popular `expansion_info["failed_playlists"] = [{"id", "reason"}]` para rastreabilidade.
- **Origem:** A2 do review da v0.5.3.

### 7. Falha parcial do fetch de uma playlist não é reportada
- **Arquivo:** Mesmo bloco do #6.
- **Impacto:** Timeout na request 3 de 5 da p2 descarta as 200 tracks já coletadas e segue para p3 sem log. Linked com #6.
- **Fix:** Mesma solução — `failed_playlists` com motivo e fase (e.g. `"partial_fetch"`).
- **Origem:** A3 do review da v0.5.3.

### 8. `--expand-playlists` não valida formato dos IDs
- **Arquivo:** `packages/maestra-ai/src/maestra_ai/cli/onboard.py:56-63` (split + strip apenas)
- **Impacto:** Usuário cola URL completa ou nome → `_fetch_playlist_tracks` falha com exceção genérica que o `except Exception: continue` esconde.
- **Fix:** Usar `normalize_playlist_id` (já existe em `core/config.py`) em cada item; levantar `UserError` se inválido.
- **Origem:** M5 do review da v0.5.3.

### 9. Mensagem "5000 faixas" hard-coded ignora `--total-cap`
- **Arquivo:** `packages/maestra-ai/src/maestra_ai/cli/onboard.py:97` (string em `_prompt_expansion_confirm`)
- **Impacto:** Se `--total-cap=1000`, o prompt mente dizendo "menor que 5000".
- **Fix:** Passar `total_cap` e `current_total` ao prompt; formatar dinamicamente.
- **Origem:** M2 do review da v0.5.3.

### 10. `reason=None` no caminho feliz do `expansion_info`
- **Arquivo:** `packages/maestra-ai/src/maestra_ai/core/onboard.py:355-415`
- **Impacto:** Campo inconsistente — em falha tem valor, em sucesso fica `None`. Consumidores de `--json` podem tropeçar no `if reason:`.
- **Fix:** Padronizar — ou sempre tem valor (`"ok"` no sucesso) ou só existe no caso de não ter havido expansão.
- **Origem:** M1 do review da v0.5.3.

### 11. `_rotate()` de snapshot sem lock
- **Arquivo:** `packages/maestra-ai/src/maestra_ai/core/snapshot.py:55`
- **Impacto:** Dois processos chamando `_rotate` concorrentemente podem duplicar ou perder arquivos no archive. Daemon director + CLI manual é cenário real.
- **Fix:** `FileLock` em `<snapshots_dir>/.rotate.lock` envolvendo o bloco `glob + move`.
- **Origem:** P1-3 do review de Fases 1-2.

### 12. `datetime.fromisoformat` sem proteção em `context.show`
- **Arquivo:** `packages/maestra-ai/src/maestra_ai/core/context.py:44`
- **Impacto:** Se usuário edita `current_context.json` manualmente com data inválida, `ValueError` cru ao rodar `maestra context show`.
- **Fix:** `try/except ValueError` traduzindo para `StorageError` com sugestão de apagar o arquivo.
- **Origem:** P2-3 do review de Fases 1-2.

### 13. `BASE_DIR` avaliado em import time com `os.makedirs`
- **Arquivo:** `packages/maestra-ai/src/maestra_ai/cli/_common.py:11-12`
- **Impacto:** Side-effect no import dificulta testes que precisam de `monkeypatch` do env antes do import. Fragilidade silenciosa.
- **Fix:** Lazy-load em funções que precisam do path; remover `makedirs` do topo do módulo.
- **Origem:** P2-2 do review de Fases 1-2.

### 14. Teste da redação em `--json` é tautológico
- **Arquivo:** `packages/maestra-ai/tests/unit/test_cli_main.py:9-37`
- **Impacto:** Testa que `_redact()` funciona, não que é chamado nos caminhos de erro reais. Cobertura falsa.
- **Fix:** Adicionar teste que força `error()` com mock de `SpotifyException` contendo `Bearer <token>` e valida redação no stdout real.
- **Origem:** P1-7 do review de Fases 1-2.

---

## Severidade BAIXA — polimento, documentação (9 itens)

### 15. Semântica de URI em N playlists do usuário não documentada
- **Arquivo:** Docstring de `run()` em `onboard.py`
- **Impacto:** Peso "playlist=2" soma uma vez mesmo se URI aparece em p1, p2 e p3 (dedup via `seen`). Usuário não sabe se são 2 ou 6.
- **Fix:** Documentar explicitamente: "peso 2 aplicado uma única vez por URI, independente de quantas playlists a contêm".
- **Origem:** A4 do review da v0.5.3.

### 16. Fallback texto para >30 playlists sem paginação
- **Arquivo:** `packages/maestra-ai/src/maestra_ai/cli/onboard.py:122-134` (`_prompt_playlists_checkbox`)
- **Impacto:** Quando `questionary` falha em runtime, imprime a lista inteira de 100+ playlists. UX degradada.
- **Fix:** Limitar a top-N por `track_count` ou documentar como degradação aceitável com nota clara.
- **Origem:** M3 do review da v0.5.3.

### 17. "Nenhuma playlist" quando todas estão vazias é enganoso
- **Arquivo:** `packages/maestra-ai/src/maestra_ai/cli/onboard.py:72-75`
- **Impacto:** Usuário que tem 10 playlists vazias recebe mensagem "Você ainda não criou nenhuma playlist" — falso.
- **Fix:** Distinguir "zero playlists próprias" de "zero com faixas"; mensagem específica para o segundo caso.
- **Origem:** M4 do review da v0.5.3.

### 18. Acoplamento implícito entre `_prompt_expansion_confirm` e `progress`
- **Arquivo:** `packages/maestra-ai/src/maestra_ai/cli/onboard.py:91-102`
- **Impacto:** `_prompt_expansion_confirm` assume que alguém acima parou o `progress`. Se chamado de outro lugar, pode sobrepor output.
- **Fix:** Docstring deixando explícito que o caller é responsável por pausar progress, OU mover stop/start para dentro do prompt.
- **Origem:** M6 do review da v0.5.3.

### 19. `selected_playlists` guarda IDs, não nomes
- **Arquivo:** `packages/maestra-ai/src/maestra_ai/core/onboard.py` (report)
- **Impacto:** Relatório human mostra "+N faixas de K playlist(s)" sem dizer quais. Agente recebe IDs nus no JSON.
- **Fix:** Trocar tipo do campo para `list[dict(id, name)]`.
- **Origem:** B1 do review da v0.5.3.

### 20. `_fetch_own_playlists` sem progress callback
- **Arquivo:** `packages/maestra-ai/src/maestra_ai/core/onboard.py:_fetch_own_playlists`
- **Impacto:** Usuário com 500 playlists vê 10s sem feedback visual durante a listagem.
- **Fix:** Aceitar `progress_cb` como `_fetch_saved` faz; emitir `{"step": 6, "detail": f"{n}/N playlists listadas"}`.
- **Origem:** B2 do review da v0.5.3.

### 21. Docstring de `run()` ambígua sobre condições de expansão
- **Arquivo:** Docstring de `run()` em `onboard.py`
- **Impacto:** Diz "se `playlist_selector` estiver definido", mas a condição real é `selector is not None AND total_unique < total_cap`. Caso `selector_provided_but_cap_already_reached` não é distinguível de `selector=None` via `expansion_info`.
- **Fix:** Alinhar docstring ao código + adicionar `reason="cap_already_reached"` quando aplicável.
- **Origem:** B4 do review da v0.5.3.

### 22. Três env vars independentes sem documentação unificada
- **Arquivo:** Docs (README troubleshooting, `core/storage.py`)
- **Impacto:** `MAESTRA_CONFIG_DIR`, `MAESTRA_DATA_DIR`, `MAESTRA_STATE_DIR` podem apontar para lugares diferentes. Usuário deleta um "pra limpar tudo" e perde só parte.
- **Fix:** Documentar no README ou consolidar em `MAESTRA_HOME` com subdirs fixos.
- **Origem:** P1-2 do review de Fases 1-2.

### 23. `_rotate` do audit sem lock (complemento do #11)
- **Arquivo:** `packages/maestra-ai/src/maestra_ai/core/audit.py:_maybe_rotate`
- **Impacto:** Mesmo padrão de race que snapshot; dois processos podem duplicar/perder linha durante rotação.
- **Fix:** Mesma solução do #11 — `FileLock` em `<dir>/.rotate.lock`.
- **Origem:** P1-3 do review de Fases 1-2.

---

## Testes faltando (3 itens)

### 24. Cobertura real do fluxo interativo do selector
- **Arquivo:** `packages/maestra-ai/tests/unit/test_cli_onboard.py:TestPlaylistSelector`
- **Gap:** `test_tty_retorna_callback` só valida que é callable. Não testa `questionary.confirm` nem `questionary.checkbox` com mocks reais — pode mascarar regressões na integração.
- **Fix:** Adicionar mocks em cima do módulo `questionary` (e.g. via `monkeypatch.setattr("questionary.confirm", ...)`).
- **Origem:** B6 do review da v0.5.3.

### 25. Edge cases de `--expand-playlists`
- **Arquivo:** `test_cli_onboard.py`
- **Gap:** IDs inválidos, IDs que não pertencem ao usuário, IDs que não existem — nada testado. Selector levantando exceção também não.
- **Fix:** Classe `TestExpandPlaylistsEdgeCases` cobrindo os 4+ cenários.
- **Origem:** B7 do review da v0.5.3.

### 26. Testes E2E de CLI
- **Gap:** Zero testes E2E. `maestra rollback`, `maestra snapshot create`, `maestra doctor`, `maestra onboard` nunca exercitados com filesystem real via subprocess.
- **Fix:** Criar `packages/maestra-ai/tests/integration/` com `subprocess.run(["uv", "run", "maestra", ...])` + `tmp_path` como `MAESTRA_DATA_DIR`.
- **Origem:** P1-5 do review de Fases 1-2.

---

## Evolução de design (3 itens — não são bugs)

### 27. Contrato do `playlist_selector` precisa de `ExpansionContext`
- **Impacto:** Hoje o selector recebe só `list[dict(id, name, track_count)]`. Não sabe `total_cap` nem `current_total`. Selectors programáticos (MCP, heurísticos) precisam descobrir fora-de-banda.
- **Fix:** Evoluir para `Callable[[list[dict], ExpansionContext], list[str]]` com `ExpansionContext = {total_cap, current_total, remaining}`.
- **Origem:** Review da v0.5.3, seção de design.

### 28. `reason="user_skipped"` mistura semântica CLI/core
- **Impacto:** Core não deveria saber "user". Se selector é um agente IA, o valor está errado.
- **Fix:** Core usa `reason="selector_returned_empty"`; CLI traduz para humano no momento de imprimir.
- **Origem:** Review da v0.5.3, seção de design.

### 29. `expansion_info` mistura intent com outcome
- **Impacto:** `attempted`, `offered_playlists`, `reason`, `tracks_added` em um dict plano. Difícil compor.
- **Fix:** Refatorar em `{attempted, skipped_because, outcome: {tracks_added, selected, failed}}` — se #27 e #28 forem implementados juntos.
- **Origem:** Review da v0.5.3, seção de design.

---

## Fora do escopo v0.5.x

- **`_derive_suggestions` fixo em artist-dominance** (B3 do review v0.5.3). Com a expansão trazendo amostra maior, vale revisitar com gêneros/mood/décadas da API Spotify. Entra em v0.6.x via brainstorming de "sugestões de contexto inteligentes".

---

## Ordem de execução — status

**v0.5.5 ✅ (2026-04-19):** itens 1-9 fechados (altos + médios de alto ROI).
**v0.5.6 ✅ (2026-04-19):** itens 10, 11, 13, 14, 24, 25, 26 + #23 (junto com #11). Item 12 descartado como falso positivo.
**v0.5.7 ✅ (2026-04-19):** itens 15, 16, 17, 18, 19, 20, 21, 22 fechados.
**v0.6.0-alpha.0 ✅ (2026-04-19):** itens 27 e 29 fechados. Item 28 já tinha sido fechado em v0.5.6 (rename de reason vocabulário).
**v0.7.0-alpha.0 ✅ (2026-04-20):** B3 fechado — sugestões inteligentes com gêneros/décadas/taste + rationale persistido + MCP tool.

Itens fechados: 29 de 29 (+ 1 descartado).

**v0.5.x está substancialmente concluída** — só faltam os 3 itens de design que justificam mini-spec próprio (quebra de contrato do selector) e a melhoria das sugestões que pede brainstorming de UX (gêneros, décadas, mood).
