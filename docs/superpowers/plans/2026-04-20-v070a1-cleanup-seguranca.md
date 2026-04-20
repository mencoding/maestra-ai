# v0.7.0-alpha.1 — cleanup + segurança Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Aplicar todos os 24 achados do review pós-v0.7.0-alpha.0 (14 dead code + 10 segurança) e publicar alpha.1.

**Architecture:** Release de higiene. Um bloco crítico (S1), um bloco lint-automático (ruff), e depois batches de remoções/hardening em commits pequenos. Sem features novas.

**Tech Stack:** Python 3.11+, uv workspace, pytest, ruff, jsonschema, mcp. Arquivos afetados: `core/{audit, security, snapshot, playback, director, taste, curator, storage, history, onboard, onboard_types}`, `cli/{config, _common, help, taste}`, `maestra_mcp/{server, tools}`.

**Base:** 69d6573 (tag v0.7.0-alpha.0). Suíte atual: 507 maestra-ai + 45 mcp = 552 verdes.

---

## Decisões de escopo

- **D1**: aplicar TypedDicts (opção "a" do review) — aproveita investimento v0.7.0, corrige CHANGELOG sem retirar contratos prometidos.
- **D11** (`_context_query_candidates`): simplificar inline (sem remoção agressiva) — review sugere v0.8 mas usuário pediu "aplicar todos".
- **S10** (`normalize_playlist_id`): usar regex ancorada para URIs padrão (`spotify:playlist:ID` e `open.spotify.com/playlist/ID`), mantendo fallback permissivo com warning — evita quebrar entradas legadas.
- **S6** (JWT regex não-canônico): aceitar limite e documentar no docstring — fix real exigiria generic high-entropy matcher com false positives.
- **D13** e **D9**: manter (review 🟢).

---

### Task 1: S1 CRÍTICO — Redigir erros no boundary MCP

**Files:**
- Modify: `packages/maestra-mcp/src/maestra_mcp/server.py:72-110`
- Modify: `packages/maestra-mcp/src/maestra_mcp/tools.py:63-97`
- Test: `packages/maestra-mcp/tests/unit/test_server.py` (adicionar `TestErrorRedaction`)
- Test: `packages/maestra-mcp/tests/unit/test_tools.py` (adicionar redaction no call_tool)

- [ ] **Step 1: Failing test — Bearer token em exceção não-MaestraError vaza pelo boundary**

```python
# test_tools.py — dentro de TestCallTool ou nova TestCallToolRedaction
async def test_call_tool_redacts_bearer_in_generic_exception(monkeypatch):
    from maestra_mcp import tools as tools_mod

    @tools_mod.tool(
        "leaky_test_tool", "Tool que vaza",
        {"type": "object", "properties": {}, "additionalProperties": False},
    )
    def _leaky(_args):
        raise RuntimeError("401 Unauthorized Bearer BQC-abc123def456ghi789")

    try:
        result = await tools_mod.call_tool("leaky_test_tool", {})
    finally:
        del tools_mod._REGISTRY["leaky_test_tool"]

    assert "error" in result
    assert "Bearer BQC" not in result["error"]["what_happened"]
    assert "REDACTED" in result["error"]["what_happened"]
```

- [ ] **Step 2: Verify fail**

Run: `uv run pytest packages/maestra-mcp/tests/unit/test_tools.py::TestCallToolRedaction -v`
Expected: FAIL — "Bearer BQC" presente no output.

- [ ] **Step 3: Failing test — erro de MaestraError também é redigido**

```python
async def test_call_tool_redacts_maestra_error_with_authorization_header():
    from maestra_mcp import tools as tools_mod
    from maestra_ai.core.errors import UserError

    @tools_mod.tool(
        "leaky_maestra_tool", "Tool que vaza via MaestraError",
        {"type": "object", "properties": {}, "additionalProperties": False},
    )
    def _leaky(_args):
        err = UserError("falhou: authorization: Bearer xyz123abc456")
        raise err

    try:
        result = await tools_mod.call_tool("leaky_maestra_tool", {})
    finally:
        del tools_mod._REGISTRY["leaky_maestra_tool"]

    what = result["error"]["what_happened"]
    assert "Bearer xyz123" not in what
    assert "REDACTED" in what
```

- [ ] **Step 4: Verify fail**

Run: `uv run pytest packages/maestra-mcp/tests/unit/test_tools.py -k "redacts_maestra_error" -v`
Expected: FAIL.

