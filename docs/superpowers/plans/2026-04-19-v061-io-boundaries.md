# v0.6.1-alpha.0 I/O Boundaries Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fechar os 7 itens Important do review pós-v0.6.0-alpha.0 (atomicidade de writes em 4 sítios, validação MCP via jsonschema, guard em `_in_cooldown`, rename privado→público em taste).

**Architecture:** Consolidar helpers de I/O em `core/storage.py` (`append_jsonl_locked` + `atomic_write_json` já existente). Migrar `write_config`, `snapshot.create`, `director._record`, `audit.log` para usar os helpers. Validação MCP via `jsonschema` dep nova em `maestra-mcp`, traduzindo `ValidationError` para `MCPInvalidArgsError(UserError)`. Rename direto em `taste.py` (pre-1.0, sem deprecation).

**Tech Stack:** Python 3.11+, `fcntl.flock` (já usado), `json`, `jsonschema>=4.0`. pytest com `threading.Thread` para testes de concorrência.

**Spec:** `docs/superpowers/specs/2026-04-19-v061-io-boundaries-design.md`.

**Base antes de começar:** tag `v0.6.0-alpha.0` + `ecc42c6` (review doc). Suite 462 maestra-ai + 35 mcp.

---

## File Structure

| Arquivo | Tipo | Responsabilidade na v0.6.1 |
|---|---|---|
| `packages/maestra-ai/src/maestra_ai/core/storage.py` | Modify | +`append_jsonl_locked`; `write_config` usa `atomic_write_json` |
| `packages/maestra-ai/src/maestra_ai/core/snapshot.py` | Modify | `create` usa `atomic_write_json` |
| `packages/maestra-ai/src/maestra_ai/core/audit.py` | Modify | `log` usa `append_jsonl_locked` |
| `packages/maestra-ai/src/maestra_ai/core/director.py` | Modify | `_record` usa `append_jsonl_locked` |
| `packages/maestra-ai/src/maestra_ai/core/feedback_prompt.py` | Modify | `_in_cooldown` guarda fromisoformat |
| `packages/maestra-ai/src/maestra_ai/core/errors.py` | Modify | +`MCPInvalidArgsError(UserError)` |
| `packages/maestra-ai/src/maestra_ai/core/taste.py` | Modify | Rename `_is_rejected/_prune_candidates/_signal_weight` |
| `packages/maestra-ai/src/maestra_ai/core/curator.py` | Modify | Atualiza uso de `is_rejected` |
| `packages/maestra-ai/src/maestra_ai/cli/_common.py` | Modify | Atualiza uso de `prune_candidates/signal_weight` |
| `packages/maestra-mcp/src/maestra_mcp/tools.py` | Modify | `call_tool` valida args antes de chamar handler |
| `packages/maestra-mcp/pyproject.toml` | Modify | +`jsonschema>=4.0,<5`; bump 0.6.1a0 |
| `packages/maestra-ai/pyproject.toml` | Modify | bump 0.6.1a0 |
| `CHANGELOG.md` | Add | Seção [0.6.1-alpha.0] |
| `docs/reviews/2026-04-19-v060-post-release.md` | Touch | marcar I1-I7 como fechados |
| `packages/maestra-ai/tests/unit/test_storage.py` | Modify/Add | `TestAppendJsonlLocked` |
| `packages/maestra-ai/tests/unit/test_snapshot.py` | Modify/Add | `test_create_atomico_em_caso_de_crash_simulado` |
| `packages/maestra-ai/tests/unit/test_feedback_prompt.py` | Modify/Add | `test_cooldown_tolera_fromisoformat_invalido` |
| `packages/maestra-mcp/tests/test_server_validation.py` | Create | `TestValidacaoArgs` (4 casos) |
| Testes que importam `_is_rejected/_prune_candidates/_signal_weight` | Modify | rename |

---

## Task 1: `append_jsonl_locked` em `core/storage.py` (TDD)

**Files:**
- Modify: `packages/maestra-ai/src/maestra_ai/core/storage.py`
- Modify: `packages/maestra-ai/tests/unit/test_storage.py`

- [ ] **Step 1: Escrever o teste de serialização**

Abrir `packages/maestra-ai/tests/unit/test_storage.py`. Achar uma classe existente de teste de storage (ex: `TestAtomicWrite` ou `TestUpdateJsonUnderLock`) e adicionar uma nova classe no mesmo nível:

```python
class TestAppendJsonlLocked:
    def test_serializa_entry_com_acento(self, tmp_path):
        from maestra_ai.core.storage import append_jsonl_locked
        path = tmp_path / "log.jsonl"
        append_jsonl_locked(path, {"user": "João", "city": "São Paulo"})
        lines = path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed == {"user": "João", "city": "São Paulo"}
```

Verificar que `json` já está importado no topo do arquivo de teste. Se não, adicionar `import json`.

