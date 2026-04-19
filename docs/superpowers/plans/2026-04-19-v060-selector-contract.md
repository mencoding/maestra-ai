# v0.6.0-alpha Selector Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Formalizar contrato do `playlist_selector` e do `expansion_info` do onboard com TypedDict, passando `ExpansionContext` (total_cap, current_total, remaining) ao selector. Hard break do contrato antigo (1-arg → 2-arg).

**Architecture:** Tipos centralizados em `core/onboard_types.py` para eliminar imports circulares e permitir consumo por CLI, MCP futuro e agentes externos. Core passa ctx explicitamente ao invocar selector. CLI atualiza selectors internos (`_fixed_selector`, `_interactive_selector`) para aceitar o 2º arg e usa os valores reais no prompt interativo.

**Tech Stack:** Python 3.11+, `typing.TypedDict`, `typing.Literal`, `collections.abc.Callable`. Testes via pytest. uv como build/dep tool. Sem novas dependências externas.

**Spec:** `docs/superpowers/specs/2026-04-19-v060-selector-contract-design.md`.

**Base antes de começar:** v0.5.7 (tag), suite 457 unit + 13 integration + 35 mcp = 505 passed.

---

## File Structure

| Arquivo | Tipo | Responsabilidade |
|---------|------|------------------|
| `packages/maestra-ai/src/maestra_ai/core/onboard_types.py` | **Novo** | 6 TypedDicts + 1 Literal + 1 alias. Zero lógica. |
| `packages/maestra-ai/src/maestra_ai/core/onboard.py` | Modificar | Importa de onboard_types; constrói ctx; passa 2 args ao selector; anota retorno. |
| `packages/maestra-ai/src/maestra_ai/cli/onboard.py` | Modificar | `_fixed_selector` e `_interactive_selector` aceitam ctx; `_interactive_selector` passa ctx["current_total"] e ctx["total_cap"] ao prompt. |
| `packages/maestra-ai/tests/unit/test_onboard.py` | Modificar | Todos os selectors inline viram 2-arg. Nova classe TestExpansionContextShape. Regressão hard break. |
| `packages/maestra-ai/tests/unit/test_cli_onboard.py` | Modificar | `_patch_questionary` e selectors fake viram 2-arg. Novo teste TestPromptUsaCtxReal. |
| `packages/maestra-ai/pyproject.toml` | Modificar | Bump 0.5.7 → 0.6.0a0. |
| `packages/maestra-mcp/pyproject.toml` | Modificar | Bump 0.5.7 → 0.6.0a0 + pin do maestra-ai. |
| `CHANGELOG.md` | Modificar | Seção [0.6.0-alpha.0]. |
| `README.md` | Modificar | Status pre-alpha (v0.6.0-alpha). |

---

## Task 1: Criar `onboard_types.py`

**Files:**
- Create: `packages/maestra-ai/src/maestra_ai/core/onboard_types.py`

- [ ] **Step 1: Escrever o módulo com os TypedDicts**

Conteúdo completo do arquivo:

```python
"""Tipos compartilhados do fluxo de onboard (v0.6.0).

Mantidos fora de `onboard.py` para poderem ser importados por:
- Core (`onboard.py`) sem import circular
- CLI (`cli/onboard.py`) para anotações de selector
- MCP futuro (expor onboard como tool)
- Agentes externos consumindo via stubs
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Literal, TypedDict


class OwnPlaylist(TypedDict):
    """Uma playlist própria oferecida ao selector durante a expansão."""

    id: str
    name: str
    track_count: int


class ExpansionContext(TypedDict):
    """Contexto passado ao selector durante a expansão.

    - total_cap: teto desejado de faixas únicas (default 5000).
    - current_total: faixas únicas já coletadas antes da expansão
      (top_long + top_medium + top_short + saved + recent).
    - remaining: total_cap - current_total. Já calculado para evitar
      que cada selector recompute.
    """

    total_cap: int
    current_total: int
    remaining: int


class SelectedPlaylist(TypedDict):
    id: str
    name: str


class FailedPlaylist(TypedDict):
    id: str
    reason: str  # truncado em 80 chars


ExpansionReason = Literal[
    "ok",
    "selector_not_provided",
    "cap_already_reached",
    "no_own_playlists",
    "only_empty_playlists",
    "selector_returned_empty",
]


class ExpansionInfo(TypedDict):
    attempted: bool
    reason: ExpansionReason
    offered_playlists: int
    own_playlists_empty_count: int
    selected_playlists: list[SelectedPlaylist]
    tracks_added: int
    failed_playlists: list[FailedPlaylist]


# Type alias exportado para anotações.
PlaylistSelector = Callable[[list[OwnPlaylist], ExpansionContext], list[str]]
```

