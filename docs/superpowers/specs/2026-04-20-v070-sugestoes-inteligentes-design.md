# Design — v0.7.0-alpha.0: sugestões inteligentes com rationale persistido

**Data:** 2026-04-20
**Versão alvo:** v0.7.0-alpha.0
**Origem:** item B3 do backlog consolidado pós-v0.5.3 (`docs/reviews/2026-04-19-backlog-consolidado.md:208,218`)
**Escopo:** substituir `_derive_suggestions` (artist-dominance + hard-coded) por lógica baseada em gêneros + décadas + artistas + taste signals, com log de rationale consultável via MCP.

---

## 1. Objetivo

Sugestões de contexto do onboard hoje combinam 2 strings derivadas de artistas dominantes com 3 strings fixas ("piano minimalista neoclássico para leitura", etc.). Substituir por lógica que:

1. **Usa sinais reais do catálogo** — gêneros obtidos via `sp.artists()`, décadas via `release_date`, artistas já coletados.
2. **Incorpora TasteProfile quando disponível** — filtra rejeitados, amplifica `good`, penaliza `skip`.
3. **Persiste rationale** em arquivo consultável — `state_dir()/onboard_rationale.json`. Agente MCP responde "por que essa sugestão apareceu?".

Audio features (`sp.audio_features`) **não entra** — Spotify deprecou acesso para apps novos em janeiro de 2026.

## 2. Contexto

### 2.1 Estado atual (v0.6.2-alpha.1)

`core/onboard.py:219-243` implementa:

```python
def _derive_suggestions(tracks_by_weight: list[dict]) -> list[str]:
    """Deriva até 5 sugestões de contexto a partir de artistas dominantes."""
    artist_count = Counter()
    for t in tracks_by_weight[:100]:
        for a in t.get("artists", []):
            artist_count[a["name"]] += 1
    top_artists = [a for a, _ in artist_count.most_common(5)]

    if len(top_artists) >= 2:
        sug1 = f"ambient instrumental inspirado em {top_artists[0]} e {top_artists[1]}"
        sug2 = f"faixas melódicas no estilo de {top_artists[0]}"
    elif top_artists:
        sug1 = "ambient instrumental para trabalho analítico"
        sug2 = f"faixas melódicas no estilo de {top_artists[0]}"
    else:
        sug1 = "ambient instrumental para trabalho analítico"
        sug2 = "faixas melódicas para foco profundo"

    return [
        sug1,
        sug2,
        "piano minimalista neoclássico para leitura",
        "indie folk melancólico para reflexão",
        "eletrônica downtempo para tarde tranquila",
    ][:5]
```

Consumo único em `cli/onboard.py:288` — renderiza no painel Rich de fim de onboard.

### 2.2 Dados já disponíveis em memória

No momento que `_derive_suggestions` é chamado em `onboard.run:598`:
- `sorted_tracks`: lista de dicts com `{uri, name, artists: [{name}], ...}` ordenada por peso. Album/release_date NÃO está presente — top_tracks do Spotify inclui `album.release_date` mas `_compute_weights` descarta; precisamos preservar.
- `taste: TasteProfile` passado ao `run()`.
- `tracks_added` inclui faixas da expansão.

### 2.3 Dados faltantes

- **Gêneros**: não vêm nem em `top_tracks` nem em `saved_tracks`. Só via `sp.artists(ids=[...])` — retorna lista com `.genres = ["indie folk", "chamber folk"]` por artista.
- **Release date**: está em `track.album.release_date` quando fetchado via `top_tracks` com fields default, mas foi descartado pelo `_compute_weights`. Preciso preservar para décadas.

### 2.4 Por que um bundle

Sugestões só valem a pena se forem genuinamente úteis. Entregar "gênero sem rationale" ou "rationale sem taste" cada um em release separado dilui a entrega. Uma release única com todos os 4 sinais (artistas, gêneros, décadas, taste) + persistência do rationale + tool MCP de consulta é o mínimo coerente.

Escopo ainda cabe num plan bite-sized (~10-12 tasks estimados); não precisa decomposição.

---

## 3. Design

### 3.1 Preservar `release_date` no pipeline