- [ ] **Step 5: Implementar em `tools.py:84-96`**

Atualizar o bloco `try/except` em `call_tool`:

```python
try:
    return await td.handler(args)
except Exception as e:
    from maestra_ai.core.errors import MaestraError
    from maestra_ai.core.security import redact_error_dict, redact_str
    if isinstance(e, MaestraError):
        return {"error": redact_error_dict(e.to_human_dict())}
    return {
        "error": {
            "code": type(e).__name__,
            "title": "Erro inesperado",
            "what_happened": redact_str(str(e)),
        },
    }
```

Também redigir erros anteriores no mesmo `call_tool`:
- Linha 70 (`err = UserError(f"Tool '{name}' não existe.")`) → `{"error": redact_error_dict(err.to_human_dict())}`
- Linha 82 (`MCPInvalidArgsError`) → idem.

- [ ] **Step 6: Implementar em `server.py:_build_call_tool_handler`**

Wrap do fallback de exceção genérica e do caso `disabled_tools`:

```python
from maestra_ai.core.security import redact_error_dict, redact_str
# ...
if name in disabled:
    err = UserError(f"Tool desabilitada via config: {name}")
    return [types.TextContent(
        type="text",
        text=json.dumps(
            {"error": redact_error_dict(err.to_human_dict())},
            ensure_ascii=False,
        ),
    )]

try:
    result = await call_tool(name, args or {})
except Exception as e:
    result = {
        "error": {
            "code": "InternalError",
            "title": "Erro não tratado em tool",
            "what_happened": redact_str(str(e)),
        },
    }
```

- [ ] **Step 7: Verify pass**

Run: `uv run pytest packages/maestra-mcp/ -v`
Expected: todos passam, incluindo os 2 novos.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "fix(mcp): redigir secrets em erros retornados pelo boundary (S1 crítico)"
```

---

### Task 2: Lint — ruff autofix + ajustes manuais

**Files:**
- Auto: múltiplos (I001, F401, UP017, UP037)
- Modify manual: `packages/maestra-ai/src/maestra_ai/core/onboard.py:~574,~581` (F401 + F821)
- Modify manual: `packages/maestra-ai/tests/unit/test_onboard.py:1549` (F841 — cobre D14)
- Modify manual: N806 e N818 conforme ruff apontar

- [ ] **Step 1: Baseline ruff**

Run: `uv run ruff check packages/ | tee /tmp/ruff-before.txt`
Expected: 26 erros reportados (conforme review).

- [ ] **Step 2: Autofix**

Run: `uv run ruff check --fix packages/`
Expected: ~22 erros fixados (I001 ordering, imports unused, UP017 datetime.UTC, UP037 typing).

- [ ] **Step 3: Corrigir F401/F821 em onboard.py manualmente**

Em `packages/maestra-ai/src/maestra_ai/core/onboard.py`:
- Remover `from pathlib import Path` dentro de `_persist_rationale` (~linha 581).
- Garantir `from pathlib import Path` no topo do módulo (se ainda não houver).
- Trocar anotação `-> "Path"` por `-> Path`.

- [ ] **Step 4: Corrigir F841 em test_onboard.py:1549**

```python
# Antes:
report = onboard.run(sp=mock_sp, ...)
# Depois:
onboard.run(sp=mock_sp, ...)
```

- [ ] **Step 5: Corrigir resíduos (N806, N818)**

Run: `uv run ruff check packages/`
Para cada erro restante, aplicar o fix apontado pela mensagem. N818 pode pedir renomear exceção sem sufixo `Error` — avaliar por nome. Se gerar breaking change inaceitável, adicionar `# noqa: N818` com comentário explicando.

- [ ] **Step 6: Verify ruff limpo**

Run: `uv run ruff check packages/`
Expected: "All checks passed!" ou exit code 0.

- [ ] **Step 7: Tests verdes**