- [ ] **Step 2: Validar que o módulo importa sem erro**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai/packages/maestra-ai && uv run python -c "from maestra_ai.core.onboard_types import ExpansionContext, ExpansionInfo, PlaylistSelector; print('ok')"`
Expected: imprime `ok`.

- [ ] **Step 3: Commit**

```bash
cd /home/menzani/Desenvolvimento/maestra-ai
git add packages/maestra-ai/src/maestra_ai/core/onboard_types.py
git commit -m "feat(onboard): criar onboard_types com TypedDicts (v0.6.0-alpha)

TypedDicts centralizados para OwnPlaylist, ExpansionContext,
SelectedPlaylist, FailedPlaylist, ExpansionReason (Literal), ExpansionInfo.
Type alias PlaylistSelector = Callable[[list[OwnPlaylist],
ExpansionContext], list[str]] (assinatura nova — 2 args).

Ainda não consumido — tasks seguintes vão refatorar core + CLI + tests."
```

---

## Task 2: Assinatura do selector em `core/onboard.py` aceita ctx

**Files:**
- Modify: `packages/maestra-ai/src/maestra_ai/core/onboard.py`

- [ ] **Step 1: Adicionar import de onboard_types**

Abrir `packages/maestra-ai/src/maestra_ai/core/onboard.py`, achar a linha `from maestra_ai.core import storage` e logo abaixo, antes do `from maestra_ai.core.errors import PlaylistCreateForbiddenError`, adicionar:

```python
from maestra_ai.core.onboard_types import (
    ExpansionContext,
    ExpansionInfo,
    FailedPlaylist,
    OwnPlaylist,
    SelectedPlaylist,
)
```

- [ ] **Step 2: Anotar retorno de `_fetch_own_playlists`**

Achar a assinatura atual:

```python
def _fetch_own_playlists(
    sp, me_id: str, *, progress_cb: Callable | None = None,
) -> tuple[list[dict], int]:
```

Substituir o tipo de retorno:

```python
def _fetch_own_playlists(
    sp, me_id: str, *, progress_cb: Callable | None = None,
) -> tuple[list[OwnPlaylist], int]:
```

Nenhuma mudança no corpo — os dicts já têm a shape certa (`id`, `name`, `track_count`).

- [ ] **Step 3: Construir ctx e passar ao selector**

Achar o bloco dentro de `run()` que invoca o selector (em torno da linha que diz `selected_ids = playlist_selector(own_playlists) or []`):

```python
        else:
            selected_ids = playlist_selector(own_playlists) or []
```

Substituir por:

```python
        else:
            ctx: ExpansionContext = {
                "total_cap": total_cap,
                "current_total": current_total_unique,
                "remaining": total_cap - current_total_unique,
            }
            selected_ids = playlist_selector(own_playlists, ctx) or []