Atualmente `_compute_weights` produz `sorted_tracks` com apenas `uri`, `name`, `artists`. Expandir para incluir `release_date` (string, formato `"YYYY"`, `"YYYY-MM"` ou `"YYYY-MM-DD"` conforme retorno do Spotify). Quando não disponível (tracks de `recent` que podem vir sem album), registra string vazia — `_decade_of` trata.

Mudança: adicionar campo ao dict construído em `_compute_weights` e nas fontes (`top_long`/`medium`/`short` → `release_date = track["album"]["release_date"]`; `saved` → `item["track"]["album"]["release_date"]`; `recent` → idem).

### 3.2 Novo helper `_fetch_artists_genres`

```python
def _fetch_artists_genres(sp, artist_names: list[str]) -> dict[str, list[str]]:
    """Resolve artist names → genres via sp.artists (1 batch call até 50 IDs).

    Precisa achar o ID do artista primeiro — `top_artists` do Spotify retorna
    full objects com .id, mas o pipeline atual joga fora. Ajustar:
    _fetch_weights_and_tracks preserva artist ID quando veio de top_tracks.

    Retorna map {artist_name: [genres_lowercased]}.
    Se a call falhar (MaestraError), propaga; se falhar genérica,
    retorna dict vazio e a geração cai em fallback.
    """
```

**Fonte dos IDs**: `sp.current_user_top_tracks` já retorna cada track com `"artists": [{"id": "X", "name": "Y"}, ...]`. Preservar `"id"` em `_compute_weights` junto com o nome. Para `saved`/`recent`/`playlist_items` expandidos, idem — quando disponível.

Se um artista aparece mas sem ID (ex.: playlist com track sem metadata completa), fica sem gênero.

**Batch**: top 50 artistas por frequência → 1 call `sp.artists(ids=[...])`.

### 3.3 Helper `_decade_of`

```python
def _decade_of(release_date: str) -> str:
    """Converte 'YYYY-MM-DD' ou 'YYYY' em '2010s', '1990s', etc.

    Retorna '' se não parse."""
```

Implementação trivial: extrair primeiros 4 dígitos, mapear década.

### 3.4 Nova `_derive_suggestions`

Assinatura:

```python
def _derive_suggestions(
    tracks_by_weight: list[dict],
    artists_genres: dict[str, list[str]],
    taste: TasteProfile,
    *,
    top_k: int = 5,
) -> tuple[list[str], list[RationaleEntry], OnboardSignals]:
    """Retorna (suggestion_texts, rationale_entries, signals).

    - suggestion_texts: list[str] de até `top_k` sugestões natural-language.
    - rationale_entries: list[RationaleEntry] paralela — index i descreve
      os dados que geraram suggestion_texts[i].
    - signals: agregados (top_genres, dominant_decades, top_artists) para
      o report `onboard.run()`.
    """
```

#### Algoritmo

**Fase 1 — aplicar taste filters** (se `taste` tem dados):
- Remover de `tracks_by_weight` qualquer `t` com `taste.is_rejected(t["uri"])` OR `t["artists"][0]["name"] in taste.get_rejected_artists()`.
- Para cada track remanescente, computar `adjusted_weight = base_weight + feedback_adj(t)` usando o schema real do TasteProfile (`track["feedback"]` single valor "good"/"bad"/None, `track["skip_count"]` int):
  - `+2.0` se `track["feedback"] == "good"`.
  - `-0.5 * track["skip_count"]` (proporcional).
  - Floor em 0 (não vira peso negativo).
  - `feedback == "bad"` já foi filtrado em is_rejected (fase anterior).
- Re-rankear por `adjusted_weight`.

**Fase 2 — agregar signals**:
- `genre_counter: Counter[str]` — para cada track dos top 200, para cada gênero dos seus artistas em `artists_genres`, soma `adjusted_weight * 1.0 / len(artists)`.
- `decade_counter: Counter[str]` — para cada track dos top 200, `decade_counter[_decade_of(track["release_date"])] += adjusted_weight`.
- `artist_counter: Counter[str]` — para cada track, `artist_counter[first_artist.name] += adjusted_weight`. **Cap por artista**: contar no máximo 10 ocorrências do mesmo artista (evita sugestão monotemática).
- `top_genres = genre_counter.most_common(10)`, `dominant_decades = decade_counter.most_common(3)`, `top_artists = artist_counter.most_common(10)`.