- [ ] **Step 2: Rodar o teste e confirmar falha**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai/packages/maestra-ai && uv run pytest tests/unit/test_storage.py::TestAppendJsonlLocked::test_serializa_entry_com_acento -v 2>&1 | tail -6`
Expected: `FAILED ... ImportError: cannot import name 'append_jsonl_locked' from 'maestra_ai.core.storage'`.

- [ ] **Step 3: Implementar `append_jsonl_locked`**

Em `packages/maestra-ai/src/maestra_ai/core/storage.py`, adicionar (depois de `atomic_write_json`, antes de `read_config`):

```python
def append_jsonl_locked(path: str | os.PathLike, entry: dict) -> None:
    """Append uma linha JSON com lock exclusivo via fcntl.flock.

    Serializa writes concorrentes de processos distintos (daemon
    director, CLI, MCP server). POSIX garante append atômico apenas
    até PIPE_BUF (~4KB); payloads reais ultrapassam esse limite,
    então o lock é necessário para evitar intercalação.

    Em caso de crash mid-write, perde-se no máximo a linha corrente
    (jamais corrompe linhas anteriores).
    """
    path = os.fspath(path)
    parent = os.path.dirname(path) or "."
    os.makedirs(parent, exist_ok=True)
    line = json.dumps(entry, ensure_ascii=False) + "\n"
    with open(path, "a", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            f.write(line)
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
```

- [ ] **Step 4: Rodar teste e confirmar PASS**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai/packages/maestra-ai && uv run pytest tests/unit/test_storage.py::TestAppendJsonlLocked::test_serializa_entry_com_acento -v 2>&1 | tail -3`
Expected: `1 passed`.

- [ ] **Step 5: Escrever o teste de concorrência**

Adicionar no mesmo `TestAppendJsonlLocked`:

```python
    def test_concorrencia_nao_intercala_bytes(self, tmp_path):
        import threading
        from maestra_ai.core.storage import append_jsonl_locked
        path = tmp_path / "log.jsonl"

        def writer(tid: int):
            for i in range(50):
                append_jsonl_locked(path, {"thread": tid, "i": i, "pad": "x" * 500})

        threads = [threading.Thread(target=writer, args=(t,)) for t in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        lines = path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 100
        # Todas as linhas devem ser JSON válido — prova ausência de intercalação.
        for line in lines:
            parsed = json.loads(line)
            assert set(parsed.keys()) == {"thread", "i", "pad"}
```

- [ ] **Step 6: Rodar e confirmar PASS**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai/packages/maestra-ai && uv run pytest tests/unit/test_storage.py::TestAppendJsonlLocked -v 2>&1 | tail -5`
Expected: `2 passed`.

- [ ] **Step 7: Commit**

```bash
cd /home/menzani/Desenvolvimento/maestra-ai
git add packages/maestra-ai/src/maestra_ai/core/storage.py packages/maestra-ai/tests/unit/test_storage.py
git commit -m "feat(storage): append_jsonl_locked helper (v0.6.1)

Serializa appends JSONL concorrentes com fcntl.LOCK_EX para
evitar intercalação entre daemon director, CLI e MCP server.
Dois testes: serialização ensure_ascii=False e concorrência
com 2 threads × 50 entries cada."
```

---

## Task 2: `storage.write_config` atômico (I1)

**Files:**
- Modify: `packages/maestra-ai/src/maestra_ai/core/storage.py:143-146`

- [ ] **Step 1: Substituir a implementação**

Achar:
```python
def write_config(data: dict) -> None:
    ensure_dirs()
    p = config_dir() / "config.json"
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
```

Substituir por:
```python
def write_config(data: dict) -> None:
    ensure_dirs()
    p = config_dir() / "config.json"
    atomic_write_json(p, data)
```

- [ ] **Step 2: Rodar suite de storage e config**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai/packages/maestra-ai && uv run pytest tests/unit/test_storage.py tests/unit/test_cli_config.py -v 2>&1 | tail -6`
Expected: todos os testes passam. Se algum teste depender de comportamento não-atômico (improvável), investigar.

- [ ] **Step 3: Commit**

```bash
cd /home/menzani/Desenvolvimento/maestra-ai
git add packages/maestra-ai/src/maestra_ai/core/storage.py
git commit -m "fix(storage): write_config usa atomic_write_json (I1 v0.6.1)

Substitui p.write_text(json.dumps(...)) por atomic_write_json(p,
data). Elimina janela de lost-update entre daemon director e CLI
manual escrevendo config.json em paralelo."
```

---

## Task 3: `snapshot.create` atômico (I4)

**Files:**
- Modify: `packages/maestra-ai/src/maestra_ai/core/snapshot.py:50`
- Modify: `packages/maestra-ai/tests/unit/test_snapshot.py`

- [ ] **Step 1: Escrever teste de crash simulado**

Abrir `packages/maestra-ai/tests/unit/test_snapshot.py`. Adicionar nova classe ou novo método em classe existente:

```python
class TestCreateAtomicity:
    def test_create_atomico_em_caso_de_crash_simulado(
        self, tmp_path, monkeypatch,
    ):
        """I4 v0.6.1: se o rename final falhar (crash), nenhum arquivo
        parcial ou .tmp residual deve ficar visível."""
        monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path))

        from maestra_ai.core import snapshot, storage

        # Força os.replace (último passo de atomic_write_json) a falhar.
        import os as _os
        real_replace = _os.replace

        def failing_replace(src, dst):
            raise RuntimeError("simulated crash mid-rename")

        monkeypatch.setattr("maestra_ai.core.storage.os.replace", failing_replace)

        with pytest.raises(RuntimeError, match="simulated crash"):
            snapshot.create("test-op", {"foo": "bar"})

        # Nenhum .json publicado
        snap_dir = storage.snapshots_dir()
        published = list(snap_dir.glob("*.json"))
        assert published == []
```

Verificar imports: `import pytest` no topo do arquivo. Se faltar, adicionar.

- [ ] **Step 2: Rodar e confirmar FALHA**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai/packages/maestra-ai && uv run pytest tests/unit/test_snapshot.py::TestCreateAtomicity -v 2>&1 | tail -10`
Expected: FALHA porque `snapshot.create` ainda usa `path.write_text` (sem tmp+rename), então o `monkeypatch` em `os.replace` não é acionado e o arquivo parcial fica publicado. O teste detectará `len(published) != 0`.

- [ ] **Step 3: Implementar o fix**

Em `packages/maestra-ai/src/maestra_ai/core/snapshot.py`, achar:
```python
    path = _snap_dir() / f"{snap_id}.json"
    payload = {
        "id": snap_id,
        "operation": operation,
        "created_at": ts,
        "state": state,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
```

Substituir a última linha por:
```python
    from maestra_ai.core.storage import atomic_write_json
    atomic_write_json(path, payload)
```

(Import local para manter o import de `storage` no topo limpo; atomic_write_json é helper de baixo nível.)

Se já houver `from maestra_ai.core import storage` no topo do arquivo, usar `storage.atomic_write_json(path, payload)` e descartar o import local.

- [ ] **Step 4: Rodar teste e confirmar PASS**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai/packages/maestra-ai && uv run pytest tests/unit/test_snapshot.py::TestCreateAtomicity -v 2>&1 | tail -5`
Expected: PASS.

- [ ] **Step 5: Rodar suite completa de snapshot**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai/packages/maestra-ai && uv run pytest tests/unit/test_snapshot.py 2>&1 | tail -3`
Expected: todos os testes passam.

- [ ] **Step 6: Commit**

```bash
cd /home/menzani/Desenvolvimento/maestra-ai
git add packages/maestra-ai/src/maestra_ai/core/snapshot.py packages/maestra-ai/tests/unit/test_snapshot.py
git commit -m "fix(snapshot): create usa atomic_write_json (I4 v0.6.1)

Substitui path.write_text(json.dumps(...)) por atomic_write_json.
Crash mid-write deixa no máximo um .tmp residual, nunca um .json
parcial que list_snapshots veria mas load falharia — importante
porque rollback.py cria safety-snapshot justamente quando algo
já está dando errado."
```

---

## Task 4: `audit.log` append locked (I3)

**Files:**
- Modify: `packages/maestra-ai/src/maestra_ai/core/audit.py:42-52`

- [ ] **Step 1: Substituir a implementação de `log`**

Em `packages/maestra-ai/src/maestra_ai/core/audit.py`, achar:

```python
def log(tool: str, args: dict, result: dict) -> None:
    entry = {
        "ts": datetime.now(UTC).isoformat(timespec="seconds"),
        "tool": tool,
        "args": _redact(args),
        "result_summary": _redact_result(result),
    }
    _path_active().parent.mkdir(parents=True, exist_ok=True)
    with _path_active().open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    _maybe_rotate()
```

Substituir o bloco de escrita por uso do helper:

```python
def log(tool: str, args: dict, result: dict) -> None:
    entry = {
        "ts": datetime.now(UTC).isoformat(timespec="seconds"),
        "tool": tool,
        "args": _redact(args),
        "result_summary": _redact_result(result),
    }
    storage.append_jsonl_locked(_path_active(), entry)
    _maybe_rotate()
```

`storage` já está importado no topo (`from maestra_ai.core import storage`). O helper cuida do mkdir.

- [ ] **Step 2: Rodar suite de audit**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai/packages/maestra-ai && uv run pytest tests/unit/test_audit.py 2>&1 | tail -3`
Expected: todos os testes passam.

- [ ] **Step 3: Commit**

```bash
cd /home/menzani/Desenvolvimento/maestra-ai
git add packages/maestra-ai/src/maestra_ai/core/audit.py
git commit -m "fix(audit): log() usa append_jsonl_locked (I3 v0.6.1)

Serializa writes concorrentes no audit.jsonl. MCP server + CLI +
daemon director podiam intercalar bytes de entries longas (>PIPE_BUF,
~4KB), corrompendo o log forense. _force_rotate mantém seu próprio
lock separado."
```

---

## Task 5: `director._record` append locked (I2)

**Files:**
- Modify: `packages/maestra-ai/src/maestra_ai/core/director.py:189-198`

- [ ] **Step 1: Substituir a implementação**

Em `packages/maestra-ai/src/maestra_ai/core/director.py`, achar:

```python
    def _record(self, decision):
        decision = {
            "at": datetime.now().isoformat(timespec="seconds"),
            "component": "maestra-director",
            **decision,
        }
        os.makedirs(os.path.dirname(self.log_path) or ".", exist_ok=True)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(decision, ensure_ascii=False) + "\n")
        return decision
```

Substituir por:

```python
    def _record(self, decision):
        decision = {
            "at": datetime.now().isoformat(timespec="seconds"),
            "component": "maestra-director",
            **decision,
        }
        from maestra_ai.core.storage import append_jsonl_locked
        append_jsonl_locked(self.log_path, decision)
        return decision
```

O `os.makedirs` explícito foi removido porque `append_jsonl_locked` faz isso. Se houver outro uso de `os.makedirs` em outro método, ficar intocado.

- [ ] **Step 2: Rodar suite de director**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai/packages/maestra-ai && uv run pytest tests/unit/test_director.py 2>&1 | tail -3`
Expected: todos os testes passam.

- [ ] **Step 3: Commit**

```bash
cd /home/menzani/Desenvolvimento/maestra-ai
git add packages/maestra-ai/src/maestra_ai/core/director.py
git commit -m "fix(director): _record usa append_jsonl_locked (I2 v0.6.1)

Evita intercalação de bytes entre daemon (loop contínuo) e
director_once (MCP/CLI) escrevendo no mesmo director_decisions.jsonl.
Payloads de decisão com tracks[] passam fácil de PIPE_BUF."
```

---

## Task 6: Guard em `FeedbackPrompter._in_cooldown` (I6)

**Files:**
- Modify: `packages/maestra-ai/src/maestra_ai/core/feedback_prompt.py:85-92`
- Modify: `packages/maestra-ai/tests/unit/test_feedback_prompt.py`

- [ ] **Step 1: Escrever o teste**

Abrir `packages/maestra-ai/tests/unit/test_feedback_prompt.py`. Adicionar nova classe ou método em classe existente:

```python
class TestCooldownCorrupcao:
    def test_cooldown_tolera_fromisoformat_invalido(self, tmp_path):
        """I6 v0.6.1: state corrompido não deve crashar o prompter.
        Retorna False (cooldown expirou, permite novo prompt)."""
        import json
        from maestra_ai.core.feedback_prompt import FeedbackPrompter

        state_path = tmp_path / "state.json"
        state_path.write_text(
            json.dumps({"workout": {"last_prompt_at": "banana"}}),
            encoding="utf-8",
        )
        fp = FeedbackPrompter(state_path=str(state_path), cooldown_minutes=60)
        assert fp._in_cooldown("workout") is False

    def test_cooldown_tolera_last_prompt_at_ausente(self, tmp_path):
        import json
        from maestra_ai.core.feedback_prompt import FeedbackPrompter

        state_path = tmp_path / "state.json"
        state_path.write_text(
            json.dumps({"workout": {"something_else": 1}}),
            encoding="utf-8",
        )
        fp = FeedbackPrompter(state_path=str(state_path), cooldown_minutes=60)
        assert fp._in_cooldown("workout") is False
```

Se a classe `FeedbackPrompter` não aceita `state_path` e `cooldown_minutes` via kwargs, olhar o `__init__` atual do arquivo e ajustar chamada conforme assinatura real. A intenção é instanciar com state path custom e cooldown arbitrário.

- [ ] **Step 2: Rodar e confirmar FALHA**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai/packages/maestra-ai && uv run pytest tests/unit/test_feedback_prompt.py::TestCooldownCorrupcao -v 2>&1 | tail -8`
Expected: primeiro teste FALHA com `ValueError: Invalid isoformat string: 'banana'`.

- [ ] **Step 3: Implementar o guard**

Em `packages/maestra-ai/src/maestra_ai/core/feedback_prompt.py`, achar:

```python
    def _in_cooldown(self, context):
        data = self._load_state()
        entry = data.get(context)
        if not entry:
            return False

        last_prompt_at = datetime.fromisoformat(entry["last_prompt_at"])
        return datetime.now() - last_prompt_at < timedelta(minutes=self.cooldown_minutes)
```

Substituir por:

```python
    def _in_cooldown(self, context):
        data = self._load_state()
        entry = data.get(context)
        if not entry:
            return False
        raw = entry.get("last_prompt_at")
        if not raw:
            return False
        try:
            last_prompt_at = datetime.fromisoformat(raw)
        except (ValueError, TypeError):
            # State corrompido: trata como cooldown expirado.
            return False
        return datetime.now() - last_prompt_at < timedelta(minutes=self.cooldown_minutes)
```

- [ ] **Step 4: Rodar e confirmar PASS**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai/packages/maestra-ai && uv run pytest tests/unit/test_feedback_prompt.py -v 2>&1 | tail -5`
Expected: todos os testes passam, incluindo os 2 novos.

- [ ] **Step 5: Commit**

```bash
cd /home/menzani/Desenvolvimento/maestra-ai
git add packages/maestra-ai/src/maestra_ai/core/feedback_prompt.py packages/maestra-ai/tests/unit/test_feedback_prompt.py
git commit -m "fix(feedback_prompt): guard fromisoformat em _in_cooldown (I6 v0.6.1)

State corrompido (edição manual, fromisoformat inválido, chave
ausente) agora retorna False em vez de crashar com ValueError.
Mesmo padrão que core/context.py:44."
```

---

## Task 7: `MCPInvalidArgsError` em `core/errors.py`

**Files:**
- Modify: `packages/maestra-ai/src/maestra_ai/core/errors.py`

- [ ] **Step 1: Adicionar a nova classe**

Em `packages/maestra-ai/src/maestra_ai/core/errors.py`, logo após `ValidationError` (linha ~278), adicionar:

```python
class MCPInvalidArgsError(UserError):
    """I5 v0.6.1: args passados a uma tool MCP não casam com inputSchema.

    Usado pelo server para traduzir jsonschema.ValidationError em um
    MaestraError estruturado com agent_hint específico por tipo de
    falha (additionalProperties, minimum, required, etc.).
    """

    code = "MCPInvalidArgsError"
    title = "Argumentos MCP inválidos"
    probable_causes = [
        "Tool chamada com campo desconhecido (additionalProperties=false)",
        "Tipo ou valor do campo não corresponde ao schema",
        "Campo obrigatório ausente",
    ]
    suggested_actions = [
        {"command": "list_tools",
         "description": "Ver inputSchema completo de cada tool"},
    ]
    agent_hint = (
        "Entrada rejeitada antes de executar a tool. Consulte o inputSchema "
        "em list_tools e reenvie apenas campos documentados, respeitando "
        "tipos e limites."
    )

    def __init__(
        self,
        what_happened: str = "",
        *,
        hint: str | None = None,
        where: dict | None = None,
    ):
        super().__init__(what_happened, where=where)
        if hint:
            # Override do hint de classe para dica específica do campo.
            self.agent_hint = hint
```

- [ ] **Step 2: Smoke test — import + to_human_dict**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai/packages/maestra-ai && uv run python -c "
from maestra_ai.core.errors import MCPInvalidArgsError, UserError, MaestraError
e = MCPInvalidArgsError('queue: missing track_uri', hint='campo obrigatório ausente: track_uri')
assert isinstance(e, UserError)
assert isinstance(e, MaestraError)
d = e.to_human_dict()
assert d['code'] == 'MCPInvalidArgsError'
assert d['agent_hint'] == 'campo obrigatório ausente: track_uri'
print('ok')
"`
Expected: imprime `ok`.

- [ ] **Step 3: Commit**

```bash
cd /home/menzani/Desenvolvimento/maestra-ai
git add packages/maestra-ai/src/maestra_ai/core/errors.py
git commit -m "feat(errors): MCPInvalidArgsError(UserError) (I5 v0.6.1)

Nova subclasse de UserError com hint per-instance (override do
agent_hint de classe). Preparação para Task 8 — validação de args
MCP via jsonschema em tools.call_tool."
```

---

## Task 8: Validação MCP em `tools.call_tool` (I5, TDD)

**Files:**
- Modify: `packages/maestra-mcp/pyproject.toml`
- Modify: `packages/maestra-mcp/src/maestra_mcp/tools.py`
- Create: `packages/maestra-mcp/tests/test_server_validation.py`

- [ ] **Step 1: Adicionar `jsonschema` como dep do maestra-mcp**

Em `packages/maestra-mcp/pyproject.toml`, achar:
```toml
dependencies = [
    "maestra-ai==0.5.7",
    "mcp>=1.0,<2.0",
]
```

Substituir por (atualizando também o pin — a v0.6.0a0 já foi bumpada, então o pin atual pode ser `0.6.0a0`):

```toml
dependencies = [
    "maestra-ai==0.6.0a0",
    "mcp>=1.0,<2.0",
    "jsonschema>=4.0,<5.0",
]
```

**Atenção:** na Task 12 esse pin será atualizado novamente para `0.6.1a0`. Por ora, preservar o pin corrente da build local.

- [ ] **Step 2: uv sync para instalar jsonschema**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai && uv sync --all-extras 2>&1 | tail -5`
Expected: `jsonschema` instalado sem erro.

- [ ] **Step 3: Escrever os 4 testes de validação**

Criar arquivo `packages/maestra-mcp/tests/test_server_validation.py` com:

```python
"""Testes de validação de args MCP contra inputSchema (I5 v0.6.1)."""
from __future__ import annotations

import pytest


@pytest.fixture
def register_test_tool(monkeypatch):
    """Registra uma tool de teste com schema estrito para validação."""
    from maestra_mcp import tools as tools_mod

    # Salva o registry original para restaurar no teardown.
    original_registry = dict(tools_mod._REGISTRY)

    schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 50},
        },
        "required": ["query"],
        "additionalProperties": False,
    }

    async def handler(args):
        return {"ok": True, "received": args}

    from maestra_mcp.tools import ToolDef
    tools_mod._REGISTRY["_test_tool"] = ToolDef(
        name="_test_tool",
        description="tool de teste",
        schema=schema,
        handler=handler,
    )
    yield
    # Restaura registry.
    tools_mod._REGISTRY.clear()
    tools_mod._REGISTRY.update(original_registry)