```

- [ ] **Step 4: Anotar `expansion_info` como ExpansionInfo**

Achar a declaração do dict (em torno da linha `expansion_info: dict = {`):

```python
    expansion_info: dict = {
        "attempted": False,
        ...
    }
```

Trocar o tipo:

```python
    expansion_info: ExpansionInfo = {
        "attempted": False,
        ...
    }
```

- [ ] **Step 5: Rodar testes para confirmar quebra esperada**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai/packages/maestra-ai && uv run pytest tests/unit/test_onboard.py 2>&1 | tail -5`
Expected: múltiplos `TypeError: <lambda>() takes 1 positional argument but 2 were given` — confirma que o hard break está ativo. Tasks 4 e 5 vão atualizar os testes.

- [ ] **Step 6: Commit (intermediário, core já rodando)**

```bash
cd /home/menzani/Desenvolvimento/maestra-ai
git add packages/maestra-ai/src/maestra_ai/core/onboard.py
git commit -m "feat(onboard): core passa ExpansionContext ao selector (breaking)

run() agora monta ctx com total_cap/current_total/remaining e chama
playlist_selector(own_playlists, ctx). Assinatura antiga (1-arg)
levanta TypeError.

_fetch_own_playlists retorna tuple[list[OwnPlaylist], int] com tipo
formal. expansion_info anotado como ExpansionInfo.

Testes ainda não atualizados — próximas tasks corrigem."
```

---

## Task 3: CLI — `_fixed_selector` e `_interactive_selector` aceitam ctx

**Files:**
- Modify: `packages/maestra-ai/src/maestra_ai/cli/onboard.py`

- [ ] **Step 1: Atualizar `_fixed_selector` em `_build_playlist_selector`**

Achar:

```python
        def _fixed_selector(_playlists):
            return ids
```

Trocar por:

```python
        def _fixed_selector(_playlists, _ctx):
            return ids
```

- [ ] **Step 2: Atualizar `_interactive_selector` para aceitar e usar ctx**

Achar a assinatura atual de `_interactive_selector`:

```python
    def _interactive_selector(playlists):
        ...
```

Substituir por:

```python
    def _interactive_selector(playlists, ctx):
        ...
```

E dentro do corpo, achar:

```python
            try:
                confirm = _prompt_expansion_confirm(total_cap=total_cap)
            except KeyboardInterrupt:
                return []
```

Substituir por:

```python
            try:
                confirm = _prompt_expansion_confirm(
                    current_total=ctx["current_total"],
                    total_cap=ctx["total_cap"],
                )
            except KeyboardInterrupt:
                return []
```

A variável `total_cap = getattr(args, "total_cap", 5000)` no escopo de `_build_playlist_selector` pode ficar — vira redundante mas não quebra. Opcionalmente remover:

```python
    total_cap = getattr(args, "total_cap", 5000)
```

Remover essa linha — agora vem do ctx.

- [ ] **Step 3: Rodar smoke dos testes do CLI onboard**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai/packages/maestra-ai && uv run pytest tests/unit/test_cli_onboard.py 2>&1 | tail -5`
Expected: falhas em TestPlaylistSelector e TestInteractiveSelectorFluxoReal (selectors fake dos testes ainda são 1-arg OU patch de `_prompt_expansion_confirm` espera kwargs diferentes). A task 5 corrige.

- [ ] **Step 4: Commit**

```bash
cd /home/menzani/Desenvolvimento/maestra-ai
git add packages/maestra-ai/src/maestra_ai/cli/onboard.py
git commit -m "feat(cli/onboard): selectors internos aceitam ExpansionContext

_fixed_selector ignora ctx (ids são pré-setados via --expand-playlists).
_interactive_selector usa ctx[current_total] e ctx[total_cap] para o
prompt dinâmico — antes passava 0 porque CLI não sabia o total real.

Próximas tasks atualizam testes."
```

---

## Task 4: Atualizar selectors nos testes de core (`test_onboard.py`)

**Files:**
- Modify: `packages/maestra-ai/tests/unit/test_onboard.py`

Os selectors nos testes de `TestPlaylistExpansion` e `TestExpansionEdgeCases` estão escritos como `lambda pls: [...]` ou funções `def selector(pls)`. Todos viram 2-arg.

- [ ] **Step 1: Atualizar `TestPlaylistExpansion.test_expansao_sem_playlists_proprias_reporta_motivo`**

Achar:

```python
        def selector(pls):
            selector_called["yes"] = True
            return []
```

Trocar por:

```python
        def selector(pls, ctx):
            selector_called["yes"] = True
            return []
```

- [ ] **Step 2: Atualizar `TestPlaylistExpansion.test_expansao_com_selecao_adiciona_faixas_com_peso_2`**

Achar:

```python
        def selector(pls):
            # agente escolhe só a primeira
            return ["p1"]
```

Trocar por:

```python
        def selector(pls, ctx):
            # agente escolhe só a primeira
            return ["p1"]
```

- [ ] **Step 3: Atualizar `TestPlaylistExpansion.test_expansao_respeita_total_cap`**

Achar:

```python
        def selector(pls):
            return ["p1"]
```

Trocar por:

```python
        def selector(pls, ctx):
            return ["p1"]
```

- [ ] **Step 4: Atualizar `TestPlaylistExpansion.test_falha_em_uma_playlist_registra_em_failed_playlists`**

Achar:

```python
        def selector(pls):
            return ["p1", "p2", "p3"]
```

Trocar por:

```python
        def selector(pls, ctx):
            return ["p1", "p2", "p3"]
```

- [ ] **Step 5: Atualizar lambdas em `TestReasonCapAlreadyReached` e `TestReasonOk`**

Achar todas as ocorrências de `playlist_selector=lambda pls:` dentro de `TestPlaylistExpansion`:

```bash
cd /home/menzani/Desenvolvimento/maestra-ai/packages/maestra-ai
grep -n "lambda pls:" tests/unit/test_onboard.py
```

Para cada linha retornada, substituir `lambda pls:` por `lambda pls, ctx:`. Esperado: 3–5 ocorrências em `test_reason_cap_already_reached_quando_total_ja_cobre`, `test_reason_ok_no_caminho_feliz`, `test_reason_selector_returned_empty`, `test_reason_only_empty_playlists_quando_todas_vazias`.

Também em `TestExpansionEdgeCases`:

```python
        def buggy_selector(_pls):
            raise ValueError("selector com bug")
```

Trocar por:

```python
        def buggy_selector(_pls, _ctx):
            raise ValueError("selector com bug")
```

E:

```python
        def selector(_pls):
            return ["id_que_nao_esta_na_lista"]
```

Trocar por:

```python
        def selector(_pls, _ctx):
            return ["id_que_nao_esta_na_lista"]
```

- [ ] **Step 6: Rodar os testes atualizados**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai/packages/maestra-ai && uv run pytest tests/unit/test_onboard.py -v 2>&1 | tail -10`
Expected: todos os testes de `TestPlaylistExpansion` e `TestExpansionEdgeCases` passando. Nenhum `TypeError: takes 1 positional argument`.

- [ ] **Step 7: Commit**

```bash
cd /home/menzani/Desenvolvimento/maestra-ai
git add packages/maestra-ai/tests/unit/test_onboard.py
git commit -m "test(onboard): selectors 2-arg em TestPlaylistExpansion + TestExpansionEdgeCases

Todos os selectors inline (lambda pls e def selector(pls)) agora
aceitam (pls, ctx) — contrato v0.6.0. Corpo do selector pode ignorar
ctx, mas a assinatura é obrigatória."
```

---

## Task 5: Atualizar selectors em `test_cli_onboard.py`

**Files:**
- Modify: `packages/maestra-ai/tests/unit/test_cli_onboard.py`

- [ ] **Step 1: Atualizar `TestPlaylistSelector.test_expand_playlists_fixo_retorna_ids`**

Achar:

```python
        ids = sel([{"id": "xxx", "name": "Ignorada", "track_count": 5}])
```

O segundo arg é o ctx. Mesmo que o `_fixed_selector` ignore, o teste deve passar ambos os args:

```python
        ids = sel(
            [{"id": "xxx", "name": "Ignorada", "track_count": 5}],
            {"total_cap": 5000, "current_total": 100, "remaining": 4900},
        )
```

- [ ] **Step 2: Aplicar o mesmo ajuste em `test_expand_playlists_aceita_url_e_uri`**

Achar:

```python
        ids = sel([])
```

Trocar por:

```python
        ids = sel([], {"total_cap": 5000, "current_total": 0, "remaining": 5000})
```

- [ ] **Step 3: Atualizar `TestPlaylistSelector.test_keyboard_interrupt_*`**

Ambos os métodos (`test_keyboard_interrupt_no_confirm_degrada_para_lista_vazia` e `test_keyboard_interrupt_no_checkbox_degrada_para_lista_vazia`) têm:

```python
        result = sel([{"id": "p1", "name": "A", "track_count": 10}])
```

Trocar (nos dois) por:

```python
        result = sel(
            [{"id": "p1", "name": "A", "track_count": 10}],
            {"total_cap": 5000, "current_total": 100, "remaining": 4900},
        )
```

- [ ] **Step 4: Atualizar `TestInteractiveSelectorFluxoReal` — 4 métodos**

Cada método chama `sel(playlists)` ou `sel([])`. Todos viram 2-arg. Para:
- `test_confirma_e_escolhe_dois_ids`: `sel(playlists)` → `sel(playlists, {"total_cap": 5000, "current_total": 500, "remaining": 4500})`
- `test_confirm_negado_retorna_vazio`: idem
- `test_checkbox_nenhum_marcado_retorna_vazio`: idem
- `test_lista_vazia_retorna_sem_imprimir`: `sel([])` → `sel([], {"total_cap": 5000, "current_total": 0, "remaining": 5000})`

- [ ] **Step 5: Rodar testes do CLI**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai/packages/maestra-ai && uv run pytest tests/unit/test_cli_onboard.py 2>&1 | tail -5`
Expected: todos os testes passando.

- [ ] **Step 6: Commit**

```bash
cd /home/menzani/Desenvolvimento/maestra-ai
git add packages/maestra-ai/tests/unit/test_cli_onboard.py
git commit -m "test(cli/onboard): selectors nos testes chamam com ctx explícito

Todos os sel(...) dos testes de TestPlaylistSelector e
TestInteractiveSelectorFluxoReal agora passam ExpansionContext como
2º arg (mesmo que o _fixed_selector ignore)."
```

---

## Task 6: Novo teste — `TestExpansionContextShape`

**Files:**
- Modify: `packages/maestra-ai/tests/unit/test_onboard.py`

- [ ] **Step 1: Adicionar nova classe de testes (após `TestPlaylistExpansion`)**

Achar o final da classe `TestPlaylistExpansion` (última método). Adicionar logo depois:

```python
class TestExpansionContextShape:
    """v0.6.0: core constrói ExpansionContext corretamente e passa ao
    selector. Contrato novo (2-arg), hard break do antigo."""

    def test_ctx_tem_total_cap_igual_ao_configurado(self, tmp_path, monkeypatch):
        from maestra_ai.core.taste import TasteProfile
        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))

        sp = TestPlaylistExpansion()._sp_with_playlists(
            own_playlists=[
                {"id": "p1", "name": "A", "owner": {"id": "me"},
                 "tracks": {"total": 3}},
            ],
        )
        captured = {}

        def spy_selector(pls, ctx):
            captured["ctx"] = dict(ctx)
            return []

        taste = TasteProfile(tmp_path / "taste.json")
        onboard.run(
            sp, taste, playlist_name="M", seed_count=0,
            playlist_selector=spy_selector, total_cap=777,
        )
        assert captured["ctx"]["total_cap"] == 777

    def test_ctx_current_total_eh_uniao_de_fontes(self, tmp_path, monkeypatch):
        """current_total = |top_long + top_medium + top_short + saved + recent|."""
        from maestra_ai.core.taste import TasteProfile
        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))

        # _make_sp(top_long=10, top_medium=10, top_short=10, recent=5, saved=0)
        # produz 35 URIs únicos (prefixos distintos).
        sp = TestPlaylistExpansion()._sp_with_playlists(
            own_playlists=[
                {"id": "p1", "name": "A", "owner": {"id": "me"},
                 "tracks": {"total": 3}},
            ],
        )
        captured = {}

        def spy_selector(pls, ctx):
            captured["ctx"] = dict(ctx)
            return []

        taste = TasteProfile(tmp_path / "taste.json")
        onboard.run(
            sp, taste, playlist_name="M", seed_count=0,
            playlist_selector=spy_selector, total_cap=5000,
        )
        assert captured["ctx"]["current_total"] == 35

    def test_ctx_remaining_eh_diferenca(self, tmp_path, monkeypatch):
        from maestra_ai.core.taste import TasteProfile
        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))

        sp = TestPlaylistExpansion()._sp_with_playlists(
            own_playlists=[
                {"id": "p1", "name": "A", "owner": {"id": "me"},
                 "tracks": {"total": 3}},
            ],
        )
        captured = {}

        def spy_selector(pls, ctx):
            captured["ctx"] = dict(ctx)
            return []

        taste = TasteProfile(tmp_path / "taste.json")
        onboard.run(
            sp, taste, playlist_name="M", seed_count=0,
            playlist_selector=spy_selector, total_cap=100,
        )
        # current_total=35, total_cap=100 → remaining=65
        assert captured["ctx"]["remaining"] == 65