**Fase 3 — gerar sugestões**:

Template engine simples: tabela módulo-level mapeia gênero → adjectivos/contextos típicos.

```python
_GENRE_MOOD_TEMPLATES = {
    "indie folk": ["melancólico para reflexão", "acústico para manhã"],
    "neo-classical": ["instrumental para concentração", "minimalista para leitura"],
    "ambient": ["para trabalho analítico", "noturno para escrita"],
    "electronic": ["downtempo para tarde tranquila", "dinâmico para treino"],
    "jazz": ["suave para jantar", "noturno com piano"],
    "hip hop": ["groove pra estrada", "com bateria pesada pra treino"],
    # ... 20-30 gêneros cobertos; fallback genérico abaixo
}
_FALLBACK_MOODS = [
    "para concentração",
    "para relaxar no fim do dia",
    "para caminhada matinal",
    "para pausa do trabalho",
]
```

Para cada gênero top (limitado a 3 primeiros do `top_genres`):
- Se tem template: `"{genre} {random_template_mood}"` (determinístico via seed = hash do input para estabilidade cross-run).
- Se não: `"{genre} {fallback_mood}"`.

Depois, adiciona 1-2 sugestões de **cross-signal**:
- `"{top_artist} e similares para {mood}"` com mood derivado da década dominante.
- `"{dominant_decade} — faixas {genre2} para {mood2}"`.

Total: top_k = 5. Deduplica se dois templates colidirem.

**Fallback se dados insuficientes** (<3 gêneros reais OU <50 tracks_by_weight após filtro taste):
- Comportamento v0.5.x: 2 personalizadas + 3 genéricas. Mantém UX de first-run.

**Fase 4 — construir rationale por sugestão**:

Para cada `suggestion_text`, identificar "com base em que":
- Extrair tokens: se o template usou gênero "X", based_on["genres"] = ["X"]; se usou artista "Y", based_on["artists"] = ["Y"]; década idem.
- `contributing_tracks`: top 10 tracks (por `adjusted_weight` desc) que matcham o `based_on` — ex.: se based_on["genres"]=["indie folk"], incluir tracks cujos artistas têm "indie folk" em `artists_genres`.
- Para cada track na lista: `{uri, name, artist, weight: adjusted_weight, feedback: taste.data["tracks"].get(uri, {}).get("feedback"), skip_count: taste.data["tracks"].get(uri, {}).get("skip_count", 0)}`.

### 3.5 Persistência do rationale

Novo arquivo em `state_dir()/onboard_rationale.json`:

```json
{
    "generated_at": "2026-04-20T09:15:03-03:00",
    "suggestions": [
        {
            "text": "indie folk melancólico para reflexão",
            "based_on": {
                "genres": ["indie folk"],
                "decades": [],
                "artists": []
            },
            "contributing_tracks": [
                {
                    "uri": "spotify:track:6habFhsOp2NvshLv26DqMb",
                    "name": "Holland Road",
                    "artist": "Mumford & Sons",
                    "weight": 8.5,
                    "feedback": "good",
                    "skip_count": 0
                }
            ]
        }
    ]
}
```

Persistido via `storage.atomic_write_json` (já existe). Sobrescreve a cada `onboard.run()` completo — lifetime = último onboard.

Função helper nova `_persist_rationale(entries: list[RationaleEntry]) -> Path`.

### 3.6 Report `onboard.run()` expandido

Adição ao dict de retorno:

```python
report["signals"] = {
    "top_genres": [("indie folk", 18.5), ("neo-classical", 12.0), ...],  # max 10
    "dominant_decades": [("2010s", 340.0), ("2020s", 180.0), ...],  # max 3
    "top_artists": [("Sufjan Stevens", 27.0), ...],  # max 10
}
```

`context_suggestions` continua list[str] — compat com CLI.

Novo campo `rationale_path` no report (path absoluta para o arquivo JSON persistido). Útil para MCP tool localizar.

### 3.7 Nova MCP tool `onboard_rationale`