class TestValidacaoArgs:
    async def test_additional_properties_rejeita_campo_desconhecido(
        self, register_test_tool,
    ):
        from maestra_mcp.tools import call_tool
        result = await call_tool("_test_tool", {"query": "x", "extra": "y"})
        assert "error" in result
        assert result["error"]["code"] == "MCPInvalidArgsError"
        # agent_hint deve mencionar o campo desconhecido.
        assert "extra" in result["error"]["agent_hint"] or "desconhecido" in result["error"]["agent_hint"]

    async def test_minimum_rejeita_valor_fora(self, register_test_tool):
        from maestra_mcp.tools import call_tool
        result = await call_tool("_test_tool", {"query": "x", "limit": 0})
        assert "error" in result
        assert result["error"]["code"] == "MCPInvalidArgsError"

    async def test_required_rejeita_ausencia(self, register_test_tool):
        from maestra_mcp.tools import call_tool
        result = await call_tool("_test_tool", {})
        assert "error" in result
        assert result["error"]["code"] == "MCPInvalidArgsError"
        assert "query" in result["error"]["agent_hint"]

    async def test_args_validos_passam(self, register_test_tool):
        from maestra_mcp.tools import call_tool
        result = await call_tool("_test_tool", {"query": "x", "limit": 10})
        assert result == {"ok": True, "received": {"query": "x", "limit": 10}}
