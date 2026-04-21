"""Curator — traduz contexto livre em buscas e retorna faixas filtradas."""

# Tabela semântica: palavras-chave → queries de busca
SEMANTIC_MAP = {
    "foco": ["lo-fi instrumental", "ambient study", "minimal piano", "post-rock instrumental"],
    "concentração": ["lo-fi instrumental", "ambient study", "minimal piano"],
    "energia": ["epic orchestral", "power metal", "eurobeat", "industrial beats"],
    "motivação": ["epic orchestral", "motivational soundtrack", "power metal"],
    "relaxar": ["acoustic chill", "ambient piano", "jazz trio"],
    "descanso": ["acoustic chill", "ambient piano", "lo-fi chill"],
    "épico": ["epic soundtrack", "cinematic orchestral", "two steps from hell"],
    "grandioso": ["epic soundtrack", "cinematic orchestral"],
    "código": ["synthwave", "chiptune", "electronic focus"],
    "programação": ["synthwave", "chiptune", "electronic focus"],
    "ambiente": ["ambient", "dark ambient", "atmospheric"],
    "batalha": ["epic battle music", "power metal", "orchestral metal"],
    "medieval": ["medieval folk", "bardcore", "celtic music"],
    "space": ["space ambient", "synthwave", "cosmic electronic"],
    "industrial": ["industrial metal", "industrial beats", "ebm"],
}

DESCRIPTOR_MAP = {
    "neoclássico": "neoclassical",
    "neoclassico": "neoclassical",
    "minimalista": "minimal",
    "minimal": "minimal",
    "ambient": "ambient",
    "denso": "dark",
    "analítico": "study",
    "analitico": "study",
    "concentrado": "focus",
    "instrumental": "instrumental",
}

# Palavras que indicam referência direta (prefixos comuns)
DIRECT_PREFIXES = ["mais ", "tipo ", "algo tipo ", "parecido com ", "como "]
DEFAULT_CONTEXT = "foco"
MIN_CANDIDATES = 10


