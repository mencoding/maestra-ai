# Design — v0.6.1-alpha.0: consolidação de I/O + boundaries

**Data:** 2026-04-19
**Versão alvo:** v0.6.1-alpha.0
**Origem:** review pós-v0.6.0-alpha.0 (`docs/reviews/2026-04-19-v060-post-release.md`)
**Itens do review fechados:** I1, I2, I3, I4, I5, I6, I7 (todos os 7 Important)
**Escopo:** correções de correção/segurança + refactor de encapsulamento. Zero feature, zero breaking no CLI, zero breaking no output do MCP para clientes válidos.

---

## 1. Objetivo

Eliminar as 7 vulnerabilidades classe **Important** do review pós-release:

1. **Atomicidade** — `write_config`, `snapshot.create`, `director._record`, `audit.log` gravam sem lock/rename. Concorrência entre daemon director, CLI e MCP server pode corromper JSON/JSONL. (I1-I4)
2. **Boundary MCP** — `call_tool` aceita qualquer dict; schemas declarados em `inputSchema` não são validados. Agentes buggy ou hostis batem direto no spotipy com tipos errados. (I5)
3. **Parse frágil em feedback** — `datetime.fromisoformat` sem guard; state corrompido vira traceback cru. (I6)
4. **Encapsulamento curator↔taste** — 3 símbolos privados de `taste` usados por curator e CLI. Refactor silencioso risca quebra. (I7)

Sem novas features. Release de qualidade pura.

## 2. Contexto

### 2.1 Estado atual (v0.6.0-alpha.0, tag fechada)
- 462 testes maestra-ai + 35 MCP verdes.
- `atomic_write_json` existe em `storage.py` mas só `FileTokenStore` consome.
- `fcntl.flock` já aparece em `_force_rotate` de audit e `_rotate` de snapshot — padrão conhecido.
- MCP server em `call_tool` passa `args: dict[str, Any]` direto para `td.handler(args)`.
- Agentes externos conhecidos: zero. Ambiente single-user, local.

### 2.2 Razão do bundle
Sete itens pequenos, todos no vetor "proteger entrada/saída". Fix fragmentado em 4 releases perde consistência de mensagem no CHANGELOG e exige 4 rodadas de regressão. Um release focado na consolidação de boundaries ancora a narrativa: *v0.6.1 = hardening*.

### 2.3 Não-breaking
- Rename privado→público em taste (§3.5) não é breaking: pre-1.0, únicos consumidores são internos (`curator.py` + `cli/_common.py` + testes). Sem depr. alias.
- MCP validação rejeita args que eram aceitos mas explodiam dentro — efeito prático: mensagens de erro melhores. Não removemos nenhum arg válido existente.

---

## 3. Design

### 3.1 Helpers de I/O em `core/storage.py` (I1-I4)

Adicionar ao final do módulo, junto de `atomic_write_json`:

```python
import fcntl


def append_jsonl_locked(path: Path, entry: dict) -> None:
    """Append uma linha JSON com lock exclusivo via fcntl.flock.

    Serializa writes concorrentes de processos distintos (daemon
    director, CLI, MCP server). POSIX garante append atômico apenas
    até PIPE_BUF (~4KB); payloads reais ultrapassam esse limite,
    então o lock é necessário para evitar intercalação.

    Em caso de crash mid-write, perde-se no máximo a linha corrente
    (jamais corrompe linhas anteriores).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(entry, ensure_ascii=False) + "\n"
    with open(path, "a", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            f.write(line)
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
```

**Migrações:**

| Item | Arquivo | Linha aprox. | De | Para |
|---|---|---|---|---|
| I1 | `core/storage.py:143-146` | `write_config` | `p.write_text(json.dumps(...))` | `atomic_write_json(p, data)` |
| I2 | `core/director.py:189-198` | `_record` | `open(log_path, "a") + f.write(line)` | `append_jsonl_locked(log_path, entry)` |
| I3 | `core/audit.py:49-52` | `log` | `open(audit_path, "a") + f.write(line)` | `append_jsonl_locked(audit_path, entry)` |
| I4 | `core/snapshot.py:50` | `create` | `path.write_text(json.dumps(...))` | `atomic_write_json(path, payload)` |