Em `maestra-mcp/src/maestra_mcp/tools.py`:

```python
@tool("onboard_rationale",
      "Retorna o rationale persistido das últimas sugestões do onboard. "
      "Permite explicar ao usuário por que cada sugestão apareceu, "
      "incluindo tracks que mais contribuíram e feedback histórico.",
      {
          "type": "object",
          "properties": {
              "suggestion": {
                  "type": "string",
                  "description": "Texto exato da sugestão (opcional; sem ela retorna todas).",
              }
          },
          "additionalProperties": False,
      })
def _onboard_rationale(args):
    suggestion = args.get("suggestion")
    path = state_dir() / "onboard_rationale.json"
    if not path.exists():
        raise UserError(
            "Nenhum rationale persistido.",
            where={"hint": "Rode `maestra onboard` primeiro."},
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    if suggestion is None:
        return data
    # Filtra
    match = [e for e in data["suggestions"] if e["text"] == suggestion]
    if not match:
        raise UserError(
            f"Sugestão não encontrada: {suggestion}",
            where={"available": [e["text"] for e in data["suggestions"]]},
        )
    return {"generated_at": data["generated_at"], "suggestions": match}
```

Handler puramente read-only; sem chamada a `controller`/`taste`/etc.

## 4. Tipos novos em `core/onboard_types.py`

```python
class OnboardSignals(TypedDict):
    top_genres: list[tuple[str, float]]
    dominant_decades: list[tuple[str, float]]
    top_artists: list[tuple[str, float]]


class TrackRationale(TypedDict):
    uri: str
    name: str
    artist: str
    weight: float
    feedback: str | None  # "good"/"bad"/None (global)
    skip_count: int  # acumulado de skips registrados pelo TasteProfile


class RationaleEntry(TypedDict):
    text: str
    based_on: dict  # {"genres": [...], "decades": [...], "artists": [...]}
    contributing_tracks: list[TrackRationale]
```

## 5. Arquivos afetados

| Arquivo | Tipo | Mudança |
|---|---|---|
| `core/onboard.py` | Modify | `_compute_weights` preserva `release_date` e `artist_id`; `_derive_suggestions` reescrita; +`_fetch_artists_genres`, `_decade_of`, `_persist_rationale`, `_apply_taste_to_weights` |
| `core/onboard_types.py` | Modify | +OnboardSignals, TrackRationale, RationaleEntry |
| `maestra-mcp/src/maestra_mcp/tools.py` | Modify | +tool `onboard_rationale` |
| `maestra-mcp/tests/test_tools.py` | Add | 3 testes: sem arquivo, lista completa, filtro por sugestão |
| `tests/unit/test_onboard.py` | Add | TestDeriveSuggestionsIntel (~6 casos): genres, decades, fallback insuficiente, taste filter rejeitados, good amplifica, cap por artista |
| `tests/unit/test_onboard.py` | Add | TestPersistRationale (~2 casos): arquivo criado, schema correto |
| `packages/maestra-ai/pyproject.toml` | Modify | bump 0.6.2a1 → 0.7.0a0 |
| `packages/maestra-mcp/pyproject.toml` | Modify | bump + pin |
| `CHANGELOG.md` | Add | seção [0.7.0-alpha.0] |
| `docs/reviews/2026-04-19-backlog-consolidado.md` | Touch | marcar B3 como fechado |

## 6. Testes

### 6.1 Novos — unit onboard

**`TestDeriveSuggestionsIntel`:**
- `test_sugestao_usa_genero_dominante_quando_disponivel` — artists_genres tem "indie folk" forte → 1ª sugestão mencionar "indie folk".
- `test_cap_por_artista_evita_monotema` — 50 tracks do mesmo artista + 2 de outros → top_artists mostra 2 artistas distintos, não 1.
- `test_taste_rejeitado_nao_entra_em_signals` — taste.is_rejected("uri1") → artista dessa track não aparece em top_artists.
- `test_rejected_artists_filtram_tracks` — `taste.get_rejected_artists()` inclui "BandA" → sugestões não mencionam BandA.
- `test_good_signals_amplificam_peso` — 10 tracks com `good` > 10 tracks neutros do mesmo artista → good aparece primeiro.
- `test_fallback_quando_generos_insuficientes` — `artists_genres={}` → retorna 2 personalizadas + 3 genéricas (compat v0.5.x).

