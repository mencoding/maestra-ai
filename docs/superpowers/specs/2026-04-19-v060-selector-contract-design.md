# Design — v0.6.0-alpha: Contrato do Selector

**Data:** 2026-04-19
**Versão alvo:** v0.6.0-alpha
**Itens do backlog consolidado:** #27 (ExpansionContext), #29 (refactor expansion_info)
**Escopo:** confinado a `core/onboard.py` + `cli/onboard.py` + tests. Nenhuma mudança em client, taste, storage, MCP.

---

## 1. Objetivo

Formalizar o contrato do `playlist_selector` e do `expansion_info` do onboard
com tipos `TypedDict`, passando contexto rico ao selector. Fazer hard break
do contrato antigo — pre-1.0, apenas um caller interno, zero agentes externos
conhecidos.

## 2. Contexto atual (v0.5.7)

```python
# Assinatura atual
PlaylistSelector = Callable[[list[dict]], list[str]]

# Selector recebe só a lista de playlists, não sabe:
# - qual total_cap foi configurado
# - quantas faixas já foram coletadas antes da expansão
# - quantas ainda podem ser adicionadas
```

Consequência: `_prompt_expansion_confirm` (v0.5.5 #9) já aceita `current_total`
mas o `_interactive_selector` sempre passa `0` porque o CLI não tem como saber
o valor real — só o core sabe. O selector é invocado "às cegas".

`expansion_info` é dict plano com 7 campos heterogêneos. Nenhuma checagem
estática; consumidores dependem de docstring e leitura de código.

## 3. Design

### 3.1 Novos tipos (`core/onboard_types.py`)

Arquivo novo para evitar import circular e permitir consumo por CLI, MCP
futuro e agentes externos via stubs.

```python
"""Tipos compartilhados do fluxo de onboard (v0.6.0)."""
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


# Type alias exportado para uso em anotações de funções que aceitam selector.
PlaylistSelector = Callable[[list[OwnPlaylist], ExpansionContext], list[str]]
```

Import necessário: `from collections.abc import Callable` no topo do arquivo.

### 3.2 Nova assinatura do selector

```python
# Antes (v0.5.x):
PlaylistSelector = Callable[[list[dict]], list[str]]

# Depois (v0.6.0):
PlaylistSelector = Callable[[list[OwnPlaylist], ExpansionContext], list[str]]
```

### 3.3 Core — chamada do selector

Em `core/onboard.run()`:

```python
ctx: ExpansionContext = {
    "total_cap": total_cap,
    "current_total": current_total_unique,
    "remaining": total_cap - current_total_unique,
}
selected_ids = playlist_selector(own_playlists, ctx) or []
```

### 3.4 CLI — atualização dos selectors internos

```python
# _fixed_selector: ignora ctx (IDs são fixos do --expand-playlists)
def _fixed_selector(_playlists, _ctx):
    return ids

# _interactive_selector: usa ctx.current_total para prompt dinâmico real
def _interactive_selector(playlists, ctx):
    if not playlists:
        return []
    if progress is not None:
        progress.stop()
    try:
        try:
            confirm = _prompt_expansion_confirm(
                current_total=ctx["current_total"],
                total_cap=ctx["total_cap"],
            )
        except KeyboardInterrupt:
            return []
        if not confirm:
            return []
        try:
            return _prompt_playlists_checkbox(playlists)
        except KeyboardInterrupt:
            return []
    finally:
        if progress is not None:
            progress.start()
```

**Ganho concreto:** o prompt agora mostra valores reais. Usuário com 700
faixas e `--total-cap=1000` vê: *"Sua amostra inicial tem 700 faixas,
abaixo do teto de 1000 (restam 300 para completar). Quer expandir com
suas próprias playlists?"*

### 3.5 Hard break — sem backward compat

Selectors com assinatura antiga (1 arg) levantam `TypeError` em runtime
quando o core os chama com 2 args. **Esse é o comportamento desejado**:
versão alpha em monorepo local, único caller interno, zero ecossistema
protegido. Qualquer agente externo adotará a v0.6.0 já no contrato novo.

## 4. Arquivos afetados

| Arquivo | Tipo | Mudança |
|---------|------|---------|
| `core/onboard_types.py` | **Novo** | TypedDicts + Literal |
| `core/onboard.py` | Refactor | Import de tipos; assinatura do selector muda; ctx passado na chamada; anotações em variáveis |
| `cli/onboard.py` | Refactor | `_fixed_selector` e `_interactive_selector` aceitam ctx; `_prompt_expansion_confirm` recebe valores reais |
| `tests/unit/test_onboard.py` | Ajuste | Todos os `lambda pls: [...]` viram `lambda pls, ctx: [...]`; novos casos validam ctx |
| `tests/unit/test_cli_onboard.py` | Ajuste | Mesmo ajuste + teste que confirma prompt usa valores do ctx |
| `CHANGELOG.md` | Add | Entrada v0.6.0-alpha |
| `docs/topics/onboarding.md` | Add | Nota sobre contrato do selector |
| `pyproject.toml` (ambos pacotes) | Bump | 0.5.7 → 0.6.0a0 |

## 5. Testes

### TDD: casos novos

**`TestExpansionContextShape`:**
- `ctx["total_cap"]` bate com `args.total_cap` do CLI.
- `ctx["current_total"]` = soma de top+saved+recent únicos (mesma fórmula que `current_total_unique`).
- `ctx["remaining"]` = `total_cap - current_total`.
- Ctx é passado mesmo quando selector retorna `[]` imediatamente.

**`TestPromptUsaCtxReal`:**
- `_interactive_selector` chama `_prompt_expansion_confirm` com os valores de `ctx`, não hard-coded.

**Regressão de hard break:**
- Selector 1-arg levanta `TypeError` (prova que o break é intencional).

### Tests existentes a atualizar

23+ casos em `TestPlaylistExpansion` e `TestExpansionEdgeCases` definem
selectors inline via `lambda pls: [...]`. Todos viram `lambda pls, ctx: [...]`.
Sem escape — é o custo do hard break.

### E2E

Nenhuma mudança. Suite de `tests/integration/` não exercita expansão (sem
credencial Spotify).

## 6. Critérios de aceite

- Todo selector no repo aceita 2 args.
- `expansion_info` retornado por `run()` passa validação TypedDict estática
  (mypy/pyright opcional — não está no CI, mas a definição existe para
  futuro).
- Prompt interativo mostra `current_total` real (não mais 0) quando chamado
  via CLI com total_cap acima do current_total.
- Suite inteira passa. Base atual (v0.5.7): 457 unit + 13 integration + 35
  mcp = 505. Esperados ~4-5 testes novos (TestExpansionContextShape,
  TestPromptUsaCtxReal, regressão hard break) → alvo ~510. 23+ testes
  existentes em `TestPlaylistExpansion`/`TestExpansionEdgeCases` são
  atualizados (mesma contagem, assinatura nova).

## 7. Não-objetivos

- **Não** adicionar `own_playlists_empty_count` ao `ExpansionContext` (já
  está no report, selector não precisa dele para decidir).
- **Não** evoluir retorno do selector além de `list[str]` (YAGNI).
- **Não** reorganizar `expansion_info` em formato nested (flat tipado foi
  a escolha — ver discussão de brainstorming).
- **Não** criar camada de deprecation/wrap — hard break.
- **Não** mexer em `MCP server` — ainda não expõe onboard como tool.

## 8. Referências

- Item #27 do backlog consolidado (`docs/reviews/2026-04-19-backlog-consolidado.md`).
- Item #29 do mesmo backlog.
- Decisões de brainstorming: forma 1 (ctx como objeto), TypedDict, 3 campos,
  hard break, flat tipado.