```

- [ ] **Step 2: Rodar a nova classe**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai/packages/maestra-ai && uv run pytest tests/unit/test_onboard.py::TestExpansionContextShape -v 2>&1 | tail -8`
Expected: 3 tests PASSED.

- [ ] **Step 3: Commit**

```bash
cd /home/menzani/Desenvolvimento/maestra-ai
git add packages/maestra-ai/tests/unit/test_onboard.py
git commit -m "test: TestExpansionContextShape valida construção do ctx (v0.6.0)

Três casos:
- ctx.total_cap bate com o configurado em run()
- ctx.current_total = |união das fontes de faixas| antes da expansão
- ctx.remaining = total_cap - current_total"
```

---

## Task 7: Novo teste — `TestPromptUsaCtxReal`

**Files:**
- Modify: `packages/maestra-ai/tests/unit/test_cli_onboard.py`

- [ ] **Step 1: Adicionar nova classe de testes (após `TestPromptExpansionConfirmDinamico`)**

```python
class TestPromptUsaCtxReal:
    """v0.6.0: _interactive_selector passa ctx[current_total] e
    ctx[total_cap] ao prompt — antes passava 0 porque CLI não tinha
    como saber o total real."""

    def test_prompt_recebe_current_total_do_ctx(self, monkeypatch):
        captured = {}

        def fake_confirm(current_total=0, total_cap=5000):
            captured["current_total"] = current_total
            captured["total_cap"] = total_cap
            return False  # dispensa a expansão

        monkeypatch.setattr(
            cli_onboard, "_prompt_expansion_confirm", fake_confirm,
        )
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)

        args = _ns(non_interactive=False, total_cap=1200)
        sel = cli_onboard._build_playlist_selector(args, progress=None)

        playlists = [{"id": "p1", "name": "A", "track_count": 10}]
        ctx = {"total_cap": 1200, "current_total": 700, "remaining": 500}
        sel(playlists, ctx)

        assert captured["current_total"] == 700
        assert captured["total_cap"] == 1200
```

