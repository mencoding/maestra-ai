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
        return [s for s in ("musicbrainz", "lastfm", "getsongbpm") if (ext.get(s) or {}).get("enabled")]

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

        # 4) Re-rank (v0.10.0-alpha.1: ainda por context_score; integração
        #    com compose_score virá em Task 18)
        filtered.sort(
            key=lambda c: self.taste.context_score(c["uri"], context),
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