```

- [ ] **Step 4: Rodar e confirmar FALHA**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai/packages/maestra-mcp && uv run pytest tests/test_server_validation.py -v 2>&1 | tail -12`
Expected: 3 FAILED (os inválidos passam hoje), 1 PASSED (args válidos). Prova que a validação ainda não existe.

- [ ] **Step 5: Implementar validação em `call_tool`**

Em `packages/maestra-mcp/src/maestra_mcp/tools.py`, achar:

```python
async def call_tool(name: str, args: dict) -> Any:
    """Dispatch para o handler registrado. Captura MaestraError e genéricas."""
    td = _REGISTRY.get(name)
    if td is None:
        from maestra_ai.core.errors import UserError
        err = UserError(f"Tool '{name}' não existe.")
        return {"error": err.to_human_dict()}
    try:
        return await td.handler(args)
    except Exception as e:
        from maestra_ai.core.errors import MaestraError
        if isinstance(e, MaestraError):
            return {"error": e.to_human_dict()}
        return {
            "error": {
                "code": type(e).__name__,
                "title": "Erro inesperado",
                "what_happened": str(e),
            },
        }
```

Substituir por:

```python
def _format_schema_hint(err) -> str:
    """Converte jsonschema.ValidationError em dica curta para o agente.

    Usa só o nome do campo e o validator; nunca vaza o valor (redaction).
    """
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
        return f"campo desconhecido (use apenas os documentados no inputSchema)"
    if validator == "type":
        return f"campo `{path}` deve ser {value}"
    if validator == "enum":
        return f"campo `{path}` deve ser um de: {value}"
    return f"validação falhou em `{path}` ({validator})"


async def call_tool(name: str, args: dict) -> Any:
    """Dispatch para o handler registrado. Valida args contra inputSchema
    antes de invocar; captura MaestraError e genéricas."""
    td = _REGISTRY.get(name)
    if td is None:
        from maestra_ai.core.errors import UserError
        err = UserError(f"Tool '{name}' não existe.")
        return {"error": err.to_human_dict()}

    # I5 v0.6.1: boundary MCP valida args antes de chamar o handler.
    import jsonschema
    from maestra_ai.core.errors import MCPInvalidArgsError
    try:
        jsonschema.validate(args, td.schema)
    except jsonschema.ValidationError as ve:
        err = MCPInvalidArgsError(
            f"{name}: {ve.message}",
            hint=_format_schema_hint(ve),
        )
        return {"error": err.to_human_dict()}

    try:
        return await td.handler(args)
    except Exception as e:
        from maestra_ai.core.errors import MaestraError
        if isinstance(e, MaestraError):
            return {"error": e.to_human_dict()}
        return {
            "error": {
                "code": type(e).__name__,
                "title": "Erro inesperado",
                "what_happened": str(e),
            },
        }
```