Observações:
- **Rotação por tamanho** em audit (linha ~63-70) é separada da escrita; continua com seu próprio lock em `_force_rotate`. Apenas a linha de `log()` muda.
- **Ordem em audit**: a verificação `_needs_rotate` acontece *depois* da escrita hoje; mantemos essa ordem — rotação adiada por 1 entry é aceitável.
- `atomic_write_json` já faz `os.replace` (rename atômico POSIX) + cleanup do tmp. Confirma-se em `storage.py:93-115`.

### 3.2 Validação MCP (I5)

**Dep:** `jsonschema>=4.0,<5.0` em `packages/maestra-mcp/pyproject.toml`.

**Server:** em `server.py:call_tool`, antes de `await td.handler(args)`:

```python
import jsonschema
from maestra_ai.core.errors import UserError

try:
    jsonschema.validate(args, td.schema)
except jsonschema.ValidationError as e:
    raise UserError(
        code="MCP_INVALID_ARGS",
        message=f"{name}: {e.message}",
        agent_hint=_format_schema_hint(e),
    )
```

**`UserError`** em `core/errors.py`:

```python
class UserError(MaestraError):
    """Erro de entrada inválida no boundary (MCP args, CLI flags).

    Distinto de ValidationError (que vem de validação de schemas de
    storage). UserError indica que o consumidor (agente, humano)
    mandou algo que nunca deveria ter sido aceito.
    """
    pass
```

**`_format_schema_hint`** em `server.py`:

```python
def _format_schema_hint(err: jsonschema.ValidationError) -> str:
    """Converte ValidationError em dica curta para o agente."""
    path = ".".join(str(p) for p in err.absolute_path) or "<root>"
    validator = err.validator
    value = err.validator_value
    if validator == "minimum":
        return f"campo `{path}` deve ser >= {value}"
    if validator == "maximum":
        return f"campo `{path}` deve ser <= {value}"
    if validator == "required":
        return f"campo obrigatório ausente: {value}"
    if validator == "additionalProperties":
        return f"campo desconhecido em `{path}` (use apenas os documentados)"
    if validator == "type":
        return f"campo `{path}` deve ser {value}"
    if validator == "enum":
        return f"campo `{path}` deve ser um de: {value}"
    return f"validação falhou em `{path}` ({validator})"
```

**Tradução pelo wrapper existente:** o server já converte `MaestraError` em `CallToolResult(isError=True, content=[...])` com redaction. `UserError` herda de `MaestraError`, então o pipeline existente absorve sem mudança. Se a implementação atual só catch classes específicas (e.g., `NetworkError`, `AuthError`), o plan vai ajustar para também pegar `UserError` — verificado na Task de implementação do I5.

### 3.3 Guard em `FeedbackPrompter._in_cooldown` (I6)

Em `core/feedback_prompt.py:89-92`:

```python
def _in_cooldown(self, entry: dict) -> bool:
    if "last_prompt_at" not in entry:
        return False
    try:
        last = datetime.fromisoformat(entry["last_prompt_at"])
    except (ValueError, TypeError):
        return False  # state corrompido → cooldown expirou
    return (datetime.now(UTC) - last) < self._cooldown
```

Idêntico ao padrão de `core/context.py:44`.

### 3.4 Rename privado → público em `taste.py` (I7)

Sem deprecation alias (pre-1.0). Três renames:

```python
# taste.py
def is_rejected(self, uri: str) -> bool:  # era _is_rejected
    ...

def prune_candidates(  # era _prune_candidates (module-level)
    candidates: list[dict], taste: TasteProfile
) -> list[dict]:
    ...

def signal_weight(signal: str) -> float:  # era _signal_weight
    ...
```

**Docstrings** explicitam "API pública consumida por curator".

**Call sites atualizados:**
- `curator.py:76` — `taste._is_rejected(...)` → `taste.is_rejected(...)`
- `cli/_common.py:126` — `taste_mod._prune_candidates(...)` → `taste_mod.prune_candidates(...)`
- `cli/_common.py:159` — `taste_mod._signal_weight(...)` → `taste_mod.signal_weight(...)`
- Testes que acessam esses símbolos: renomeia.