- [ ] **Step 2: Rodar o teste**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai/packages/maestra-ai && uv run pytest tests/unit/test_cli_onboard.py::TestPromptUsaCtxReal -v 2>&1 | tail -6`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
cd /home/menzani/Desenvolvimento/maestra-ai
git add packages/maestra-ai/tests/unit/test_cli_onboard.py
git commit -m "test: TestPromptUsaCtxReal valida que prompt usa ctx real (v0.6.0)

_interactive_selector agora recebe ctx do core e passa current_total
e total_cap ao _prompt_expansion_confirm. Antes current_total era
hard-coded 0 porque CLI não tinha como saber o total."
```

---

## Task 8: Teste de regressão do hard break

**Files:**
- Modify: `packages/maestra-ai/tests/unit/test_onboard.py`

- [ ] **Step 1: Adicionar teste de regressão (no final de `TestExpansionContextShape`)**

No final da classe `TestExpansionContextShape`, adicionar:

```python
    def test_selector_com_assinatura_antiga_1arg_levanta_type_error(
        self, tmp_path, monkeypatch,
    ):
        """v0.6.0 hard break: selector com assinatura antiga (1 arg)
        levanta TypeError quando core o chama com 2 args. Confirma
        que a quebra é intencional e observável."""
        import pytest

        from maestra_ai.core.taste import TasteProfile
        monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))

        sp = TestPlaylistExpansion()._sp_with_playlists(
            own_playlists=[
                {"id": "p1", "name": "A", "owner": {"id": "me"},
                 "tracks": {"total": 3}},
            ],
        )

        # Assinatura antiga — só 1 arg.
        old_selector = lambda pls: []  # noqa: E731

        taste = TasteProfile(tmp_path / "taste.json")
        with pytest.raises(TypeError, match="positional argument"):
            onboard.run(
                sp, taste, playlist_name="M", seed_count=0,
                playlist_selector=old_selector,
            )
```

