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
from maestra_ai.core.errors import PlaylistCreateForbiddenError
from maestra_ai.core.onboard_types import (
    ExpansionContext,
    ExpansionInfo,
    FailedPlaylist,
    OwnPlaylist,
    PlaylistSelector,
    SelectedPlaylist,
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


_TOTAL_CAP_DEFAULT = 5000


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
) -> dict:
    """Executa onboarding. Retorna relatório estruturado.

    ## Parâmetros

    - `saved_cap`: override do cap de Liked Songs. Se None, usa `_MAX_SAVED`.
      Para segurança, o valor é clampeado a `min(saved_cap, _MAX_SAVED * 2)`.

    - `existing_playlist_id`: v0.4.5 parte 2 — se passado, pula a criação
      de playlist e reaproveita a existente como buffer. Nome é obtido via
      `sp.playlist(..., fields="name")` apenas para relatório.

    - `total_cap`: v0.5.3 — teto desejado para total de faixas únicas
      pontuadas. Default 5000.

    - `playlist_selector`: v0.5.3 — callback opcional que decide quais
      playlists do usuário entram na expansão. Veja "Expansão" abaixo.

    ## Expansão por playlists próprias (v0.5.3)

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
    - `playlist`=2 (v0.5.3) — **aplicado uma única vez** por URI,
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
            cfg = storage.read_config()
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
        except Exception:
            own_playlists, empty_count = [], 0
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
            expansion_info["selected_playlists"] = [
                {"id": pid, "name": name_by_id.get(pid, pid)}
                for pid in selected_ids
            ]
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
                        expansion_info["failed_playlists"].append({
                            "id": pid,
                            "reason": str(fetch_err)[:80],
                        })
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

    # Índice uri → track para recuperar name/artist
    index: dict[str, dict] = {}
    for t in top_long + top_medium + top_short + saved + recent + playlist_tracks:
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
        "playlist_expansion": expansion_info,
        "unique_tracks_scored": len(weights),
        "seeded": seeded,
        "context_suggestions": suggestions,
    }