**Verificação final:** `grep -rn "_is_rejected\|_prune_candidates\|_signal_weight" packages/` retorna zero (exceto linha da release note do CHANGELOG).

### 3.5 Escopo explícito do rename

Símbolos que **ficam privados** (não promovidos):
- `_redact` em audit — uso puramente interno.
- `_SECRET_KEYS` — lista de config.
- `_SERVICE`, `_USER` em token_store — constantes locais.
- `_bucket`, `_breaker` em client — singletons mutáveis (ver M4, out-of-scope).

O critério: público é o que já é consumido por outro módulo, não o que "poderia ser útil".

---

## 4. Arquivos afetados

| Arquivo | Tipo | Mudança |
|---|---|---|
| `packages/maestra-ai/src/maestra_ai/core/storage.py` | Modify | +append_jsonl_locked; write_config atômico |
| `packages/maestra-ai/src/maestra_ai/core/snapshot.py` | Modify | create usa atomic_write_json |
| `packages/maestra-ai/src/maestra_ai/core/audit.py` | Modify | log() usa append_jsonl_locked |
| `packages/maestra-ai/src/maestra_ai/core/director.py` | Modify | _record usa append_jsonl_locked |
| `packages/maestra-ai/src/maestra_ai/core/feedback_prompt.py` | Modify | guard fromisoformat |
| `packages/maestra-ai/src/maestra_ai/core/taste.py` | Modify | rename 3 símbolos + docstring público |
| `packages/maestra-ai/src/maestra_ai/core/curator.py` | Modify | 1 call site |
| `packages/maestra-ai/src/maestra_ai/cli/_common.py` | Modify | 2 call sites |
| `packages/maestra-ai/src/maestra_ai/core/errors.py` | Modify | +UserError |
| `packages/maestra-mcp/src/maestra_mcp/server.py` | Modify | jsonschema.validate + _format_schema_hint |
| `packages/maestra-mcp/pyproject.toml` | Modify | +jsonschema dep; bump 0.6.1a0 + pin maestra-ai |
| `packages/maestra-ai/pyproject.toml` | Modify | bump 0.6.1a0 |
| `CHANGELOG.md` | Add | seção [0.6.1-alpha.0] |
| `docs/reviews/2026-04-19-v060-post-release.md` | Touch | marcar I1-I7 como fechados |
| `packages/maestra-ai/tests/unit/test_storage.py` | Modify/Add | TestAppendJsonlLocked |
| `packages/maestra-ai/tests/unit/test_snapshot.py` | Add | test_create_atomico_em_caso_de_crash |
| `packages/maestra-ai/tests/unit/test_feedback_prompt.py` | Add | test_cooldown_tolera_fromisoformat_invalido |
| `packages/maestra-mcp/tests/test_server.py` (ou novo) | Add | TestValidacaoArgs (4 casos) |
| Testes que importam `_is_rejected`/`_prune_candidates`/`_signal_weight` | Modify | rename |

---

## 5. Testes (TDD)

### 5.1 Novos

**`TestAppendJsonlLocked` em `test_storage.py`:**
- `test_serializa_entry_com_acento` — append de `{"user": "João"}`, relê, confere `ensure_ascii=False`.
- `test_concorrencia_nao_intercala` — 2 threads apendam 50 entries cada; lê de volta; 100 linhas, todas JSON-parseáveis, sem bytes intercalados. Usa `threading.Thread` simples; se flaky em CI, marca como `@pytest.mark.flaky(reruns=2)`.

**`test_create_atomico_em_caso_de_crash_simulado` em `test_snapshot.py`:**
- Patch `os.replace` para levantar `RuntimeError("simulated crash")`. `atomic_write_json` faz write no `.tmp` e tenta rename.
- Chama `snapshot.create(...)`; confere que: (a) `path.exists()` é False (não parcial); (b) nenhum arquivo `.tmp` residual no diretório (helper faz cleanup via `try/finally`).

**`test_cooldown_tolera_fromisoformat_invalido` em `test_feedback_prompt.py`:**
- State com `{"last_prompt_at": "banana"}` → `_in_cooldown` retorna `False`, sem raise.
- State com `{"last_prompt_at": None}` → mesmo.
- State sem a chave → mesmo (já era comportamento anterior, mantém).