- [ ] **Step 6: Rodar e confirmar PASS**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai/packages/maestra-mcp && uv run pytest tests/test_server_validation.py -v 2>&1 | tail -8`
Expected: 4 passed.

- [ ] **Step 7: Rodar suite completa maestra-mcp**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai/packages/maestra-mcp && uv run pytest tests/ 2>&1 | tail -3`
Expected: ~39 passed (35 antigos + 4 novos).

- [ ] **Step 8: Commit**

```bash
cd /home/menzani/Desenvolvimento/maestra-ai
git add packages/maestra-mcp/src/maestra_mcp/tools.py packages/maestra-mcp/tests/test_server_validation.py packages/maestra-mcp/pyproject.toml
git commit -m "feat(mcp): validação de args via jsonschema em call_tool (I5 v0.6.1)

Adiciona jsonschema>=4.0 como dep do maestra-mcp. tools.call_tool
valida args contra inputSchema antes de invocar o handler;
ValidationError → MCPInvalidArgsError com agent_hint específico
por tipo (minimum, required, additionalProperties, type, enum).

Quatro testes cobrem: campo desconhecido, valor abaixo do mínimo,
required ausente, args válidos passam inalterados."
```

---

## Task 9: Rename `_is_rejected` → `is_rejected` em taste + curator