- [ ] **Step 2: Rodar o teste**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai/packages/maestra-ai && uv run pytest tests/unit/test_onboard.py::TestExpansionContextShape::test_selector_com_assinatura_antiga_1arg_levanta_type_error -v 2>&1 | tail -6`
Expected: PASS (o TypeError é levantado conforme esperado).

- [ ] **Step 3: Commit**

```bash
cd /home/menzani/Desenvolvimento/maestra-ai
git add packages/maestra-ai/tests/unit/test_onboard.py
git commit -m "test: regressão do hard break — selector 1-arg levanta TypeError

Garante que quebra do contrato antigo é intencional e observável:
pytest.raises(TypeError) com lambda pls: []. Previne que alguém
'conserte' o erro com try/except silencioso no futuro."
```

---

## Task 9: Validação global + bump v0.6.0-alpha.0

**Files:**
- Modify: `packages/maestra-ai/pyproject.toml`
- Modify: `packages/maestra-mcp/pyproject.toml`
- Modify: `README.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Rodar suite inteira (unit + integration do maestra-ai)**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai/packages/maestra-ai && uv run pytest tests/unit/ tests/integration/ 2>&1 | tail -3`
Expected: ~510 passed (era 470 antes; +3 em TestExpansionContextShape, +1 regressão hard break, +1 TestPromptUsaCtxReal).

- [ ] **Step 2: Rodar suite do maestra-mcp**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai/packages/maestra-mcp && uv run pytest tests/ 2>&1 | tail -3`
Expected: 35 passed.