class Curator:
    """Traduz contexto em queries de busca e retorna URIs filtradas."""

    def __init__(self, controller, taste):
        self.controller = controller
        self.taste = taste

    def _build_informed_query(self, context: str) -> str | None:
        """Monta query "{tag_dominante} {mood} {decade}" a partir de tags do perfil.

        v0.10.0-alpha.1: stub mínimo (retorna None). Cascade cai direto no
        SEMANTIC_MAP. A derivação real via conjunto_positivo virá quando
        houver uso suficiente para calibrar.
        """
        return None

    def _active_sources(self) -> list[str]:
        from maestra_ai.core.config import load_and_migrate
        cfg = load_and_migrate()
        ext = cfg.get("external_sources") or {}
        return [s for s in ("musicbrainz", "lastfm", "reccobeats") if (ext.get(s) or {}).get("enabled")]

    def curate(self, context, count=5, exclude_uris=None, exclude_artists=None, max_per_artist=None):
        """Gera lista de faixas para um contexto.

        Retorna tupla (tracks, queries_used, sources_used).
        tracks: lista de dicts com track, artist, uri.
        queries_used: lista de queries efetivamente usadas.
        sources_used: lista de fontes externas ativas.
        """
        context = self._normalize_context(context)
        queries_used: list[str] = []
        candidates: list[dict] = []
        excluded = set(exclude_uris or [])
        excluded_artists = set(exclude_artists or [])
        seen: set[str] = set(excluded)
        search_limit = max(count, count + len(excluded), 10)

        def _search_and_collect(query: str) -> None:
            queries_used.append(query)
            results = self.controller.search(query, type="track", limit=search_limit)
            for r in results:
                if r["uri"] in seen:
                    continue
                seen.add(r["uri"])
                candidates.append(r)

        # 1) Query informada
        informed = self._build_informed_query(context)
        if informed:
            _search_and_collect(informed)

        # 2) Fallback SEMANTIC_MAP se abaixo do mínimo
        if len(candidates) < MIN_CANDIDATES:
            for q in self._resolve_queries(context):
                if q in queries_used:
                    continue
                _search_and_collect(q)
                if len(candidates) >= MIN_CANDIDATES:
                    break

        # 3) Filtra rejeitadas pelo perfil de gosto (URI + context_score + artistas excluídos pelo caller)
        filtered = []
        for c in candidates:
            if self.taste.is_rejected(c["uri"]):
                continue
            if self.taste.context_score(c["uri"], context) < 0:
                continue
            if c["artist"] in excluded_artists:
                continue
            filtered.append(c)

        # Filtra por artistas rejeitados no perfil (delegação ao TasteProfile)
        filtered = self.taste.filter_with_artist_info(filtered)

        # 4) Re-rank por compose_score (taste + decade + tag + bpm ponderados)
        from maestra_ai.core.config import load_and_migrate, load_curate_weights
        cfg = load_and_migrate()
        weights = load_curate_weights(cfg)
        has_lf = (cfg.get("external_sources") or {}).get("lastfm", {}).get("enabled", False)

        filtered.sort(
            key=lambda c: self._compose_score_for(c, context, weights, has_lf),
            reverse=True,
        )

        # 5) max_per_artist
        if max_per_artist:
            limited: list[dict] = []
            counts: dict[str, int] = {}
            for t in filtered:
                a = t["artist"]
                if counts.get(a, 0) >= max_per_artist:
                    continue
                counts[a] = counts.get(a, 0) + 1
                limited.append(t)
            filtered = limited

        return filtered[:count], queries_used, self._active_sources()

    def _dominant_decades(self) -> set[str]:
        """Carrega décadas dominantes globais do profile.json (onboard)."""
        try:
            from maestra_ai.core import storage
            path = storage.data_dir() / "profile.json"
            import json
            if path.exists():
                data = json.loads(path.read_text()) or {}
                return set(data.get("dominant_decades") or [])
        except Exception:
            pass
        return set()

    def _track_tags(self, track: dict) -> set[str]:
        """Tags do artista via cache external (MB + LF se presente).

        v0.10.0-alpha.1: simplificado — retorna vazio (contribui 0 no score
        via tag_similarity). Integração rica com enhancement cache virá
        quando houver demanda de calibração real.
        """
        return set()

    def _context_tags(self, context: str) -> set[str]:
        """Tags do contexto derivadas de MOOD_TAG_KEYWORDS."""
        from maestra_ai.core.external.mood_mappings import MOOD_TAG_KEYWORDS
        ctx_lower = context.lower()
        return {kw for kw in MOOD_TAG_KEYWORDS if kw in ctx_lower}

    def _track_bpm(self, uri: str) -> float | None:
        """Retorna tempo (BPM) cacheado via Reccobeats para `uri` ou None."""
        from maestra_ai.core.external import cache as cache_mod
        track = cache_mod.get_track(uri)
        if not track:
            return None
        rb_data = track.get("reccobeats")
        if not rb_data:
            return None
        tempo = rb_data.get("tempo")
        try:
            return float(tempo) if tempo else None
        except (ValueError, TypeError):
            return None

    def _active_bpm_target(self) -> dict | None:
        """Retorna o target de BPM do contexto ativo ({min, max}) ou None."""
        from maestra_ai.core import storage
        from maestra_ai.core.context import ContextState
        path = storage.data_dir() / "context.json"
        state = ContextState(path)
        data = state.show()
        if not data:
            return None
        ctx = data.get("context") or {}
        return ctx.get("bpm")

    def _compose_score_for(self, track: dict, context: str, weights: dict, has_lastfm: bool) -> float:
        from maestra_ai.core.scoring import (
            bpm_proximity,
            compose_score,
            decade_match,
            effective_weights,
            tag_similarity,
        )
        dominant = self._dominant_decades()
        t_tags = self._track_tags(track)
        c_tags = self._context_tags(context)
        tag = tag_similarity(t_tags, c_tags)
        dec = decade_match(track.get("release_date"), dominant)
        bpm_target = self._active_bpm_target()
        track_bpm = self._track_bpm(track["uri"])
        bpm = bpm_proximity(track_bpm=track_bpm, target=bpm_target)
        taste_score = max(-1.0, min(1.0, self.taste.context_score(track["uri"], context)))
        w = effective_weights(
            weights,
            has_lastfm=has_lastfm,
            has_bpm_target=bool(bpm_target),
            track_has_bpm=track_bpm is not None,
            has_decade=bool(dominant),
        )
        return compose_score(weights=w, taste=taste_score, tag=tag, decade=dec, bpm=bpm)

    def _resolve_queries(self, context):
        """Resolve contexto em lista de queries de busca.

        Cascata:
        1. Referência direta → busca literal
        2. Mapeamento aprendido → queries do TasteProfile
        3. Mapeamento semântico → tabela estática
        4. Fallback → contexto literal
        """
        context_lower = self._normalize_context(context).lower().strip()

        # 1. Referência direta
        for prefix in DIRECT_PREFIXES:
            if context_lower.startswith(prefix):
                return [context_lower[len(prefix):]]

        # 2. Mapeamento aprendido
        learned = self.taste.get_successful_queries(context_lower)
        if learned:
            return learned

        # 3. Contexto composto: preserva descritores específicos antes da tabela geral.
        descriptor_query = self._descriptor_query(context_lower)
        if descriptor_query:
            semantic_queries = []
            for keyword, mapped_queries in SEMANTIC_MAP.items():
                if keyword in context_lower:
                    semantic_queries.extend(mapped_queries)
            return list(dict.fromkeys([descriptor_query, context_lower, *semantic_queries]))

        # 4. Mapeamento semântico
        for keyword, queries in SEMANTIC_MAP.items():
            if keyword in context_lower:
                return queries

        # 5. Fallback: usa o contexto literal como query
        return [context_lower]

    def _descriptor_query(self, context_lower):
        """Converte contextos compostos em query musical mais especifica."""
        descriptors = [
            query_token
            for token, query_token in DESCRIPTOR_MAP.items()
            if token in context_lower
        ]
        descriptors = list(dict.fromkeys(descriptors))
        if len(descriptors) < 2:
            return None
        return " ".join(descriptors)

    def _normalize_context(self, context):
        """Retorna contexto utilizavel quando mood veio vazio."""
        if context is None:
            return DEFAULT_CONTEXT
        context = str(context).strip()
        return context or DEFAULT_CONTEXT

    def prune(self, *, playlist_id, context, confirm=False, top=20):
        """Remove da playlist faixas com sinal contextual negativo ou global bad.

        Dry-run por padrão (confirm=False). Em execução real, cria snapshot
        automático antes de remover.
        """
        from maestra_ai.core import snapshot
        from maestra_ai.core import taste as taste_mod

        tracks = self.controller.playlist_tracks(playlist_id)
        candidates = taste_mod.prune_candidates(tracks, self.taste, context)

        if not confirm:
            return {
                "dry_run": True,
                "context": context,
                "candidates": candidates[:top],
                "total_candidates": len(candidates),
                "removed": 0,
            }

        # Execução real
        state = {
            "playlist_tracks": tracks,
            "context": context,
            "taste_snapshot": self.taste.data,
        }
        snap_id = snapshot.create("prune", state)

        uris = [c["uri"] for c in candidates]
        if uris:
            self.controller.playlist_remove(playlist_id, uris)

        return {
            "dry_run": False,
            "context": context,
            "removed": len(uris),
            "snapshot_id": snap_id,
            "uris_removed": uris,
        }