Run: `uv run pytest packages/ -q`
Expected: 552 passed (sem regressão).

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "style: ruff autofix + ajustes manuais (D12, D14, imports/lint)"
```

---

### Task 3: Dead code — remover shims e duplicatas

**Files:**
- Modify: `packages/maestra-ai/src/maestra_ai/cli/config.py:29-33` — remover `_stub`
- Modify: `packages/maestra-ai/src/maestra_ai/cli/_common.py:90-95` — remover `_pid_running`
- Modify: `packages/maestra-ai/src/maestra_ai/cli/_common.py:156-159` — remover `_signal_weight`
- Modify: `packages/maestra-ai/src/maestra_ai/core/taste.py:553-614` — eliminar alias `_prune_candidates_fn`

- [ ] **Step 1: Verify zero callers para cada um**

```bash
rg "_stub" packages/
rg "_pid_running" packages/maestra-ai/src/maestra_ai/cli/
rg "_signal_weight" packages/
rg "_prune_candidates_fn" packages/
```

Confirmar: `_stub` só em `cli/config.py`; `_pid_running` em `cli/_common.py` sem callers externos; `_signal_weight` só a definição; `_prune_candidates_fn` só em `taste.py`.

- [ ] **Step 2: Remover `_stub` em `cli/config.py:29-33`**

Deletar a função `def _stub(args): ...` e qualquer referência direta.

- [ ] **Step 3: Remover `_pid_running` em `cli/_common.py:90-95`**

Deletar a função. Nenhum import externo precisa mudar (já usam `core.director._pid_running`).

- [ ] **Step 4: Remover `_signal_weight` em `cli/_common.py:156-159`**

Deletar o shim. Verificar com grep que não há caller esquecido.

- [ ] **Step 5: Eliminar alias em `taste.py`**

Em `review()`, renomear parâmetro `prune_candidates=None` → `prune_candidates_override=None`. O corpo passa a chamar `prune_candidates(...)` diretamente (função do módulo). Remover a linha `_prune_candidates_fn = prune_candidates`.

- [ ] **Step 6: Tests verdes**

Run: `uv run pytest packages/ -q`
Expected: 552 passed.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "refactor: remover shims obsoletos e alias _prune_candidates_fn (D2-D4, D6)"
```

---

### Task 4: D1 — Aplicar TypedDicts de onboard

**Files:**
- Modify: `packages/maestra-ai/src/maestra_ai/core/onboard.py` — aplicar `SelectedPlaylist`, `FailedPlaylist`, `OnboardSignals`, `TrackRationale`, `RationaleEntry` onde se encaixam

- [ ] **Step 1: Aplicar `SelectedPlaylist` e `FailedPlaylist`**

Em `onboard.py`, localizar `expansion_info["selected_playlists"].append({"id": ..., "name": ...})` e `expansion_info["failed_playlists"].append({"id": pid, "reason": ...})`. Importar os tipos e construir via:

```python
from maestra_ai.core.onboard_types import SelectedPlaylist, FailedPlaylist
# ...
sel: SelectedPlaylist = {"id": pid, "name": pname}
expansion_info["selected_playlists"].append(sel)
```

- [ ] **Step 2: Aplicar `OnboardSignals` ao return de `run()`**

O campo `signals` do report passa a ser anotado como `OnboardSignals`. Construir explicitamente:

```python
from maestra_ai.core.onboard_types import OnboardSignals
signals: OnboardSignals = {
    "top_genres": top_genres[:10],
    "dominant_decades": decades[:3],
    "top_artists": top_artists[:10],
}
```

- [ ] **Step 3: Aplicar `TrackRationale` e `RationaleEntry` em `_build_rationale`**

Anotar o retorno:

```python
def _build_rationale(...) -> RationaleEntry:
    contributing: list[TrackRationale] = [...]
    return {"text": text, "based_on": based_on, "contributing_tracks": contributing}
```

- [ ] **Step 4: Verify types**

Run: `uv run mypy packages/maestra-ai/src/maestra_ai/core/onboard.py --ignore-missing-imports 2>&1 | head -20`
Expected: sem erros novos nos pontos tocados. Se mypy reclamar de dict lit vs TypedDict, ajustar.

- [ ] **Step 5: Tests verdes**

Run: `uv run pytest packages/maestra-ai/tests/unit/test_onboard.py -q`
Expected: passa.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor(onboard): aplicar TypedDicts exportados em onboard_types (D1)"
```

---

### Task 5: S2 — PlaybackObserver usa append_jsonl_locked

**Files:**
- Modify: `packages/maestra-ai/src/maestra_ai/core/playback.py:130-137`
- Test: `packages/maestra-ai/tests/unit/test_playback.py` — novo teste de concorrência ou substituição do mock de `open`

- [ ] **Step 1: Failing test — writes concorrentes não corrompem jsonl**

```python
# test_playback.py
def test_append_events_usa_lock_e_nao_corrompe_concorrencia(tmp_path, monkeypatch):
    import threading
    from maestra_ai.core.playback import PlaybackObserver

    log_path = tmp_path / "playback_events.jsonl"
    obs_1 = PlaybackObserver(state_dir=tmp_path)
    obs_2 = PlaybackObserver(state_dir=tmp_path)

    def hammer(obs, n):
        for i in range(n):
            obs._append_events([{"ts": "2026-04-20T00:00:00+00:00", "type": "play", "i": i}])

    t1 = threading.Thread(target=hammer, args=(obs_1, 50))
    t2 = threading.Thread(target=hammer, args=(obs_2, 50))
    t1.start(); t2.start(); t1.join(); t2.join()

    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 100
    import json
    for line in lines:
        json.loads(line)  # não deve levantar