**`TestPersistRationale`:**
- `test_persist_cria_arquivo_com_schema_correto` — roda `run()` com sp mockado, confere que `onboard_rationale.json` existe e tem keys `generated_at` + `suggestions`.
- `test_persist_sobrescreve_onboard_anterior` — 2 runs em sequência; arquivo reflete o último.

### 6.2 Novos — MCP

**`TestOnboardRationaleTool`:**
- `test_retorna_erro_quando_sem_rationale` — arquivo não existe → `UserError` com code="UserError".
- `test_retorna_todas_sugestoes_sem_args` — arquivo existe, call sem `suggestion` → dict completo.
- `test_filtra_por_suggestion_exata` — call com `suggestion="indie folk..."` → só aquela.

### 6.3 Regressão

Suite: 482 unit + 42 MCP = 524 → ~532 (+8 testes novos estimados; alguns testes existentes de `_derive_suggestions` precisam ajuste).

## 7. Critérios de aceite

1. `grep "hard-coded"` em `_derive_suggestions` retorna zero — nenhuma string fixa literal nas 5 sugestões geradas (exceto no fallback de dados insuficientes).
2. `sp.artists(ids=...)` chamada no caminho feliz do onboard, exatamente 1 vez.
3. `state_dir()/onboard_rationale.json` escrito via `atomic_write_json`.
4. Nova tool `onboard_rationale` no `_REGISTRY`, com schema estrito.
5. TasteProfile com dados não-vazios produz sugestões diferentes do mesmo sample sem taste.
6. Suite inteira: zero falhas; ~532 testes.
7. `report["signals"]` tem as 3 chaves com listas não-vazias quando dados suficientes.

## 8. Non-objetivos

- **Audio features / recommendations** — deprecado, já decidido fora de escopo.
- **Multi-idioma nas sugestões** — PT-BR apenas. i18n fica para v1.x.
- **Automatizar `context set`** com base na 1ª sugestão — mantém user-guided (padrão atual).
- **Histórico de rationales** — sempre último; sem append. Se precisar, v0.7.x via flag `--keep-history`.
- **Refactor do curator** para consumir `signals` — curator fica como está; `signals` é output do onboard apenas.
- **`context_score` nas sugestões** — circular (context_score vem do curator); fica fora.
- **Novo command `maestra onboard explain`** — YAGNI; MCP tool já cobre o caso.

## 9. Riscos e mitigações

| Risco | Prob. | Mitigação |
|---|---|---|
| Templates engessados produzem sugestões parecidas | Média | Teste `test_sugestao_usa_genero_dominante_quando_disponivel` + inspeção manual em 3 cenários distintos; templates em dict facilitam ajuste |
| `sp.artists()` falha → sugestões colapsam | Baixa | Try/except translate para fallback (comportamento v0.5.x) em vez de propagar |
| Peso de `good`/`skip` mal calibrado distorce | Média | Cap por artista (§Fase 2); constantes em module-level para tuning rápido |
| Rationale JSON cresce demais | Baixa | Cap de 10 tracks por sugestão × 5 sugestões × ~500 bytes = ~25KB. Aceitável |
| Release_date ausente em parte do sample | Alta | `_decade_of("")` retorna ""; bucket "" é filtrado antes do Counter |
| Spotify deprecar `sp.artists()` também | Baixa | Sem mitigação — se acontecer, caímos no fallback. Evento externo |

## 10. Referências

- Backlog consolidado: `docs/reviews/2026-04-19-backlog-consolidado.md:208,218`.
- `_derive_suggestions` atual: `core/onboard.py:219-243`.
- Consumo único no CLI: `cli/onboard.py:288`.
- Pattern `atomic_write_json`: `core/storage.py:93`.
- Pattern MCP tool read-only: `maestra-mcp/tools.py` (várias; ex.: `now`).
- TasteProfile API pública (pós-v0.6.1): `is_rejected`, `get_rejected_artists`, `data["tracks"]`.
