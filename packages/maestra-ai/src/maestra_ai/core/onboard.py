"""Onboard — importa histórico Spotify e popula taste_profile inicial.

6 etapas ponderadas:
1. Autenticação (implícita — sp recebido já autenticado).
2. Playlist — cria privada com sufixo se nome duplicado.
3. Top tracks (long_term, medium_term, short_term) — 3 janelas.
4. Biblioteca (saved) — paginação defensiva, cap 1000.
5. Recently played — 50 mais recentes.
6. Análise local — pondera sinais, registra em taste_profile,
   semeia playlist, deriva 5 sugestões de contexto.

Pesos: long=3 (gosto consolidado), medium=2, short=2 (mood recente),
saved=3 (curadoria explícita via ❤️), recent=1.

v0.4.5: Liked Songs repesado para 3 — ação de favoritar é declaração
explícita de curadoria e merece peso igual ao top_long_term (que é
comportamental). Cap elevado de 1000 → 5000 para cobrir bibliotecas
longas. Parâmetro `saved_cap` na `run(...)` permite override controlado.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from datetime import UTC
from pathlib import Path

from maestra_ai.core import storage
from maestra_ai.core.config import any_source_enabled, load_and_migrate
from maestra_ai.core.errors import MaestraError, PlaylistCreateForbiddenError
from maestra_ai.core.external.mood_mappings import (  # noqa: F401
    _FALLBACK_MOODS,
    _FALLBACK_MOODS_BY_FAMILY,
    _GENRE_FAMILIES,
    _GENRE_MOOD_TEMPLATES,
    _MOOD_CONTEXT,
    _MOOD_CONTEXT_BY_FAMILY,
    MOOD_TAG_KEYWORDS,
    _family_for_genre,
)
from maestra_ai.core.onboard_types import (
    ExpansionContext,
    ExpansionInfo,
    FailedPlaylist,
    OnboardSignals,
    OwnPlaylist,
    PlaylistSelector,
    RationaleEntry,
    SelectedPlaylist,
    TrackRationale,
)

WEIGHTS = {
    "long_term": 3,
    "medium_term": 2,
    "short_term": 2,
    "saved": 3,
    "recent": 1,
    # v0.5.3: faixas de playlists criadas pelo usuário. Peso 2 =
    # curadoria explícita indireta (colocou em playlist mas não
    # necessariamente "liked"), entre recent=1 e saved=3.
    "playlist": 2,
}

_MAX_SAVED = 5000
_PAGE = 50


def _fetch_top_window(sp, time_range: str) -> list[dict]:
    resp = sp.current_user_top_tracks(limit=50, time_range=time_range)
    return resp.get("items", [])


def _fetch_saved(
    sp,
    progress_cb: Callable | None = None,
    *,
    max_tracks: int = _MAX_SAVED,
) -> list[dict]:
    """Paginação pelo campo `next` da resposta Spotify.

    v0.4.4 CRITICAL-4: ignora items com track=None (faixa removida do
    catálogo / indisponível na região).

    v0.4.5: `max_tracks` parametrizável (default = _MAX_SAVED = 5000).

    v0.5.2 (bug 3): usar `resp['next']` como condição de parada em vez da
    heurística `len(items) < 50`. Cenário que falhava antes: página
    intermediária com menos de 50 items (rate limit soft, inconsistência
    do Spotify) encerrava a paginação prematura e perdia o restante da
    biblioteca silenciosamente. Fallback para heurística quando `next`
    ausente (mocks antigos, respostas malformadas).
    """
    collected: list[dict] = []
    offset = 0
    while len(collected) < max_tracks:
        resp = sp.current_user_saved_tracks(limit=_PAGE, offset=offset)
        items = resp.get("items", [])
        has_next_field = "next" in resp
        next_url = resp.get("next")
        if not items:
            break
        for it in items:
            track = it.get("track")
            if track is None or not track.get("uri"):
                continue
            collected.append(track)
        offset += len(items)
        if progress_cb:
            progress_cb(len(collected))
        # Parada canônica: Spotify diz que acabou via next=null.
        if has_next_field and next_url is None:
            break
        # Fallback (campo next ausente): heurística antiga.
        if not has_next_field and len(items) < _PAGE:
            break
    return collected[:max_tracks]


# M6 v0.6.2: cap anti-loop. 200 × _PAGE(50) = 10_000 playlists
# (Spotify hard limit para conta de usuário). Defense-in-depth contra
# bug de servidor ou mock com `next` fixo.
_PLAYLIST_PAGE_CAP = 200


def _fetch_own_playlists(
    sp, me_id: str, *, progress_cb: Callable | None = None,
) -> tuple[list[OwnPlaylist], int]:
    """v0.5.3: lista playlists criadas PELO próprio usuário (filtro
    owner.id == me_id). Exclui seguidas. Paginação via campo `next`.

    v0.5.3.1 (C2): guarda contra loop infinito.

    v0.5.5 #4: filtra playlists com `track_count <= 0`.

    v0.5.7 #17: retorna tupla `(usable, empty_count)`.

    v0.5.7 #20: `progress_cb` opcional recebe int (total listado até
    agora) a cada página — CLI com Rich Progress pode atualizar status
    em bibliotecas grandes (500+ playlists) sem silêncio de 10s.
    """
    collected: list[dict] = []
    empty_count = 0
    offset = 0
    for _ in range(_PLAYLIST_PAGE_CAP):
        resp = sp.current_user_playlists(limit=_PAGE, offset=offset)
        items = resp.get("items", []) or []
        if not items:
            break
        for it in items:
            owner = (it.get("owner") or {}).get("id")
            if owner != me_id:
                continue
            track_count = (it.get("tracks") or {}).get("total", 0)
            if track_count <= 0:
                empty_count += 1
                continue
            collected.append({
                "id": it.get("id"),
                "name": it.get("name") or it.get("id"),
                "track_count": track_count,
            })
        offset += len(items)
        if progress_cb:
            progress_cb(len(collected))
        if resp.get("next") is None:
            break
    return collected, empty_count


_PLAYLIST_TRACKS_FIELDS = "items(track(uri,name,artists(name))),next"


def _fetch_playlist_tracks(sp, playlist_id: str, *, max_tracks: int) -> list[dict]:
    """v0.5.3: busca tracks de uma playlist, paginação defensiva (100/call).

    Ignora track=None (locais ou removidas do catálogo).
    Respeita cap `max_tracks`.

    v0.5.5 #3: `fields` restrito ao que taste_profile consome (uri, name,
    artists.name) + campo de paginação. Reduz payload em ~80% — cada
    response de playlist grande caía com metadata de álbum, imagens e
    available_markets (~180 países) sem utilidade local.
    """
    collected: list[dict] = []
    offset = 0
    page_size = 100
    while len(collected) < max_tracks:
        resp = sp.playlist_items(
            playlist_id,
            limit=page_size,
            offset=offset,
            fields=_PLAYLIST_TRACKS_FIELDS,
        )
        items = resp.get("items", []) or []
        if not items:
            break
        for it in items:
            if len(collected) >= max_tracks:
                break
            track = it.get("track")
            if track is None or not track.get("uri"):
                continue
            collected.append(track)
        offset += len(items)
        if resp.get("next") is None:
            break
    return collected[:max_tracks]


def _fetch_recent(sp) -> list[dict]:
    resp = sp.current_user_recently_played(limit=50)
    return [it.get("track") for it in resp.get("items", []) if it.get("track")]


def _compute_weights(
    *,
    top_long: list[dict],
    top_medium: list[dict],
    top_short: list[dict],
    saved: list[dict],
    recent: list[dict],
) -> dict[str, int]:
    w: Counter[str] = Counter()
    for t in top_long:
        w[t["uri"]] += WEIGHTS["long_term"]
    for t in top_medium:
        w[t["uri"]] += WEIGHTS["medium_term"]
    for t in top_short:
        w[t["uri"]] += WEIGHTS["short_term"]
    for t in saved:
        w[t["uri"]] += WEIGHTS["saved"]
    for t in recent:
        w[t["uri"]] += WEIGHTS["recent"]
    return dict(w)


# v0.7.0: constantes de adjustment por feedback. Module-level para
# facilitar tuning; não são configuráveis por usuário (YAGNI).
_GOOD_BONUS = 2.0
_SKIP_PENALTY = 0.5


def _apply_taste_to_weights(
    weights: dict[str, float],
    tracks: list[dict],
    taste,
) -> dict[str, float]:
    """Filtra rejeitados e aplica bonus/penalty baseado em feedback.

    - `taste.is_rejected(uri)` ou artista em `rejected_artists` → remove.
    - `track["feedback"] == "good"` → +_GOOD_BONUS.
    - Penalty = skip_count * _SKIP_PENALTY, floor em 0.
    - Tracks com peso final <= 0 são removidas do dict.

    Não muta `weights`. Retorna dict novo.
    """
    rejected_artists = set(taste.get_rejected_artists())
    track_index = {t["uri"]: t for t in tracks if t.get("uri")}
    out: dict[str, float] = {}
    for uri, base in weights.items():
        if taste.is_rejected(uri):
            continue
        track = track_index.get(uri, {})
        first_artist = ""
        artists = track.get("artists") or []
        if artists:
            first_artist = artists[0].get("name") or ""
        if first_artist in rejected_artists:
            continue
        adjusted = float(base)
        profile_track = taste.data.get("tracks", {}).get(uri, {})
        if profile_track.get("feedback") == "good":
            adjusted += _GOOD_BONUS
        skip_count = profile_track.get("skip_count", 0) or 0
        adjusted -= skip_count * _SKIP_PENALTY
        if adjusted <= 0:
            continue
        out[uri] = adjusted
    return out



def _decade_of(release_date: str) -> str:
    """Converte 'YYYY-MM-DD', 'YYYY-MM' ou 'YYYY' em string da década.

    Ex.: '2015-04-13' → '2010s'. String vazia ou inválida → ''.
    """
    if not release_date or len(release_date) < 4:
        return ""
    year_str = release_date[:4]
    if not year_str.isdigit():
        return ""
    year = int(year_str)
    decade = (year // 10) * 10
    return f"{decade}s"


_FALLBACK_SUGGESTIONS = [
    "piano minimalista neoclássico para leitura",
    "indie folk melancólico para reflexão",
    "eletrônica downtempo para tarde tranquila",
]


_DEFAULT_CAP_PER_ARTIST = 10


def _derive_suggestions(
    tracks_by_weight: list[dict],
    weights: dict[str, float],
    artists_genres: dict[str, list[str]],
    taste,
    *,
    top_k: int = 5,
    cap_per_artist: int = _DEFAULT_CAP_PER_ARTIST,
    artists_tags: dict[str, list[str]] | None = None,
) -> tuple[list[str], list[RationaleEntry], OnboardSignals]:
    """Deriva sugestões ricas + rationale + signals (v0.7.0 B3).

    Retorna (texts, rationale_entries, signals) onde:
    - texts: list[str] de até `top_k` sugestões natural-language.
    - rationale_entries: list[RationaleEntry] paralela — index i explica texts[i].
    - signals: OnboardSignals com top_genres/dominant_decades/top_artists.
    """
    genre_counter: Counter[str] = Counter()
    decade_counter: Counter[str] = Counter()
    artist_counter: Counter[str] = Counter()
    artist_track_count: Counter[str] = Counter()

    # v0.9.0-alpha.4 (C3): para cada gênero, lembrar os top-3 artist_ids
    # que mais contribuíram. Usado depois para derivar mood das tags
    # agregadas desses artistas (pool mais rico que top-1 apenas).
    genre_to_top_artist_ids: dict[str, list[str]] = {}
    genre_artist_score: dict[tuple[str, str], float] = {}

    ordered = sorted(
        tracks_by_weight,
        key=lambda t: weights.get(t.get("uri", ""), 0.0),
        reverse=True,
    )[:200]

    for t in ordered:
        uri = t.get("uri")
        if not uri:
            continue
        w = weights.get(uri, 0.0)
        artists = t.get("artists") or []
        first_artist = (artists[0].get("name") if artists else "") or ""

        if first_artist and artist_track_count[first_artist] >= cap_per_artist:
            continue
        if first_artist:
            artist_track_count[first_artist] += 1
            artist_counter[first_artist] += w

        decade = _decade_of(t.get("release_date", ""))
        if decade:
            decade_counter[decade] += w

        for a in artists:
            aid = a.get("id")
            if not aid:
                continue
            for g in artists_genres.get(aid, []):
                genre_counter[g.lower()] += w / max(len(artists), 1)
                # NEW: track top artist per genre for mood derivation
                key = (g.lower(), aid)
                genre_artist_score[key] = genre_artist_score.get(key, 0.0) + w

    # C3: resolve top-3 artistas por gênero.
    for genre in {k[0] for k in genre_artist_score.keys()}:
        scored = [
            (aid, score)
            for (g, aid), score in genre_artist_score.items()
            if g == genre
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        genre_to_top_artist_ids[genre] = [aid for aid, _ in scored[:3]]

    signals: OnboardSignals = {
        "top_genres": [(g, round(s, 2)) for g, s in genre_counter.most_common(10)],
        "dominant_decades": [(d, round(s, 2)) for d, s in decade_counter.most_common(3)],
        "top_artists": [(a, round(s, 2)) for a, s in artist_counter.most_common(10)],
    }

    texts: list[str] = []
    rationale: list[RationaleEntry] = []

    if not signals["top_genres"]:
        texts, rationale = _fallback_suggestions(
            signals["top_artists"], ordered, taste, top_k,
        )
        return texts, rationale, signals

    # C1: rastreia contextos já usados para evitar repetição entre sugestões.
    used_contexts: set[str] = set()

    # v0.9.0-alpha.6 (A): pre-alimenta used_contexts com o contexto do
    # template fixo do top artist (gerado depois no fluxo mas publicado
    # no mesmo conjunto de 5 sugestões). Evita colisão com sugestão
    # baseada em gênero que resolva para "para foco profundo".
    if signals["top_artists"]:
        used_contexts.add("para foco profundo")

    used_genres: list[str] = []
    for genre, _score in signals["top_genres"][:3]:
        mood = _select_mood(
            genre, seed=genre,
            artists_tags=artists_tags,
            genre_to_top_artist_ids=genre_to_top_artist_ids,
            used_contexts=used_contexts,
        )
        used_contexts.add(mood)
        text = f"{genre} {mood}"
        texts.append(text)
        used_genres.append(genre)
        rationale.append(_build_rationale(
            text, based_on={"genres": [genre], "decades": [], "artists": []},
            ordered=ordered, artists_genres=artists_genres, taste=taste,
            match_genre=genre,
        ))

    if signals["dominant_decades"]:
        top_decade = signals["dominant_decades"][0][0]
        second_genre = (signals["top_genres"][1][0]
                        if len(signals["top_genres"]) > 1
                        else signals["top_genres"][0][0])
        mood = _select_mood(
            second_genre, seed=f"{top_decade}-{second_genre}",
            artists_tags=artists_tags,
            genre_to_top_artist_ids=genre_to_top_artist_ids,
            used_contexts=used_contexts,
        )
        used_contexts.add(mood)
        text = f"{top_decade} — faixas {second_genre} {mood}"
        if text not in texts:
            texts.append(text)
            rationale.append(_build_rationale(
                text,
                based_on={"genres": [second_genre], "decades": [top_decade], "artists": []},
                ordered=ordered, artists_genres=artists_genres, taste=taste,
                match_genre=second_genre, match_decade=top_decade,
            ))

    if signals["top_artists"]:
        top_artist = signals["top_artists"][0][0]
        text = f"{top_artist} e similares para foco profundo"
        if text not in texts and len(texts) < top_k:
            texts.append(text)
            rationale.append(_build_rationale(
                text,
                based_on={"genres": [], "decades": [], "artists": [top_artist]},
                ordered=ordered, artists_genres=artists_genres, taste=taste,
                match_artist=top_artist,
            ))

    while len(texts) < top_k:
        fallback_idx = len(texts) - len([t for t in texts if t in _FALLBACK_SUGGESTIONS])
        if fallback_idx >= len(_FALLBACK_SUGGESTIONS):
            break
        fallback_text = _FALLBACK_SUGGESTIONS[fallback_idx]
        if fallback_text in texts:
            break
        texts.append(fallback_text)
        fallback_entry: RationaleEntry = {
            "text": fallback_text,
            "based_on": {"genres": [], "decades": [], "artists": []},
            "contributing_tracks": [],
        }
        rationale.append(fallback_entry)

    return texts[:top_k], rationale[:top_k], signals


def _pick_mood_for_genre(genre: str, *, seed: str) -> str:
    """Seleciona um mood determinístico (stable seed) para um gênero."""
    moods = _GENRE_MOOD_TEMPLATES.get(genre.lower(), _FALLBACK_MOODS)
    idx = hash(seed) % len(moods)
    return moods[idx]


def _matched_moods_from_tags(tags: list[str]) -> list[str]:
    """Retorna lista deduplicada e ORDENADA de moods que casam com as tags.

    Preserva ordem de aparição (primeira ocorrência) — isso importa porque
    `_select_mood` depois consulta com um hash determinístico.
    """
    if not tags:
        return []
    matched: list[str] = []
    for tag in tags:
        if not tag:
            continue
        lowered = tag.lower()
        for mood_key in MOOD_TAG_KEYWORDS:
            if mood_key in lowered and mood_key not in matched:
                matched.append(mood_key)
    return matched


def _situation_of(mood: str) -> str:
    """Extrai a 'situação' do mood — parte após o último 'para'.

    v0.11.2: dedup por situação evita colisões como "para garagem" e
    "clássico para garagem" aparecerem em sugestões adjacentes (o usuário
    percebe ambos como 'garagem' e marca o relatório como ruidoso).

    Exemplos:
      'clássico para garagem'    → 'garagem'
      'para garagem'             → 'garagem'
      'energético para deslocamento' → 'deslocamento'
      'para foco profundo'       → 'foco profundo'
      'melancólico'              → 'melancólico' (sem 'para')
    """
    marker = " para "
    idx = mood.rfind(marker)
    if idx != -1:
        return mood[idx + len(marker):].strip()
    if mood.startswith("para "):
        return mood[5:].strip()
    return mood.strip()


def _used_situations(used_contexts: set[str]) -> set[str]:
    """Derivado somente-leitura: conjunto de situações já usadas."""
    return {_situation_of(c) for c in used_contexts}


def _resolve_context_for_mood(
    mood: str,
    *,
    family: str | None,
    seed: str,
    used_contexts: set[str],
) -> str | None:
    """Escolhe um contexto de uso para um mood, considerando família e repetição.

    Prioridade de busca de contextos:
      1. `_MOOD_CONTEXT_BY_FAMILY[(family, mood)]` se a família for dada
         e houver override para esse par.
      2. `_MOOD_CONTEXT[mood]` — default.

    Dentro da lista escolhida, tenta primeiro uma opção cuja *situação*
    ainda não foi usada (v0.11.2). Se todas já foram usadas, retorna
    None (para que o chamador tente outro mood).
    """
    contexts: list[str] = []
    if family is not None:
        contexts = _MOOD_CONTEXT_BY_FAMILY.get((family, mood), [])
    if not contexts:
        contexts = _MOOD_CONTEXT.get(mood, [])
    if not contexts:
        return None

    used_situations = _used_situations(used_contexts)
    start = hash(seed + mood) % len(contexts)
    for offset in range(len(contexts)):
        candidate = contexts[(start + offset) % len(contexts)]
        if _situation_of(candidate) not in used_situations:
            return candidate
    return None


def _derive_mood_from_tags(tags: list[str], *, seed: str) -> str | None:
    """Deriva um contexto de uso a partir de tags MB (legado, single-pick).

    Use `_matched_moods_from_tags` + `_resolve_context_for_mood` para o
    pipeline novo com família e diversificação.
    """
    matched = _matched_moods_from_tags(tags)
    if not matched:
        return None
    primary = matched[hash(seed) % len(matched)]
    contexts = _MOOD_CONTEXT.get(primary, [])
    if not contexts:
        return None
    return contexts[hash(seed + primary) % len(contexts)]


def _select_mood(
    genre: str,
    *,
    seed: str,
    artists_tags: dict[str, list[str]] | None,
    genre_to_top_artist_ids: dict[str, list[str]],
    used_contexts: set[str] | None = None,
) -> str:
    """Escolhe um contexto de uso para um gênero.

    Prioridade:
      1. `_GENRE_MOOD_TEMPLATES[genre]` — mapa curado por gênero.
      2. Para cada mood derivado das tags MB dos top-3 artistas deste
         gênero, tenta resolver um contexto via família (se houver) ou
         via `_MOOD_CONTEXT`, respeitando `used_contexts` (C1).
      3a. `_FALLBACK_MOODS_BY_FAMILY[family]` — fallback específico da
          família (alpha.5), mais coerente que o genérico.
      3b. `_FALLBACK_MOODS` genérico — último recurso.

    `used_contexts` pode ser mutado pelo chamador entre chamadas
    sucessivas para garantir diversidade entre as top-K sugestões.
    """
    if used_contexts is None:
        used_contexts = set()

    # 1. Mapa curado por gênero
    if genre.lower() in _GENRE_MOOD_TEMPLATES:
        # Dentro do mapa, também respeita used_contexts (por situação — v0.11.2).
        curated = _GENRE_MOOD_TEMPLATES[genre.lower()]
        used_situations = _used_situations(used_contexts)
        start = hash(seed) % len(curated)
        for offset in range(len(curated)):
            candidate = curated[(start + offset) % len(curated)]
            if _situation_of(candidate) not in used_situations:
                return candidate
        # Todos os curados usados → primeira opção mesmo assim.
        return curated[start]

    # 2. Tags MB com família de gênero
    family = _family_for_genre(genre)
    if artists_tags:
        top_aids = genre_to_top_artist_ids.get(genre.lower(), [])
        # C3: une tags dos top-3 artistas preservando ordem de aparição.
        merged_tags: list[str] = []
        seen_tags: set[str] = set()
        for aid in top_aids:
            for t in artists_tags.get(aid, []) or []:
                low = t.lower()
                if low not in seen_tags:
                    seen_tags.add(low)
                    merged_tags.append(t)

        matched_moods = _matched_moods_from_tags(merged_tags)
        # Tenta cada mood até um resolver contexto não-usado.
        start_m = hash(seed) % max(len(matched_moods), 1) if matched_moods else 0
        for offset in range(len(matched_moods)):
            mood = matched_moods[(start_m + offset) % len(matched_moods)]
            ctx = _resolve_context_for_mood(
                mood, family=family, seed=seed, used_contexts=used_contexts,
            )
            if ctx is not None:
                return ctx

    # 3a. Fallback específico por família (v0.9.0-alpha.5). Preferido
    # sobre o fallback global porque mantém coerência com o gênero.
    used_situations = _used_situations(used_contexts)
    if family is not None:
        family_fallbacks = _FALLBACK_MOODS_BY_FAMILY.get(family, [])
        if family_fallbacks:
            start_fam = hash(seed) % len(family_fallbacks)
            for offset in range(len(family_fallbacks)):
                candidate = family_fallbacks[
                    (start_fam + offset) % len(family_fallbacks)
                ]
                if _situation_of(candidate) not in used_situations:
                    return candidate
            # Todos usados — ainda melhor repetir família do que cair em
            # fallback global genérico, mas prefere variar em último caso.

    # 3b. Fallback genérico, evitando repetição por situação (v0.11.2).
    start_f = hash(seed) % len(_FALLBACK_MOODS)
    for offset in range(len(_FALLBACK_MOODS)):
        candidate = _FALLBACK_MOODS[(start_f + offset) % len(_FALLBACK_MOODS)]
        if _situation_of(candidate) not in used_situations:
            return candidate
    return _FALLBACK_MOODS[start_f]


def _fallback_suggestions(
    top_artists, ordered, taste, top_k,
):
    """Comportamento v0.5.x: 2 personalizadas + 3 genéricas."""
    texts: list[str] = []
    rationale: list[RationaleEntry] = []
    if len(top_artists) >= 2:
        a1, a2 = top_artists[0][0], top_artists[1][0]
        sug1 = f"ambient instrumental inspirado em {a1} e {a2}"
        sug2 = f"faixas melódicas no estilo de {a1}"
    elif top_artists:
        sug1 = "ambient instrumental para trabalho analítico"
        sug2 = f"faixas melódicas no estilo de {top_artists[0][0]}"
    else:
        sug1 = "ambient instrumental para trabalho analítico"
        sug2 = "faixas melódicas para foco profundo"
    for t in (sug1, sug2):
        texts.append(t)
        entry: RationaleEntry = {
            "text": t,
            "based_on": {"genres": [], "decades": [],
                         "artists": [a for a, _ in top_artists[:2]]},
            "contributing_tracks": [],
        }
        rationale.append(entry)
    for ft in _FALLBACK_SUGGESTIONS:
        if len(texts) >= top_k:
            break
        texts.append(ft)
        generic: RationaleEntry = {
            "text": ft,
            "based_on": {"genres": [], "decades": [], "artists": []},
            "contributing_tracks": [],
        }
        rationale.append(generic)
    return texts, rationale


def _build_rationale(
    text: str,
    *,
    based_on: dict,
    ordered: list[dict],
    artists_genres: dict[str, list[str]],
    taste,
    match_genre: str | None = None,
    match_decade: str | None = None,
    match_artist: str | None = None,
    limit: int = 10,
) -> RationaleEntry:
    """Escolhe até `limit` tracks que matcham o critério e compõe RationaleEntry."""
    contributing: list[TrackRationale] = []
    for t in ordered:
        if len(contributing) >= limit:
            break
        artists = t.get("artists") or []
        first_artist = (artists[0].get("name") if artists else "") or ""

        matched = False
        if match_genre:
            for a in artists:
                aid = a.get("id")
                if aid and match_genre.lower() in [
                    g.lower() for g in artists_genres.get(aid, [])
                ]:
                    matched = True
                    break
        if match_decade and _decade_of(t.get("release_date", "")) == match_decade:
            matched = True
        if match_artist and first_artist == match_artist:
            matched = True
        if not matched:
            continue

        uri = t.get("uri", "")
        profile_track = taste.data.get("tracks", {}).get(uri, {})
        track_item: TrackRationale = {
            "uri": uri,
            "name": t.get("name") or "",
            "artist": first_artist,
            "weight": 0.0,
            "feedback": profile_track.get("feedback"),
            "skip_count": profile_track.get("skip_count", 0) or 0,
        }
        contributing.append(track_item)
    entry: RationaleEntry = {
        "text": text,
        "based_on": based_on,
        "contributing_tracks": contributing,
    }
    return entry


def _persist_rationale(rationale_entries: list[RationaleEntry]) -> Path:
    """Persiste as rationale entries em state_dir/onboard_rationale.json.

    Sobrescreve a cada chamada (lifetime = último onboard).
    Retorna a Path do arquivo.
    """
    from datetime import datetime
    path = storage.state_dir() / "onboard_rationale.json"
    payload = {
        "generated_at": datetime.now(UTC).astimezone().isoformat(
            timespec="seconds",
        ),
        "suggestions": list(rationale_entries),
    }
    storage.atomic_write_json(path, payload)
    return path


def _resolve_playlist_name(sp, desired: str) -> str:
    """Se já existe playlist com esse nome, acrescenta sufixo numérico."""
    try:
        existing = sp.current_user_playlists(limit=50).get("items", [])
    except MaestraError:
        raise  # AuthError/RateLimit/API → pipeline central (cli/__init__.py:246)
    except Exception:
        return desired  # shape inesperada da API → fallback benigno
    existing_names = {p.get("name") for p in existing}
    if desired not in existing_names:
        return desired
    n = 2
    while f"{desired} ({n})" in existing_names:
        n += 1
    return f"{desired} ({n})"


_TOTAL_CAP_DEFAULT = 5000


def _build_top_100_for_enhancement(
    *,
    top_long: list[dict],
    saved: list[dict],
    recent: list[dict],
    weights: dict,
) -> list[dict]:
    """Monta lista ordenada por weight, até 100 itens. Deduplica por URI."""
    seen: set[str] = set()
    unified: list[dict] = []
    for pool in (top_long, saved, recent):
        for t in pool:
            uri = t.get("uri")
            if not uri or uri in seen:
                continue
            seen.add(uri)
            unified.append(t)
    unified.sort(key=lambda t: weights.get(t.get("uri", ""), 0.0), reverse=True)
    return unified[:100]


def _to_track_info_for_enhancer(t: dict) -> dict:
    """Adapta dict de track do spotipy para TrackInfo."""
    first_spotify_aid = next(
        (a.get("id") for a in (t.get("artists") or []) if a.get("id")),
        None,
    )
    return {
        "uri": t.get("uri", ""),
        "name": t.get("name") or "",
        "artists": [a.get("name", "") for a in (t.get("artists") or []) if a.get("name")],
        "isrc": ((t.get("external_ids") or {}).get("isrc")),
        "spotify_artist_id": first_spotify_aid,
    }


def _emit_mb_summary(enhanced_tracks: list, *, console) -> None:
    """Resumo pós-enhancement: conta tracks com metadata MB não-vazio."""
    with_mb = sum(
        1 for t in enhanced_tracks
        if t.get("musicbrainz") and (t["musicbrainz"].get("genres") or t["musicbrainz"].get("tags"))
    )
    console.print(
        f"\n[bold]Melhoramento externo (MusicBrainz):[/bold] "
        f"{with_mb} de {len(enhanced_tracks)} faixas com gêneros/tags canônicos.",
    )


def _aggregate_tags_from_enhanced(
    enhanced: dict,
    track_info: dict,
    artists_tags: dict[str, list[str]],
) -> None:
    """Agrega tags MB + tags Last.fm (dedup, preserva ordem) por artist_id Spotify."""
    mb_tags = (enhanced.get("musicbrainz") or {}).get("tags") or []
    lf_tags = (enhanced.get("lastfm") or {}).get("top_tags") or []
    combined: list[str] = []
    seen: set[str] = set()
    for tag in list(mb_tags) + list(lf_tags):
        t = (tag or "").strip()
        if not t or t.lower() in seen:
            continue
        seen.add(t.lower())
        combined.append(t)
    for artist in track_info.get("artists") or []:
        aid = artist.get("id")
        if not aid:
            continue
        existing = artists_tags.get(aid, [])
        existing_lower = {t.lower() for t in existing}
        merged = list(existing)
        for t in combined:
            if t.lower() not in existing_lower:
                merged.append(t)
                existing_lower.add(t.lower())
        artists_tags[aid] = merged


def _emit_lf_summary(report: dict, *, console) -> None:
    """Resumo pós-enhancement: métricas Last.fm."""
    lf_matched = report.get("external_lf_matched", 0)
    lf_with_tags = report.get("external_lf_with_tags", 0)
    if lf_matched:
        console.print(f"  • Last.fm — {lf_matched} faixas casadas, {lf_with_tags} com tags ricas.")


def run(
    sp,
    taste,
    *,
    playlist_name: str,
    seed_count: int = 30,
    dry_run: bool = False,
    progress_cb: Callable | None = None,
    saved_cap: int | None = None,
    existing_playlist_id: str | None = None,
    total_cap: int = _TOTAL_CAP_DEFAULT,
    playlist_selector: PlaylistSelector | None = None,
    skip_library: bool = False,
    skip_long_term: bool = False,
    skip_medium_term: bool = False,
    skip_playlist_creation: bool = False,
    enhance_external: bool = True,
) -> dict:
    """Executa onboarding. Retorna relatório estruturado.

    ## Parâmetros

    - `saved_cap`: override do cap de Liked Songs. Se None, usa `_MAX_SAVED`.
      Para segurança, o valor é clampeado a `min(saved_cap, _MAX_SAVED * 2)`.

    - `existing_playlist_id`: v0.4.5 parte 2 — se passado, pula a criação
      de playlist e reaproveita a existente como buffer. Nome é obtido via
      `sp.playlist(..., fields="name")` apenas para relatório.

    - `total_cap`: teto desejado para total de faixas únicas
      pontuadas. Default 5000.

    - `playlist_selector`: callback opcional que decide quais
      playlists do usuário entram na expansão. Veja "Expansão" abaixo.

    ## Expansão por playlists próprias

    Executada entre recent e análise quando TODAS estas condições são
    verdadeiras:
    - `playlist_selector is not None`
    - `current_total_unique < total_cap`

    O selector recebe `list[dict(id, name, track_count)]` filtrada por
    `owner.id == me.id` e já sem playlists vazias. Retornar `[]` pula
    a expansão (`reason="selector_returned_empty"`). Exceções do
    selector propagam — não são engolidas.

    ## Semântica de pesos

    Cada URI contribui com a SOMA dos pesos das fontes em que aparece:
    - `long_term`=3, `medium_term`=2, `short_term`=2
    - `saved` (Liked Songs ❤️)=3
    - `recent`=1
    - `playlist`=2 — **aplicado uma única vez** por URI,
      mesmo que apareça em múltiplas playlists do usuário (dedup por
      `seen` set). Exemplo: faixa em top_long + duas playlists do
      usuário = 3 (long) + 2 (playlist) = 5, não 3 + 2 + 2 = 7.

    ## expansion_info no report

    Campo `reason` sempre preenchido com vocabulário fechado:
    - `selector_not_provided` — selector=None
    - `cap_already_reached` — total já cobria o cap antes da oferta
    - `no_own_playlists` — usuário sem playlists próprias utilizáveis
    - `selector_returned_empty` — selector retornou []
    - `ok` — expansão concluída com tracks_added > 0

    Campo `failed_playlists` lista `{id, reason}` para playlists em
    que `_fetch_playlist_tracks` falhou (race, timeout, 401 parcial).
    """
    # Resolução do cap efetivo para Liked Songs.
    if saved_cap is None:
        effective_cap = _MAX_SAVED
    else:
        effective_cap = min(saved_cap, _MAX_SAVED * 2)

    # v0.8.0-alpha.3: buffer local de warnings (falhas parciais toleradas
    # que o user precisa conhecer no report final). Preferível a global/
    # thread-local — mantém run() reentrante.
    warnings: list[str] = []

    def report_step(step, name, detail=None):
        if progress_cb:
            ev = {"step": step, "name": name}
            if detail:
                ev["detail"] = detail
            progress_cb(ev)

    # Step 1: auth (sp já autenticado; confirma com call barata)
    report_step(1, "Autenticação")
    # call barata para validar token; se falhar, _call_spotify levanta AuthError
    sp.current_user()

    # Step 2: playlist (cria nova ou reaproveita existente)
    # v0.8.0: skip_playlist_creation=True pula criação/resolução (fluxo C
    # de re-análise pura). playlist_id fica None no report.
    report_step(2, "Playlist", detail=playlist_name)
    playlist_id = None
    effective_name = playlist_name
    if skip_playlist_creation:
        pass
    elif existing_playlist_id:
        # Reaproveita playlist já existente; busca nome para relatório.
        playlist_id = existing_playlist_id
        try:
            pl_meta = sp.playlist(existing_playlist_id, fields="name")
            current_name = (pl_meta or {}).get("name") or existing_playlist_id
        except Exception:
            current_name = existing_playlist_id

        # v0.5.2 (bug 5): se usuário passar --playlist-name junto com
        # --playlist-id e o nome atual da playlist diferir, renomeia no
        # Spotify. Caso típico: usuário cria playlist no app Spotify que
        # fica com nome default "My Playlist #N" e quer chamá-la "Maestra".
        if playlist_name and playlist_name != current_name and not dry_run:
            try:
                sp.playlist_change_details(existing_playlist_id, name=playlist_name)
                effective_name = playlist_name
            except Exception:
                # Rename falhou (permissão, Development Mode) — mantém nome
                # atual. Não bloqueia o onboard.
                effective_name = current_name
        else:
            effective_name = current_name

        if not dry_run:
            cfg = load_and_migrate()
            cfg["playlist_id"] = playlist_id
            cfg["playlist_name"] = effective_name
            storage.write_config(cfg)
    elif not dry_run:
        effective_name = _resolve_playlist_name(sp, playlist_name)
        me = sp.current_user()
        try:
            new_pl = sp.user_playlist_create(
                me["id"],
                effective_name,
                public=False,
                description="Buffer de curadoria da Maestra.",
            )
        except Exception as e:
            # v0.5.2: 403 aqui é quase sempre Development Mode / User Management.
            # Inspeciona string da exceção (spotipy.SpotifyException formata assim).
            status = getattr(e, "http_status", None) or getattr(e, "status", None)
            msg = str(e)
            if status == 403 or "403" in msg:
                raise PlaylistCreateForbiddenError(
                    f"Spotify retornou 403 ao criar a playlist '{effective_name}' "
                    f"para o usuário '{me.get('id')}'.",
                    status=403,
                    where={
                        "user_id": me.get("id"),
                        "email": me.get("email"),
                        "country": me.get("country"),
                        "product": me.get("product"),
                        "playlist_name": effective_name,
                    },
                ) from e
            raise
        playlist_id = new_pl["id"]
        cfg = load_and_migrate()
        cfg["playlist_id"] = playlist_id
        cfg["playlist_name"] = effective_name
        storage.write_config(cfg)

    # Step 3: top tracks (3 janelas)
    # v0.8.0: skip_long_term / skip_medium_term permitem pular janelas
    # individualmente (fluxo C mode=recent_mood usa só short_term).
    report_step(3, "Top tracks (3 janelas)")
    top_long = [] if skip_long_term else _fetch_top_window(sp, "long_term")
    top_medium = [] if skip_medium_term else _fetch_top_window(sp, "medium_term")
    top_short = _fetch_top_window(sp, "short_term")

    # Step 4: biblioteca
    # v0.8.0: skip_library=True pula _fetch_saved (sem tocar no spotipy).
    report_step(4, "Biblioteca (saved tracks)")
    if skip_library:
        saved = []
    else:
        saved = _fetch_saved(
            sp,
            progress_cb=(lambda n: report_step(4, "Biblioteca", f"{n}/{effective_cap}"))
            if progress_cb else None,
            max_tracks=effective_cap,
        )

    # Step 5: recently played
    report_step(5, "Recently played")
    recent = _fetch_recent(sp)

    # v0.5.3 Step 6: expansão via playlists próprias (opcional)
    # Aplica apenas se:
    #   - total atual < total_cap
    #   - playlist_selector fornecido
    # Core delega 100% da decisão ao selector (CLI decide UX). Se selector
    # retornar [], pula silenciosamente.
    playlist_tracks: list[dict] = []
    # v0.5.6 #10: `reason` sempre preenchido com um dos valores de vocabulário
    # fechado para simplificar consumidores (CLI, agentes via --json):
    #   - "selector_not_provided": playlist_selector=None (expansão pulada)
    #   - "cap_already_reached":   total atual >= total_cap antes da oferta
    #   - "no_own_playlists":      selector chamou mas usuário não tem
    #                               playlists próprias utilizáveis
    #   - "selector_returned_empty": selector rodou e retornou []
    #   - "only_empty_playlists":    v0.5.7 — usuário tem N playlists
    #                                 próprias mas todas com track_count=0
    #   - "ok":                     expansão concluída (tracks_added > 0)
    expansion_info: ExpansionInfo = {
        "attempted": False,
        "offered_playlists": 0,
        "own_playlists_empty_count": 0,
        "selected_playlists": [],
        "tracks_added": 0,
        "reason": "selector_not_provided",
        # v0.5.5 #6-#7: rastreamento de falhas parciais durante fetch.
        "failed_playlists": [],
    }
    current_total_unique = len({t.get("uri") for t in
                                 (top_long + top_medium + top_short + saved + recent)
                                 if t.get("uri")})
    if playlist_selector is None:
        pass  # expansion_info["reason"] já é "selector_not_provided"
    elif current_total_unique >= total_cap:
        # v0.5.6 #10: caso explícito — agentes programáticos querem
        # distinguir "não chamei" (selector None) de "chamei mas cap
        # já estava cheio".
        expansion_info["reason"] = "cap_already_reached"
    else:
        # Mesmo step que a análise (6), com detail para não quebrar o
        # contrato de "6 etapas" com consumidores.
        report_step(6, "Expansão por playlists (opcional)")
        try:
            me = sp.current_user()
            own_playlists, empty_count = _fetch_own_playlists(
                sp, me_id=me.get("id"),
                progress_cb=(
                    lambda n: report_step(6, "Listando playlists", f"{n}")
                ) if progress_cb else None,
            )
        except MaestraError:
            raise  # AuthError/RateLimit/API → pipeline central
        except Exception:
            own_playlists, empty_count = [], 0  # shape inesperada → fallback
        expansion_info["attempted"] = True
        expansion_info["offered_playlists"] = len(own_playlists)
        # v0.5.7 #17: expõe contagem para CLI distinguir "nenhuma playlist
        # própria" de "playlists próprias existem mas todas estão vazias".
        expansion_info["own_playlists_empty_count"] = empty_count
        if not own_playlists:
            expansion_info["reason"] = (
                "only_empty_playlists" if empty_count > 0
                else "no_own_playlists"
            )
        else:
            ctx: ExpansionContext = {
                "total_cap": total_cap,
                "current_total": current_total_unique,
                "remaining": total_cap - current_total_unique,
            }
            selected_ids = playlist_selector(own_playlists, ctx) or []
            # v0.5.7 #19: guarda objetos {id, name} em vez de só IDs.
            # Relatórios humanos e JSON podem mostrar nomes sem precisar
            # refazer lookup na API.
            name_by_id = {p["id"]: p.get("name", p["id"]) for p in own_playlists}
            selected: list[SelectedPlaylist] = [
                {"id": pid, "name": name_by_id.get(pid, pid)}
                for pid in selected_ids
            ]
            expansion_info["selected_playlists"] = selected
            if selected_ids:
                # URIs já vistos, para não duplicar trabalho de fetch nem
                # inflar artificialmente o contador
                seen = {t.get("uri") for t in
                         (top_long + top_medium + top_short + saved + recent)
                         if t.get("uri")}
                remaining = total_cap - len(seen)
                for pid in selected_ids:
                    if remaining <= 0:
                        break
                    try:
                        tracks = _fetch_playlist_tracks(
                            sp, pid, max_tracks=remaining,
                        )
                    except Exception as fetch_err:
                        # v0.5.5 #6-#7: registra a falha sem abortar a
                        # expansão. Truncamento em 80 chars evita explodir
                        # o report com stack traces longos.
                        failed: FailedPlaylist = {
                            "id": pid,
                            "reason": str(fetch_err)[:80],
                        }
                        expansion_info["failed_playlists"].append(failed)
                        continue
                    for t in tracks:
                        uri = t.get("uri")
                        if uri and uri not in seen:
                            seen.add(uri)
                            playlist_tracks.append(t)
                            remaining -= 1
                            if remaining <= 0:
                                break
                expansion_info["tracks_added"] = len(playlist_tracks)
                # v0.5.6 #10: reason explícito no caminho feliz.
                # Core usa "selector_returned_empty" em vez de "user_skipped"
                # (termo de UI não pertence ao core — CLI traduz se quiser).
                expansion_info["reason"] = "ok"
            else:
                expansion_info["reason"] = "selector_returned_empty"

    # Step 6: análise + semeadura
    report_step(6, "Análise local e semeadura")
    weights = _compute_weights(
        top_long=top_long, top_medium=top_medium, top_short=top_short,
        saved=saved, recent=recent,
    )
    # Peso playlist (v0.5.3): soma 2 para cada URI nas playlists escolhidas.
    # A soma acumula com outras fontes (ex: faixa em top_long + playlist = 5).
    for t in playlist_tracks:
        uri = t.get("uri")
        if uri:
            weights[uri] = weights.get(uri, 0) + WEIGHTS["playlist"]

    # v0.7.0: index enriquecido com release_date e artist IDs para
    # permitir que _derive_suggestions agregue década e resolva gêneros.
    index: dict[str, dict] = {}
    for t in top_long + top_medium + top_short + saved + recent + playlist_tracks:
        uri = t.get("uri")
        if not uri or uri in index:
            continue
        artists = t.get("artists") or []
        norm_artists = [
            {"id": a.get("id"), "name": a.get("name")}
            for a in artists if a.get("name")
        ]
        release_date = ""
        album = t.get("album") or {}
        if isinstance(album, dict):
            release_date = album.get("release_date") or ""
        index[uri] = {
            "uri": uri,
            "name": t.get("name"),
            "artists": norm_artists,
            "release_date": release_date,
        }

    if not dry_run:
        for uri, score in weights.items():
            t = index.get(uri, {})
            artists = t.get("artists") or []
            artist_name = artists[0].get("name") if artists else None
            taste.record_global_positive(
                uri,
                name=t.get("name"),
                artist=artist_name,
                weight=score,
            )

    seeded = 0
    if not dry_run and seed_count > 0 and playlist_id:
        seed_uris = [t["uri"] for t in top_short[:seed_count]]
        if seed_uris:
            sp.playlist_add_items(playlist_id, seed_uris)
            seeded = len(seed_uris)

    # v0.7.0: sugestões inteligentes com taste + gêneros + rationale
    tracks_list = list(index.values())
    adjusted_weights = _apply_taste_to_weights(
        {uri: float(w) for uri, w in weights.items()},
        tracks_list,
        taste,
    )
    # G1: artists_genres é preenchido pelo MB após enhance_many (Spotify depreciou /v1/artists genres em 2025)
    artists_genres: dict[str, list[str]] = {}
    artists_tags: dict[str, list[str]] = {}

    external_enhanced_count = 0
    external_sources_used: list[str] = []
    external_mb_with_genres = 0
    external_mb_matched = 0
    external_mb_artist_resolved = 0
    external_mb_with_tags_only = 0
    external_lf_matched = 0
    external_lf_with_tags = 0
    external_rb_matched = 0
    cfg = load_and_migrate()
    if any_source_enabled(cfg) and enhance_external:
        from maestra_ai.core.external import default_enhancer
        enhancer = default_enhancer()
        active = enhancer.active_sources()
        if active:
            top_100 = _build_top_100_for_enhancement(
                top_long=top_long, saved=saved, recent=recent,
                weights=adjusted_weights,
            )
            track_infos = [_to_track_info_for_enhancer(t) for t in top_100]
            enhanced = enhancer.enhance_many(
                track_infos,
                progress_cb=(
                    lambda ev: progress_cb({
                        "step": -1, "name": "external",
                        "detail": ev.get("detail") or "",
                    })
                ) if progress_cb else None,
            )
            external_enhanced_count = len(enhanced)
            external_sources_used = active

            # G2: métricas granulares do MB para diagnóstico + exibição
            external_mb_matched = sum(
                1 for t in enhanced if t.get("musicbrainz")
            )
            external_mb_artist_resolved = sum(
                1 for t in enhanced if t.get("artist_mbid")
            )
            external_mb_with_genres = sum(
                1 for t in enhanced
                if t.get("musicbrainz") and t["musicbrainz"].get("genres")
            )
            external_mb_with_tags_only = sum(
                1 for t in enhanced
                if t.get("musicbrainz")
                and not t["musicbrainz"].get("genres")
                and t["musicbrainz"].get("tags")
            )

            # G1: artists_genres agora vem do MB (via spotify_artist_id),
            # não mais do Spotify /v1/artists (que foi depreciado).
            # G3: artists_tags agrega MB tags + Last.fm top_tags via helper.
            external_lf_matched = sum(
                1 for t in enhanced if t.get("lastfm")
            )
            external_lf_with_tags = sum(
                1 for t in enhanced
                if t.get("lastfm") and (t["lastfm"].get("top_tags") or [])
            )
            external_rb_matched = sum(
                1 for t in enhanced
                if t.get("reccobeats") and t["reccobeats"].get("tempo")
            )
            for t_info, enhanced_track in zip(track_infos, enhanced, strict=False):
                spotify_aid = t_info.get("spotify_artist_id")
                mb = enhanced_track.get("musicbrainz") or {}
                mb_genres = mb.get("genres") or []
                if spotify_aid and mb_genres:
                    artists_genres[spotify_aid] = mb_genres
                # Agrega tags MB + LF via helper (dedup, preserva ordem).
                # t_info usa spotify_artist_id (string), convertemos para shape
                # compatível com o helper {artists: [{id: ...}]}.
                aid_track_info = {"artists": [{"id": spotify_aid}]} if spotify_aid else {}
                _aggregate_tags_from_enhanced(enhanced_track, aid_track_info, artists_tags)

    sorted_tracks = sorted(
        [t for t in tracks_list if t.get("uri") in adjusted_weights],
        key=lambda t: adjusted_weights.get(t.get("uri", ""), 0),
        reverse=True,
    )
    suggestions, rationale_entries, signals = _derive_suggestions(
        sorted_tracks, adjusted_weights, artists_genres, taste,
        artists_tags=artists_tags,
    )
    rationale_path = _persist_rationale(rationale_entries)

    return {
        "status": "ok",
        "playlist_id": playlist_id,
        "playlist_name": effective_name,
        "top_long_count": len(top_long),
        "top_medium_count": len(top_medium),
        "top_short_count": len(top_short),
        "saved_tracks_fetched": len(saved),
        "recent_count": len(recent),
        "playlist_expansion": expansion_info,
        "unique_tracks_scored": len(weights),
        "seeded": seeded,
        "context_suggestions": suggestions,
        "signals": signals,
        "rationale_path": str(rationale_path),
        "warnings": warnings,
        "external_enhanced_count": external_enhanced_count,
        "external_sources_used": external_sources_used,
        "external_mb_with_genres": external_mb_with_genres,
        "external_mb_matched": external_mb_matched,
        "external_mb_artist_resolved": external_mb_artist_resolved,
        "external_mb_with_tags_only": external_mb_with_tags_only,
        "external_lf_matched": external_lf_matched,
        "external_lf_with_tags": external_lf_with_tags,
        "external_rb_matched": external_rb_matched,
    }