- [ ] **Step 3: Bump versão em `packages/maestra-ai/pyproject.toml`**

Achar `version = "0.5.7"` e trocar por `version = "0.6.0a0"` (PEP 440 pré-release).

- [ ] **Step 4: Bump versão em `packages/maestra-mcp/pyproject.toml`**

Achar `version = "0.5.7"` e trocar por `version = "0.6.0a0"`.

Achar também `"maestra-ai==0.5.7"` (na lista de dependencies) e trocar por `"maestra-ai==0.6.0a0"`.

- [ ] **Step 5: Atualizar status no README**

Achar:

```markdown
**Status:** pre-alpha (v0.5.7). Lançamento público planejado em v1.0.0.
```

Trocar por:

```markdown
**Status:** pre-alpha (v0.6.0-alpha). Lançamento público planejado em v1.0.0.
```

- [ ] **Step 6: Adicionar entrada no CHANGELOG.md**

Abrir `CHANGELOG.md` e logo após `## [Unreleased]` e antes de `## [0.5.7] - 2026-04-19`, adicionar:

```markdown
## [0.6.0-alpha.0] - 2026-04-19

Primeiro bump de minor desde v0.5.0. Formaliza contrato do
`playlist_selector` e do `expansion_info` do onboard via TypedDict.
**Hard break** do contrato antigo (1-arg → 2-arg) — pre-1.0, 1 caller
interno, zero agentes externos conhecidos. Sub-projeto A do backlog
consolidado (itens #27, #29). Suite: ~510 (maestra-ai).

### Breaking
- `playlist_selector` agora é
  `Callable[[list[OwnPlaylist], ExpansionContext], list[str]]` — 2
  argumentos. Selectors antigos com 1 argumento levantam `TypeError`
  em runtime. Sem deprecation path.

### Added
- **`core/onboard_types.py`** com `OwnPlaylist`, `ExpansionContext`,
  `SelectedPlaylist`, `FailedPlaylist`, `ExpansionReason`,
  `ExpansionInfo`, `PlaylistSelector`. Contratos centralizados para
  consumo por core, CLI, MCP futuro e agentes externos via stubs.
- **`ExpansionContext` passado ao selector** — `total_cap`,
  `current_total`, `remaining`. Selector programático não precisa
  mais descobrir esses valores fora de banda.
- **Prompt interativo mostra current_total real**: antes caía em 0
  porque CLI não tinha como saber; agora `_interactive_selector` usa
  `ctx["current_total"]`.

### Changed
- `_fixed_selector` e `_interactive_selector` em `cli/onboard.py`
  aceitam `(playlists, ctx)`. `_fixed_selector` ignora `ctx`
  (IDs fixos via `--expand-playlists`).
- `expansion_info` formalmente anotado como `ExpansionInfo`. Estrutura
  runtime inalterada (flat, 7 campos).
- `_fetch_own_playlists` retorna `tuple[list[OwnPlaylist], int]` com
  tipo formal.

### Tests
- +3 em `TestExpansionContextShape` (total_cap, current_total, remaining).
- +1 regressão de hard break (selector 1-arg → TypeError).
- +1 em `TestPromptUsaCtxReal` (prompt recebe valores do ctx).
- 23+ testes existentes atualizados para assinatura 2-arg (mesma
  contagem).
```