```

- [ ] **Step 2: Verify fail**

Run: `uv run pytest packages/maestra-ai/tests/unit/test_playback.py::test_append_events_usa_lock_e_nao_corrompe_concorrencia -v`
Expected: pode passar por sorte em hardware atual, mas o objetivo é o código. Se passar: ok, foco está em evitar regressão futura. Se falhar: ótimo, justifica o fix.

- [ ] **Step 3: Implementar — substituir loop por `append_jsonl_locked`**

Em `packages/maestra-ai/src/maestra_ai/core/playback.py:130-137`:

```python
def _append_events(self, events: list[dict]) -> None:
    from maestra_ai.core.storage import append_jsonl_locked
    for event in events:
        append_jsonl_locked(self.log_path, event)
```

- [ ] **Step 4: Tests verdes**

Run: `uv run pytest packages/maestra-ai/tests/unit/test_playback.py -v`
Expected: todos passam.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "fix(playback): usar append_jsonl_locked para writes concorrentes (S2)"
```

---

### Task 6: S3 + S9 — validação de topic e schema de rationale

**Files:**
- Modify: `packages/maestra-ai/src/maestra_ai/cli/help.py:10-17`
- Modify: `packages/maestra-mcp/src/maestra_mcp/tools.py:472-493` (`_onboard_rationale`)
- Test: `packages/maestra-ai/tests/unit/test_help_cli.py` (novo caso para topic inválido)
- Test: `packages/maestra-mcp/tests/unit/test_tools.py` (novo caso para rationale corrompido)

- [ ] **Step 1: Failing test — topic com path traversal é rejeitado**

```python
def test_help_rejeita_topic_com_traversal(capsys):
    from maestra_ai.cli import help as help_cli
    import argparse
    args = argparse.Namespace(topic="../cli/__init__")
    rc = help_cli.cmd_help_topic(args)
    assert rc != 0
    out = capsys.readouterr()
    assert "inválido" in (out.out + out.err).lower() or "inválid" in (out.out + out.err).lower()
```

- [ ] **Step 2: Failing test — rationale corrompido retorna UserError claro**

```python
async def test_onboard_rationale_corrompido_retorna_user_error(tmp_path, monkeypatch):
    from maestra_ai.core import storage
    from maestra_mcp import tools as tools_mod

    monkeypatch.setattr(storage, "state_dir", lambda: tmp_path)
    path = tmp_path / "onboard_rationale.json"
    path.write_text("{nope not json", encoding="utf-8")

    result = await tools_mod.call_tool("onboard_rationale", {})
    assert "error" in result
    assert "corromp" in result["error"]["what_happened"].lower()
```

- [ ] **Step 3: Verify fail**

Run: `uv run pytest packages/maestra-ai/tests/unit/test_help_cli.py -k "traversal" -v`
Run: `uv run pytest packages/maestra-mcp/tests/unit/test_tools.py -k "corrompido" -v`
Expected: ambos FAIL.

- [ ] **Step 4: Implementar S3 — regex em help.py**

Em `packages/maestra-ai/src/maestra_ai/cli/help.py`:

```python
import re as _re
_TOPIC_RE = _re.compile(r"^[a-z][a-z0-9_-]*$")

def cmd_help_topic(args):
    topic = args.topic
    if not _TOPIC_RE.fullmatch(topic or ""):
        from maestra_ai.cli._common import error
        return error(f"Tópico inválido: {topic!r}. Use letras minúsculas, dígitos, '-' ou '_'.")
    # resto igual
```

- [ ] **Step 5: Implementar S9 — validar rationale em tools.py**

Em `packages/maestra-mcp/src/maestra_mcp/tools.py` dentro de `_onboard_rationale`:

```python
try:
    data = _json.loads(path.read_text(encoding="utf-8"))
except (OSError, _json.JSONDecodeError) as e:
    from maestra_ai.core.errors import UserError
    raise UserError(
        "Arquivo de rationale do onboard corrompido ou ilegível. "
        "Rode 'maestra onboard' novamente."
    ) from e
if not isinstance(data, dict) or "suggestions" not in data:
    from maestra_ai.core.errors import UserError
    raise UserError("Rationale do onboard em formato inesperado. Rode 'maestra onboard' novamente.")
```

- [ ] **Step 6: Tests verdes**

Run: `uv run pytest packages/ -q`
Expected: todos passam.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "fix: validar topic em help e schema de rationale no MCP (S3, S9)"
```

---

### Task 7: S4 — director.start fecha log_fd no pai

**Files:**
- Modify: `packages/maestra-ai/src/maestra_ai/core/director.py:276-284`

- [ ] **Step 1: Inspecionar código atual**

Confirmar que `log_fd = open(log_path, "a", ...)` é passado a `subprocess.Popen(..., stdout=log_fd, stderr=log_fd, ...)` sem fechamento posterior.

- [ ] **Step 2: Envolver em context manager**

Substituir por:

```python
with open(log_path, "a", encoding="utf-8") as log_fd:
    proc = subprocess.Popen(
        cmd,
        stdout=log_fd,
        stderr=log_fd,
        start_new_session=True,
        env=env,
        cwd=cwd,
    )
```

O `with` fecha o fd do pai após `Popen` já ter duplicado para o filho. Validar visualmente que nenhuma linha posterior ao `with` precise de `log_fd`.

- [ ] **Step 3: Tests verdes**

Run: `uv run pytest packages/maestra-ai/tests/unit/test_director.py -q`
Expected: todos passam. Não há teste direto para fd leak (requer /proc inspection); validação é por leitura de código e manutenção da suite.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "fix(director): fechar log_fd no pai após Popen (S4 fd leak)"
```

---

### Task 8: S5 + S8 — "authorization" em _SECRET_KEYS e timestamp UTC de snapshot

**Files:**
- Modify: `packages/maestra-ai/src/maestra_ai/core/audit.py:20-21`
- Modify: `packages/maestra-ai/src/maestra_ai/core/snapshot.py:41`
- Test: `packages/maestra-ai/tests/unit/test_audit.py` (assert authorization redacted)
- Test: `packages/maestra-ai/tests/unit/test_snapshot.py` (assert id sem offset local)

- [ ] **Step 1: Failing test — authorization redigido**

```python
def test_redact_cobre_key_authorization():
    from maestra_ai.core.audit import _redact
    out = _redact({"headers": {"Authorization": "Bearer abc123"}})
    assert out["headers"]["Authorization"] == "REDACTED"
```

- [ ] **Step 2: Failing test — snapshot timestamp sem offset local**

```python
def test_snapshot_id_usa_utc_sem_astimezone(tmp_path, monkeypatch):
    from maestra_ai.core import snapshot
    monkeypatch.setattr(snapshot.storage, "state_dir", lambda: tmp_path)
    sid = snapshot.create(data={"k": "v"}, kind="test")
    # ID formato: "YYYYMMDDTHHMMSS-<hash>"; não deve ter "-0300" ou "+0000" embedded
    # e deve ser interpretável como UTC lexicograficamente.
    assert sid.count("T") == 1
    # Segundo segmento não deve ser offset
    after_t = sid.split("T", 1)[1]
    # Se o código usasse astimezone().strftime com %z, veríamos dígitos após seg; sem %z, não.
    # Melhor: asserção sobre chamada direta.
    import datetime as dt
    now_utc = dt.datetime.now(dt.UTC)
    prefix = now_utc.strftime("%Y%m%dT%H%M")
    assert sid.startswith(prefix[:10])  # data UTC
```

- [ ] **Step 3: Verify fail**

Run: `uv run pytest -k "authorization" -v`
Run: `uv run pytest -k "snapshot_id_usa_utc" -v`
Expected: ambos FAIL.

- [ ] **Step 4: Implementar S5**

Em `audit.py:20-21`:

```python
_SECRET_KEYS = {"refresh_token", "client_secret", "access_token", "password",
                "token", "email", "authorization"}
```

- [ ] **Step 5: Implementar S8**

Em `snapshot.py:41`, remover `.astimezone()`:

```python
ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
```

- [ ] **Step 6: Tests verdes**

