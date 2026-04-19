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

from maestra_ai.core import storage

WEIGHTS = {
    "long_term": 3,
    "medium_term": 2,
    "short_term": 2,
    "saved": 3,
    "recent": 1,
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
    """Paginação defensiva: cap `max_tracks`, para em página vazia ou parcial.

    v0.4.4 CRITICAL-4: ignora items com track=None (faixa removida do
    catálogo / indisponível na região).

    v0.4.5: `max_tracks` parametrizável (default = _MAX_SAVED = 5000).
    """
    collected: list[dict] = []
    offset = 0
    while len(collected) < max_tracks:
        resp = sp.current_user_saved_tracks(limit=_PAGE, offset=offset)
        items = resp.get("items", [])
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
        if len(items) < _PAGE:
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


def _derive_suggestions(tracks_by_weight: list[dict]) -> list[str]:
    """Deriva até 5 sugestões de contexto a partir de artistas dominantes."""
    artist_count: Counter[str] = Counter()
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


def _resolve_playlist_name(sp, desired: str) -> str:
    """Se já existe playlist com esse nome, acrescenta sufixo numérico."""
    try:
        existing = sp.current_user_playlists(limit=50).get("items", [])
    except Exception:
        return desired
    existing_names = {p.get("name") for p in existing}
    if desired not in existing_names:
        return desired
    n = 2
    while f"{desired} ({n})" in existing_names:
        n += 1
    return f"{desired} ({n})"


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
) -> dict:
    """Executa onboarding. Retorna relatório estruturado.

    `saved_cap`: override do cap de Liked Songs. Se None, usa _MAX_SAVED.
    Para segurança, o valor é clampeado a min(saved_cap, _MAX_SAVED * 2).

    `existing_playlist_id`: v0.4.5 parte 2 — se passado, pula a criação
    de playlist e reaproveita a existente como buffer. Nome é obtido via
    `sp.playlist(..., fields="name")` apenas para relatório.
    """
    # Resolução do cap efetivo para Liked Songs.
    if saved_cap is None:
        effective_cap = _MAX_SAVED
    else:
        effective_cap = min(saved_cap, _MAX_SAVED * 2)

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
    report_step(2, "Playlist", detail=playlist_name)
    playlist_id = None
    effective_name = playlist_name
    if existing_playlist_id:
        # Reaproveita playlist já existente; busca nome para relatório.
        playlist_id = existing_playlist_id
        try:
            pl_meta = sp.playlist(existing_playlist_id, fields="name")
            effective_name = (pl_meta or {}).get("name") or existing_playlist_id
        except Exception:
            effective_name = existing_playlist_id
        if not dry_run:
            cfg = storage.read_config()
            cfg["playlist_id"] = playlist_id
            cfg["playlist_name"] = effective_name
            storage.write_config(cfg)
    elif not dry_run:
        effective_name = _resolve_playlist_name(sp, playlist_name)
        me = sp.current_user()
        new_pl = sp.user_playlist_create(
            me["id"],
            effective_name,
            public=False,
            description="Buffer de curadoria da Maestra.",
        )
        playlist_id = new_pl["id"]
        cfg = storage.read_config()
        cfg["playlist_id"] = playlist_id
        cfg["playlist_name"] = effective_name
        storage.write_config(cfg)

    # Step 3: top tracks (3 janelas)
    report_step(3, "Top tracks (3 janelas)")
    top_long = _fetch_top_window(sp, "long_term")
    top_medium = _fetch_top_window(sp, "medium_term")
    top_short = _fetch_top_window(sp, "short_term")

    # Step 4: biblioteca
    report_step(4, "Biblioteca (saved tracks)")
    saved = _fetch_saved(
        sp,
        progress_cb=(lambda n: report_step(4, "Biblioteca", f"{n}/{effective_cap}"))
        if progress_cb else None,
        max_tracks=effective_cap,
    )

    # Step 5: recently played
    report_step(5, "Recently played")
    recent = _fetch_recent(sp)

    # Step 6: análise + semeadura
    report_step(6, "Análise local e semeadura")
    weights = _compute_weights(
        top_long=top_long, top_medium=top_medium, top_short=top_short,
        saved=saved, recent=recent,
    )

    # Índice uri → track para recuperar name/artist
    index: dict[str, dict] = {}
    for t in top_long + top_medium + top_short + saved + recent:
        uri = t.get("uri")
        if uri and uri not in index:
            index[uri] = t

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

    # Sugestões ordenadas por peso
    sorted_tracks = sorted(
        list(index.values()),
        key=lambda t: weights.get(t.get("uri", ""), 0),
        reverse=True,
    )
    suggestions = _derive_suggestions(sorted_tracks)

    return {
        "status": "ok",
        "playlist_id": playlist_id,
        "playlist_name": effective_name,
        "top_long_count": len(top_long),
        "top_medium_count": len(top_medium),
        "top_short_count": len(top_short),
        "saved_tracks_fetched": len(saved),
        "recent_count": len(recent),
        "unique_tracks_scored": len(weights),
        "seeded": seeded,
        "context_suggestions": suggestions,
    }