- [ ] **Step 7: Re-sync workspace**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai && uv sync --all-extras 2>&1 | tail -3`
Expected: `maestra-ai==0.6.0a0` e `maestra-mcp==0.6.0a0` instalados.

- [ ] **Step 8: Validação final da suite após bump**

Run: `cd /home/menzani/Desenvolvimento/maestra-ai/packages/maestra-ai && uv run pytest tests/unit/ tests/integration/ 2>&1 | tail -3 && cd ../maestra-mcp && uv run pytest tests/ 2>&1 | tail -3`
Expected: ~510 (maestra-ai) + 35 (maestra-mcp) = ~545 passed.

- [ ] **Step 9: Commit + tag**

```bash
cd /home/menzani/Desenvolvimento/maestra-ai
git add -A
git commit -m "chore: bump v0.6.0-alpha.0 — contrato do selector (sub-projeto A)

Fecha itens #27 (ExpansionContext) e #29 (expansion_info tipado) do
backlog consolidado. Primeiro bump de minor desde v0.5.0. Contrato
novo e hard break do antigo (ver CHANGELOG).

Sub-projeto B (sugestões inteligentes / B3) fica para ciclo próprio
de brainstorming + plan + implementação."
git tag -a v0.6.0-alpha.0 -m "v0.6.0-alpha.0 — contrato formal do selector"
```

- [ ] **Step 10: Atualizar backlog consolidado marcando #27 e #29 como fechados**

Abrir `docs/reviews/2026-04-19-backlog-consolidado.md`, achar a seção "Ordem de execução — status", e trocar:

```markdown
**v0.6.0-alpha (pendente):** 27, 28, 29 (quebra de contrato do selector + refactor de expansion_info) + B3 fora-de-escopo (sugestões inteligentes).

Itens fechados: 25 de 29 (+ 1 descartado). Pendentes: 3 de design + 1 fora-de-escopo.
```

Por:

```markdown
**v0.6.0-alpha.0 ✅ (2026-04-19):** itens 27 e 29 fechados. Item 28 já tinha sido fechado em v0.5.6 (rename de reason vocabulário).
**v0.6.x+ pendente:** B3 — sugestões inteligentes (brainstorming próprio).

Itens fechados: 28 de 29 (+ 1 descartado). Pendente: B3 (fora do backlog original, planejado para v0.6.1 após brainstorming).
```

Commit adicional:

```bash
cd /home/menzani/Desenvolvimento/maestra-ai
git add docs/reviews/2026-04-19-backlog-consolidado.md
git commit -m "docs: marcar itens 27+29 como fechados em v0.6.0-alpha.0"
```

---

## Self-Review do plano

### Spec coverage

Cada seção do spec tem task correspondente:

- Spec §3.1 (tipos): Task 1.
- Spec §3.2 (nova assinatura) + §3.5 (hard break): Task 2 (core), Task 8 (teste regressão).
- Spec §3.3 (core chama com ctx): Task 2.
- Spec §3.4 (CLI atualiza selectors): Task 3.
- Spec §4 (arquivos afetados): Tasks 1, 2, 3, 4, 5, 9.
- Spec §5 tests TDD: TestExpansionContextShape → Task 6; TestPromptUsaCtxReal → Task 7; Regressão → Task 8; atualização dos 23+ existentes → Tasks 4 e 5.
- Spec §6 critérios de aceite: Task 9 (validação de suite + bump).

Nenhum gap identificado.

### Placeholder scan

Nenhum "TBD", "fill in details" ou "Similar to Task N" no plano. Todos os code blocks têm código concreto. Todos os comandos mostram cwd e saída esperada.

### Type consistency

- `OwnPlaylist`, `ExpansionContext`, `SelectedPlaylist`, `FailedPlaylist`, `ExpansionReason`, `ExpansionInfo`, `PlaylistSelector` definidos em Task 1 e referenciados em Tasks 2, 4, 5, 6, 7 com os mesmos nomes.
- Campos do `ExpansionContext` (`total_cap`, `current_total`, `remaining`) consistentes em Task 2 (construção), 3 (CLI lê), 6 (asserts), 7 (asserts).
- Assinatura `(playlists, ctx)` aparece idêntica em todas as atualizações (Tasks 3, 4, 5).