Run: `uv run pytest packages/ -q`
Expected: todos passam.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "fix: redigir 'authorization' e usar UTC puro em snapshot id (S5, S8)"
```

---

### Task 9: D5 — inline de shims em cli/taste.py

**Files:**
- Modify: `packages/maestra-ai/src/maestra_ai/cli/taste.py` — usar `core.taste` direto
- Modify: `packages/maestra-ai/src/maestra_ai/cli/_common.py:123,150` — remover `_prune_candidates` e `_context_review`

- [ ] **Step 1: Verify callers**

```bash
rg "_prune_candidates|_context_review" packages/maestra-ai/src/maestra_ai/cli/
```

Confirmar que só `cli/taste.py` importa.

- [ ] **Step 2: Atualizar `cli/taste.py`**

Substituir `from maestra_ai.cli._common import _prune_candidates, _context_review` (ou equivalente) por:

```python
from maestra_ai.core import taste as taste_mod
```

E nos call sites, trocar `_prune_candidates(...)` → `taste_mod.prune_candidates(...)` e `_context_review(...)` → `taste_mod.review(...)`.

- [ ] **Step 3: Remover shims em `cli/_common.py:123,150`**

Deletar as funções `_prune_candidates` e `_context_review` (~12 LoC).

- [ ] **Step 4: Tests verdes**

Run: `uv run pytest packages/maestra-ai/tests/unit/test_taste_cli.py -q`
Run: `uv run pytest packages/ -q`
Expected: todos passam.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(cli): inline taste shims em cli/taste.py (D5)"
```

---

### Task 10: D7 + D8 — storage keyring cleanup

**Files:**
- Modify: `packages/maestra-ai/src/maestra_ai/core/storage.py:168-203` — remover `_keyring_backend_ok`, `_flag_keyring_used`, `_flag_keyring_used_get`
- Modify: `packages/maestra-ai/src/maestra_ai/cli/doctor.py:108` — usar `token_store._keyring_backend_ok`

- [ ] **Step 1: Verify callers**

```bash
rg "_keyring_backend_ok|_flag_keyring_used" packages/
```

Confirmar:
- `_keyring_backend_ok` em `storage.py` (def) e `doctor.py` (caller) + `token_store.py` (def independente).
- `_flag_keyring_used*` somente em `storage.py`.

- [ ] **Step 2: Trocar caller em `doctor.py:108`**

```python
from maestra_ai.core.token_store import _keyring_backend_ok
# ...usar _keyring_backend_ok() onde antes vinha de storage.
```

- [ ] **Step 3: Remover de `storage.py`**

Deletar `_keyring_backend_ok`, `_flag_keyring_used`, `_flag_keyring_used_get` (~25 LoC).

- [ ] **Step 4: Tests verdes**

Run: `uv run pytest packages/maestra-ai/tests/unit/test_doctor.py -q`
Run: `uv run pytest packages/ -q`
Expected: todos passam.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(storage): consolidar keyring backend check em token_store (D7, D8)"
```

---

### Task 11: D10 — curator usa TasteProfile.filter

**Files:**
- Modify: `packages/maestra-ai/src/maestra_ai/core/curator.py:76-89`

- [ ] **Step 1: Inspecionar loop atual**

Abrir `curator.py:76-89` e identificar o filtro inline que reimplementa `is_rejected` + `get_rejected_artists`.

- [ ] **Step 2: Substituir por `taste.filter` (ou `filter_with_artist_info` se tiver artist_id)**

Se o loop usa só `uri`:

```python
from maestra_ai.core.taste import TasteProfile
profile = TasteProfile.load()
tracks = profile.filter(tracks)  # retorna só os não-rejeitados
```

Se usa artist info:

```python
tracks = profile.filter_with_artist_info(tracks)
```

Escolher baseado no shape dos dicts. Manter comportamento observável idêntico.

- [ ] **Step 3: Tests verdes**

Run: `uv run pytest packages/maestra-ai/tests/unit/test_curator.py -q`
Expected: todos passam.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor(curator): usar TasteProfile.filter em vez de loop inline (D10)"
```

---

### Task 12: D11 + S6 + S10 — hardening menor e documentação

**Files:**
- Modify: `packages/maestra-ai/src/maestra_ai/core/history.py:~249` (`_context_query_candidates`) — simplificar ou docstring "v0.8 rework"
- Modify: `packages/maestra-ai/src/maestra_ai/core/security.py:28-40` — docstring sobre limites JWT (S6)
- Modify: `packages/maestra-ai/src/maestra_ai/core/config.py:12` (`normalize_playlist_id`) — regex ancorada (S10)
- Test: `packages/maestra-ai/tests/unit/test_config.py` — casos para S10