**`TestValidacaoArgs` em `tests/test_server.py` (maestra-mcp):**
- `test_additional_properties_rejeita_campo_desconhecido` — chamar `queue({"track_uri": "...", "extra": "x"})` → `UserError` com code `MCP_INVALID_ARGS`.
- `test_minimum_rejeita_valor_fora` — `director_start({"interval": 5})` (mínimo é 15) → `UserError`.
- `test_required_rejeita_ausencia` — `search({})` (query required) → `UserError`.
- `test_args_validos_passam` — call sanity ok com args válidos, não levanta.

### 5.2 Atualizados

- Testes em `test_taste.py` que chamam `_is_rejected` etc. — rename.
- `test_curator.py` — confere chamada para `is_rejected` (público agora).
- Testes de audit/director: **opcionalmente** adicionar caso de concorrência com threads; não-crítico. Se custo alto, deixa em Minor para depois.

### 5.3 Regressão

Suite inteira + MCP roda:
- maestra-ai: 462 → ~465 (+3 ou 4 novos).
- maestra-mcp: 35 → ~39 (+4 validação).

---

## 6. Critérios de aceite

1. `write_config`, `snapshot.create`, `director._record`, `audit.log` usam helpers com lock/rename. `grep` não encontra mais `write_text(json.dumps` em caminho de escrita de estado.
2. `grep -rn "_is_rejected\|_prune_candidates\|_signal_weight" packages/` retorna apenas a linha do CHANGELOG.
3. MCP com `jsonschema.validate` em call_tool. 4 testes de validação passam.
4. `UserError` definido em `errors.py` e herda de `MaestraError`.
5. `_in_cooldown` não crasha com state corrompido.
6. Suite: ~465 + ~39 = ~504 passed. Zero falhas.
7. `pyproject.toml` (ambos) bumped para `0.6.1a0`; dep `maestra-ai==0.6.1a0` no mcp.
8. Backlog review pós-v060 marca I1-I7 fechados.

---

## 7. Não-objetivos

- Não atacar Minors M1-M8 nem Nits N1-N5 — ficam para v0.6.2+.
- Não refatorar audit rotation (já tem lock próprio, só a escrita entra).
- Não evoluir circuit breaker / rate limiter.
- Não criar módulo novo `core/_io.py` (consolidação em storage foi decidida).
- Não adicionar deprecation alias para os símbolos renomeados em taste — hard break controlado.
- `M1`/`M2` (onboard silenciando AuthError/Rate) NÃO entram — são Minor e exigem design próprio sobre o que é "silenciável".
- Não expor validação MCP ao CLI — CLI já valida via argparse + normalizadores.

---

## 8. Riscos e mitigações

| Risco | Prob. | Mitigação |
|---|---|---|
| Teste de concorrência flaky em CI | Média | `pytest.mark.flaky` + threads dentro do mesmo processo, sem sleep. Se inviável, pula. |
| `jsonschema` adiciona 200KB ao MCP | Baixa | Aceitável; é dep comum, zero preocupação. |
| Rename quebra import de usuário externo | Baixíssima | Zero agentes externos conhecidos (ver contexto). Pré-1.0. |
| `atomic_write_json` em snapshot cria arquivo `.tmp` residual em crash | Baixa | O helper já faz cleanup via `try/finally`. Confirmar em teste. |
| `UserError` redaction no MCP vaza info sensível no `agent_hint` | Baixa | Hints usam só nome do campo, nunca valor. Verificado em teste. |

---

## 9. Referências

- Review original: `docs/reviews/2026-04-19-v060-post-release.md`.
- Releases anteriores: v0.5.2 a v0.6.0-alpha.0 (ver CHANGELOG).
- Padrão existente de lock: `core/audit.py:_force_rotate`, `core/snapshot.py:_rotate`.
- Padrão existente de atomic: `core/storage.py:atomic_write_json`.
- Boundary MCP: `packages/maestra-mcp/src/maestra_mcp/server.py:call_tool`, `tools.py`.