**Files:**
- Modify: `packages/maestra-ai/src/maestra_ai/core/taste.py:480`
- Modify: `packages/maestra-ai/src/maestra_ai/core/taste.py:469` (caller interno)
- Modify: `packages/maestra-ai/src/maestra_ai/core/curator.py:76`
- Modify: testes que referenciam `_is_rejected`

- [ ] **Step 1: Encontrar todos os call sites**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai && grep -rn "_is_rejected" packages/ 2>&1`

Registrar todos os arquivos e linhas retornados. Esperado: `core/taste.py` (definição + 1 chamada interna), `core/curator.py` (1 chamada), testes.

- [ ] **Step 2: Rename da definição em `taste.py`**

Em `packages/maestra-ai/src/maestra_ai/core/taste.py:480`, achar:

```python
    def _is_rejected(self, uri):
        """Verifica se uma faixa está rejeitada no perfil."""
        track = self.data["tracks"].get(uri)
        if not track:
            return False
        return track.get("feedback") == "bad"
```

Substituir por:

```python
    def is_rejected(self, uri):
        """Verifica se uma faixa está rejeitada no perfil.

        **API pública** — consumida por `curator.curate` e testes.
        """
        track = self.data["tracks"].get(uri)
        if not track:
            return False
        return track.get("feedback") == "bad"
```

- [ ] **Step 3: Atualizar caller interno em taste.py**

Achar `if not self._is_rejected(uri)` (linha 469) e trocar por `if not self.is_rejected(uri)`.

- [ ] **Step 4: Atualizar caller em curator.py**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai && grep -n "_is_rejected" packages/maestra-ai/src/maestra_ai/core/curator.py`
Para cada linha retornada, trocar `_is_rejected` por `is_rejected`.

- [ ] **Step 5: Atualizar testes**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai && grep -rn "_is_rejected" packages/maestra-ai/tests/`
Para cada ocorrência, trocar `_is_rejected` por `is_rejected`.

- [ ] **Step 6: Verificar zero ocorrências remanescentes**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai && grep -rn "_is_rejected" packages/`
Expected: sem saída (ou apenas em CHANGELOG/docs se aplicável).

- [ ] **Step 7: Rodar suite completa**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai/packages/maestra-ai && uv run pytest tests/unit/ 2>&1 | tail -3`
Expected: todos os testes passam.

- [ ] **Step 8: Commit**

```bash
cd /home/menzani/Desenvolvimento/maestra-ai
git add -A
git commit -m "refactor(taste): rename _is_rejected → is_rejected (I7.1 v0.6.1)

Promove para API pública — consumido por curator.curate e testes.
Sem deprecation alias (pre-1.0, zero consumidores externos)."
```

---

## Task 10: Rename `_prune_candidates` → `prune_candidates` + callers

**Files:**
- Modify: `packages/maestra-ai/src/maestra_ai/core/taste.py:522, 597`
- Modify: `packages/maestra-ai/src/maestra_ai/cli/_common.py:126`
- Modify: testes

- [ ] **Step 1: Encontrar todos os call sites**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai && grep -rn "_prune_candidates" packages/ 2>&1`

- [ ] **Step 2: Rename da definição em `taste.py`**

Em `packages/maestra-ai/src/maestra_ai/core/taste.py:522`, achar:

```python
def _prune_candidates(tracks, profile, context):
    candidates = []
    for track in tracks:
```

Trocar por:

```python
def prune_candidates(tracks, profile, context):
    """Decide quais faixas de uma playlist são candidatas a remoção.

    **API pública** — consumida por `cli/_common.py` e testes.
    Retorna lista de `{**track, reason, context_score}`.
    """
    candidates = []
    for track in tracks:
```

- [ ] **Step 3: Atualizar caller interno em taste.py**

Achar (linha ~597) `prune_candidates = _prune_candidates(playlist_tracks, ...)` e trocar por `prune_candidates = prune_candidates(playlist_tracks, ...)`.

**Atenção:** o nome da variável local no lado esquerdo colide com o da função depois do rename. Renomear a variável local para evitar shadowing: `prunable = prune_candidates(playlist_tracks, profile, context)`. Em seguida, atualizar as referências a essa variável no mesmo escopo (use grep próximo à linha para ver onde ela é usada).

Run dentro do mesmo bloco: `cd /home/menzani/Desenvolvimento/maestra-ai && sed -n '595,630p' packages/maestra-ai/src/maestra_ai/core/taste.py` para inspecionar o uso.

Depois: substituir `prune_candidates` (a variável local) por `prunable` em TODAS as linhas do escopo onde aparecer.