- [ ] **Step 1: Failing test — S10 casos ambíguos**

```python
def test_normalize_playlist_id_rejeita_dois_ids_concatenados():
    from maestra_ai.core.config import normalize_playlist_id
    # Duas IDs com espaço: escolher a primeira explicitamente ou rejeitar.
    # Comportamento atual: retorna a primeira silenciosamente.
    # Desejado: com regex ancorada, só aceita se o input for URL/URI canônica
    # ou um ID isolado.
    sid_a = "aaaaaaaaaaaaaaaaaaaaaa"
    sid_b = "bbbbbbbbbbbbbbbbbbbbbb"
    # URI canônica: ok
    assert normalize_playlist_id(f"spotify:playlist:{sid_a}") == sid_a
    # URL canônica: ok
    assert normalize_playlist_id(f"https://open.spotify.com/playlist/{sid_a}") == sid_a
    # ID isolado: ok
    assert normalize_playlist_id(sid_a) == sid_a
    # Dois IDs concatenados com espaço — comportamento legacy permissivo OK por ora,
    # mas garantimos que pelo menos a primeira é a retornada deterministicamente.
    assert normalize_playlist_id(f"{sid_a} {sid_b}") == sid_a
```

- [ ] **Step 2: Verify baseline**

Run: `uv run pytest packages/maestra-ai/tests/unit/test_config.py -k "normalize_playlist" -v`

O teste acima provavelmente passa com implementação atual (tolerante). Adicionar um teste novo que FALHA:

```python
def test_normalize_playlist_id_preferencia_uri_canonica_quando_presente():
    from maestra_ai.core.config import normalize_playlist_id
    sid = "cccccccccccccccccccccc"
    # Entrada com ID solto + URI canônica: retornar a do padrão canônico.
    mixed = f"xxxxxxxxxxxxxxxxxxxxxx spotify:playlist:{sid}"
    assert normalize_playlist_id(mixed) == sid
```

Expected: FAIL (atual pega o primeiro run de 22 base62).

- [ ] **Step 3: Implementar S10 — regex ancorada com fallback**

Em `packages/maestra-ai/src/maestra_ai/core/config.py`:

```python
_PLAYLIST_CANONICAL_RE = re.compile(
    r"(?:spotify:playlist:|open\.spotify\.com/playlist/)([a-zA-Z0-9]{22})"
)
_PLAYLIST_ID_RE = re.compile(r"[a-zA-Z0-9]{22}")

def normalize_playlist_id(value: str) -> str:
    # Prefere match canônico (URI/URL Spotify)
    canonical = _PLAYLIST_CANONICAL_RE.search(value or "")
    if canonical:
        return canonical.group(1)
    # Fallback permissivo: primeiro run de 22 base62
    fallback = _PLAYLIST_ID_RE.search(value or "")
    if fallback:
        return fallback.group(0)
    raise ValueError(f"ID de playlist não reconhecido: {value!r}")
```

- [ ] **Step 4: Documentar S6 em `security.py`**

Adicionar nota no docstring do módulo:

```python
"""...
Limite conhecido: o matcher JWT cobre o shape canônico ``eyJ...eyJ...`` (header
base64url começando com ``{``). Tokens JWT com headers não-canônicos ou tokens
opacos isolados (sem prefixo Bearer ou known-key) NÃO são redigidos — confie
no boundary de `_SECRET_KEYS` para casos por-chave e no pipeline Bearer para
tokens de acesso Spotify.
"""
```

- [ ] **Step 5: Simplificar D11 (`_context_query_candidates`)**

Em `history.py:~249`, avaliar. Se a função gera heurística estática não calibrada (dois buckets "foco"/"energia"): adicionar docstring explicando o escopo e TODO para v0.8 + simplificar para retornar lista vazia quando não houver evidência estatística suficiente (por ex, quando o taste tem <20 faixas). Mudança conservadora; não quebrar callers.

```python
def _context_query_candidates(genres: dict[str, int]) -> dict:
    """Heurística estática (v0.7): mapeia gêneros em buckets 'foco' e 'energia'.

    Nota: marcado para rework em v0.8 com calibração por TasteProfile.
    Comportamento: retorna {"foco": [...], "energia": [...]} ou dict vazio
    se o sinal for fraco (<3 gêneros distintos).
    """
    if len(genres) < 3:
        return {}
    # ... lógica existente
```

- [ ] **Step 6: Tests verdes**

Run: `uv run pytest packages/ -q`
Expected: todos passam.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "refactor: ancorar normalize_playlist_id, documentar limites JWT, nota v0.8 em context_query (S6, S10, D11)"
```

---

### Task 13: Bump + changelog + tag

**Files:**
- Modify: `packages/maestra-ai/pyproject.toml` — version 0.7.0-alpha.1
- Modify: `packages/maestra-mcp/pyproject.toml` — version 0.7.0-alpha.1
- Modify: `CHANGELOG.md` — seção v0.7.0-alpha.1

- [ ] **Step 1: Bump version em ambos pyproject.toml**

`packages/maestra-ai/pyproject.toml`: `version = "0.7.0-alpha.1"`
`packages/maestra-mcp/pyproject.toml`: `version = "0.7.0-alpha.1"`

- [ ] **Step 2: CHANGELOG**

Adicionar seção no topo:

```markdown
## [0.7.0-alpha.1] — 2026-04-20

### Corrigido
- **CRÍTICO (S1):** MCP boundary redige secrets antes de retornar erros ao cliente (`redact_error_dict` + `redact_str`).
- S2: `PlaybackObserver` usa `append_jsonl_locked` para prevenir intercalação sob concorrência.
- S3: `help <topic>` valida topic com regex âncora (defesa-em-profundidade).
- S4: `director.start` fecha `log_fd` no pai após Popen (elimina fd leak em MCP long-lived).
- S5: chave `authorization` adicionada ao redactor.
- S8: snapshot IDs usam UTC puro (sem `.astimezone()`).
- S9: `onboard_rationale` valida schema antes de usar.
- S10: `normalize_playlist_id` prefere URIs/URLs canônicas do Spotify.

### Removido (dead code)
- `_stub` em `cli/config.py`, `_pid_running` e `_signal_weight` em `cli/_common.py` (shims obsoletos).
- `_prune_candidates_fn` alias em `core/taste.py` (contorno de shadowing substituído por rename).
- `_flag_keyring_used*` em `core/storage.py` (flag file não mais lido).
- `_keyring_backend_ok` duplicado em `core/storage.py` (consolidado em `token_store`).
- Shims `_prune_candidates`/`_context_review` em `cli/_common.py` (inline em `cli/taste.py`).

### Refatorado
- `onboard.py` aplica TypedDicts exportados (`SelectedPlaylist`, `FailedPlaylist`, `OnboardSignals`, `TrackRationale`, `RationaleEntry`).
- `curator.curate` usa `TasteProfile.filter` em vez de loop inline.
- `_context_query_candidates` marcado para rework v0.8 + guard de sinal fraco.

### Lint
- Suíte ruff limpa (26 → 0 erros). Autofix + ajustes manuais.
```

- [ ] **Step 3: Tests finais**

Run: `uv run pytest packages/ -q`
Run: `uv run ruff check packages/`
Expected: 552 passed + ruff limpo.

- [ ] **Step 4: Commit + tag**

```bash
git add -A
git commit -m "chore: bump v0.7.0-alpha.1"
git tag v0.7.0-alpha.1
```

---

## Self-review

**Spec coverage:**
- Dead code: D1 (T4), D2-D4-D6 (T3), D5 (T9), D7-D8 (T10), D10 (T11), D11 (T12), D12-D14 (T2). D9 e D13 = manter (🟢, fora do escopo).
- Segurança: S1 (T1), S2 (T5), S3+S9 (T6), S4 (T7), S5+S8 (T8), S6+S10 (T12). S7 = N/A (key names não são segredo).

**Placeholder scan:** sem TBD/TODO sem código concreto. Todo step de código tem snippet real.

**Type consistency:** TypedDicts importados de `onboard_types` — confere com nomes definidos (SelectedPlaylist, FailedPlaylist, OnboardSignals, TrackRationale, RationaleEntry). `redact_error_dict`/`redact_str` confere com `core/security.py`.

**Notas:**
- Tasks 1, 5, 6, 7, 10 são sensíveis (segurança/fd); priorizar review cuidadoso.
- Tasks 2, 3, 9, 11 são mecânicas (baixo risco).
- Task 4 requer jeito com mypy (TypedDict lit). Se subagent travar, pode deferrer anotação de dict-literal e só anotar os retornos.