- [ ] **Step 4: Atualizar caller em `cli/_common.py`**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai && grep -n "_prune_candidates" packages/maestra-ai/src/maestra_ai/cli/_common.py`

Para cada ocorrência, trocar `taste_mod._prune_candidates(...)` por `taste_mod.prune_candidates(...)`.

- [ ] **Step 5: Atualizar testes**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai && grep -rn "_prune_candidates" packages/maestra-ai/tests/`
Trocar em cada ocorrência.

- [ ] **Step 6: Verificar zero ocorrências remanescentes**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai && grep -rn "_prune_candidates" packages/`
Expected: sem saída.

- [ ] **Step 7: Rodar suite completa**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai/packages/maestra-ai && uv run pytest tests/unit/ 2>&1 | tail -3`
Expected: todos os testes passam.

- [ ] **Step 8: Commit**

```bash
cd /home/menzani/Desenvolvimento/maestra-ai
git add -A
git commit -m "refactor(taste): rename _prune_candidates → prune_candidates (I7.2 v0.6.1)

Promove função module-level para API pública — consumida por
cli/_common.py e testes. Variável local que colidia com o novo
nome renomeada para 'prunable'."
```

---

## Task 11: Rename `_signal_weight` → `signal_weight` + callers

**Files:**
- Modify: `packages/maestra-ai/src/maestra_ai/core/taste.py:514`
- Modify: `packages/maestra-ai/src/maestra_ai/cli/_common.py:159`
- Modify: testes

- [ ] **Step 1: Encontrar call sites**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai && grep -rn "_signal_weight" packages/ 2>&1`

- [ ] **Step 2: Rename da definição em `taste.py`**

Em `packages/maestra-ai/src/maestra_ai/core/taste.py:514`, achar:

```python
def _signal_weight(signal):
    if signal == "good":
        return 1
    if signal in ("bad", "skip"):
        return -1
    return 0
```

Trocar por:

```python
def signal_weight(signal):
    """Retorna peso numérico do sinal de feedback.

    **API pública** — consumida por `cli/_common.py` e testes.
    Mapa: good→1, bad/skip→-1, outros→0.
    """
    if signal == "good":
        return 1
    if signal in ("bad", "skip"):
        return -1
    return 0
```

- [ ] **Step 3: Atualizar caller em `cli/_common.py`**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai && grep -n "_signal_weight" packages/maestra-ai/src/maestra_ai/cli/_common.py`

Para cada ocorrência, trocar `taste_mod._signal_weight(...)` por `taste_mod.signal_weight(...)`.

- [ ] **Step 4: Atualizar testes**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai && grep -rn "_signal_weight" packages/maestra-ai/tests/`
Trocar em cada ocorrência.

- [ ] **Step 5: Verificar zero ocorrências remanescentes**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai && grep -rn "_signal_weight" packages/`
Expected: sem saída.

- [ ] **Step 6: Rodar suite completa**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai/packages/maestra-ai && uv run pytest tests/unit/ tests/integration/ 2>&1 | tail -3 && cd ../maestra-mcp && uv run pytest tests/ 2>&1 | tail -3`
Expected: ambas suites verdes.

- [ ] **Step 7: Commit**

```bash
cd /home/menzani/Desenvolvimento/maestra-ai
git add -A
git commit -m "refactor(taste): rename _signal_weight → signal_weight (I7.3 v0.6.1)

Última parte do rename privado→público em taste. API pública
estabilizada para curator/cli/_common. Pre-1.0, zero deprecation."
```

---

## Task 12: Bump v0.6.1-alpha.0 + CHANGELOG + backlog + tag

**Files:**
- Modify: `packages/maestra-ai/pyproject.toml`
- Modify: `packages/maestra-mcp/pyproject.toml`
- Modify: `CHANGELOG.md`
- Modify: `docs/reviews/2026-04-19-v060-post-release.md`
- Modify: `README.md`

- [ ] **Step 1: Validação pré-bump — suite completa**

Run:
```bash
cd /home/menzani/Desenvolvimento/maestra-ai/packages/maestra-ai && uv run pytest tests/unit/ tests/integration/ 2>&1 | tail -3
cd /home/menzani/Desenvolvimento/maestra-ai/packages/maestra-mcp && uv run pytest tests/ 2>&1 | tail -3
```
Expected: ~465 (maestra-ai) + ~39 (maestra-mcp) = ~504 passed.

- [ ] **Step 2: Bump `packages/maestra-ai/pyproject.toml`**

Achar `version = "0.6.0a0"` e trocar por `version = "0.6.1a0"`.

- [ ] **Step 3: Bump `packages/maestra-mcp/pyproject.toml`**

Achar `version = "0.6.0a0"` e trocar por `version = "0.6.1a0"`.
Achar `"maestra-ai==0.6.0a0"` e trocar por `"maestra-ai==0.6.1a0"`.

- [ ] **Step 4: Atualizar status no README**

Em `/home/menzani/Desenvolvimento/maestra-ai/README.md`, achar:
`**Status:** pre-alpha (v0.6.0-alpha). Lançamento público planejado em v1.0.0.`
Trocar por:
`**Status:** pre-alpha (v0.6.1-alpha). Lançamento público planejado em v1.0.0.`

- [ ] **Step 5: Adicionar entrada no CHANGELOG**

Abrir `CHANGELOG.md`. Logo após `## [Unreleased]` e antes de `## [0.6.0-alpha.0] - 2026-04-19`, adicionar:

```markdown
## [0.6.1-alpha.0] - 2026-04-19

Release só de correção — fecha os 7 itens Important do review
pós-v0.6.0-alpha.0 (ver `docs/reviews/2026-04-19-v060-post-release.md`).
Zero feature nova, zero breaking no CLI, zero breaking no output
do MCP para clientes válidos. Suite: ~504 (maestra-ai + maestra-mcp).

### Fixed
- **I1** — `storage.write_config` agora usa `atomic_write_json`
  (rename atômico via `os.replace`). Elimina janela de lost-update
  entre daemon director e CLI manual.
- **I2** — `director._record` usa `storage.append_jsonl_locked`
  com `fcntl.LOCK_EX`. Payloads de decisão com `tracks[]` passam
  de PIPE_BUF (~4KB), e o lock evita intercalação de bytes entre
  daemon e `director_once` via MCP.
- **I3** — `audit.log` idem. MCP server + CLI + daemon podiam
  corromper o audit.jsonl em paralelo; agora são serializados.
- **I4** — `snapshot.create` usa `atomic_write_json`. Crash
  mid-write deixa no máximo um `.tmp` residual, nunca um `.json`
  parcial (importante porque `rollback.py` cria safety-snapshot
  justamente quando algo já está dando errado).
- **I6** — `FeedbackPrompter._in_cooldown` guarda `fromisoformat`
  contra state corrompido (edição manual, valor inválido, chave
  ausente). Antes crashava com `ValueError`; agora retorna `False`
  (cooldown expirou). Mesmo padrão de `context.py:44`.

### Added
- **I5** — validação de args MCP contra `inputSchema`. Dep nova
  `jsonschema>=4.0` em maestra-mcp. `tools.call_tool` valida antes
  de invocar o handler; `ValidationError` é traduzido em
  `MCPInvalidArgsError(UserError)` com `agent_hint` específico por
  tipo (minimum, required, additionalProperties, type, enum).
- **`MCPInvalidArgsError`** em `core/errors.py` — subclasse de
  `UserError` com hint per-instance (override do agent_hint de classe).
- **`core.storage.append_jsonl_locked(path, entry)`** — helper
  público para append JSONL serializado com `fcntl.LOCK_EX`.

### Changed (breaking — renames em taste, pre-1.0)
- **I7** — promove 3 símbolos privados para API pública em
  `core/taste.py`:
  - `TasteProfile._is_rejected` → `TasteProfile.is_rejected`
  - `_prune_candidates` → `prune_candidates`
  - `_signal_weight` → `signal_weight`
  Callers atualizados em `core/curator.py` e `cli/_common.py`.
  Sem deprecation alias — zero consumidores externos conhecidos.

### Tests
- +2 em `TestAppendJsonlLocked` (serialização + concorrência 2×50).
- +1 em `TestCreateAtomicity` (crash simulado em `os.replace`).
- +2 em `TestCooldownCorrupcao` (fromisoformat inválido + chave ausente).
- +4 em `TestValidacaoArgs` (MCP: additionalProperties, minimum, required, válido).
- Testes que importavam os nomes privados de taste foram atualizados.
```

- [ ] **Step 6: Atualizar backlog review**

Em `docs/reviews/2026-04-19-v060-post-release.md`, achar a seção "## Important (7)" e logo antes adicionar:

```markdown
> **Status v0.6.1-alpha.0 (2026-04-19):** todos os 7 itens Important
> (I1-I7) foram fechados. Detalhes no CHANGELOG [0.6.1-alpha.0].
```

- [ ] **Step 7: Re-sync do workspace**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai && uv sync --all-extras 2>&1 | tail -3`
Expected: `maestra-ai==0.6.1a0` e `maestra-mcp==0.6.1a0` instalados.

- [ ] **Step 8: Validação final**

Run:
```bash
cd /home/menzani/Desenvolvimento/maestra-ai/packages/maestra-ai && uv run pytest tests/unit/ tests/integration/ 2>&1 | tail -3
cd /home/menzani/Desenvolvimento/maestra-ai/packages/maestra-mcp && uv run pytest tests/ 2>&1 | tail -3
```
Expected: ~504 passed combinados, zero falhas.

- [ ] **Step 9: Commit + tag**

```bash
cd /home/menzani/Desenvolvimento/maestra-ai
git add -A
git commit -m "chore: bump v0.6.1-alpha.0 — I/O boundaries + atomicity

Fecha os 7 Important do review pós-v0.6.0-alpha.0:
- I1-I4: atomicidade (write_config, snapshot, audit, director)
- I5: validação MCP via jsonschema
- I6: guard fromisoformat em FeedbackPrompter
- I7: rename privado→público em taste

Zero feature nova, zero breaking no CLI. Pin maestra-ai atualizado
em maestra-mcp. Ver CHANGELOG [0.6.1-alpha.0]."
git tag -a v0.6.1-alpha.0 -m "v0.6.1-alpha.0 — hardening de I/O e boundaries"
```

---

## Self-Review

### Spec coverage

| Spec § | Task |
|---|---|
| §3.1 helper + I1-I4 migrações | Tasks 1-5 |
| §3.2 MCP + `MCPInvalidArgsError` | Tasks 7, 8 |
| §3.3 guard _in_cooldown | Task 6 |
| §3.4-3.5 renames | Tasks 9, 10, 11 |
| §5 testes | espalhados nas respectivas tasks (1, 3, 6, 8) |
| §6 critérios de aceite | Task 12 (validação + bump + changelog + tag) |

Sem gaps. Nenhum requisito do spec fica sem task.

### Placeholder scan

Checado: zero "TBD"/"TODO"/"similar to Task N". Todos os snippets de código estão completos. Todos os comandos de shell têm `cd` explícito e saída esperada.

**Exceção consciente em Task 10 Step 3**: instrução para renomear variável local via `sed -n` inspecionar + manual — não é placeholder, é uma etapa que depende do contexto local do arquivo (pode haver múltiplas referências à variável). A instrução é concreta: "substituir `prune_candidates` (variável local) por `prunable` no escopo".

### Type consistency

- `append_jsonl_locked(path, entry: dict) -> None` — assinatura consistente em Tasks 1, 4, 5.
- `MCPInvalidArgsError(what_happened: str, *, hint: str | None = None, where=None)` — consistente entre Task 7 (definição) e Task 8 (uso no `call_tool`).
- `signal_weight`, `prune_candidates`, `is_rejected` — mesmos nomes públicos em Tasks 9, 10, 11 e nas docstrings.
- `_format_schema_hint` em Task 8 é helper privado dentro de `tools.py`; não é compartilhado externamente.
