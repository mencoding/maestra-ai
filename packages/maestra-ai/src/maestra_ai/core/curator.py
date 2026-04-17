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


class Curator:
    """Traduz contexto em queries de busca e retorna URIs filtradas."""

    def __init__(self, controller, taste):
        self.controller = controller
        self.taste = taste

    def curate(self, context, count=5, exclude_uris=None, exclude_artists=None, max_per_artist=None):
        """Gera lista de faixas para um contexto.

        Retorna tupla (tracks, queries_used).
        tracks: lista de dicts com track, artist, uri.
        queries_used: lista de queries efetivamente usadas.
        """
        context = self._normalize_context(context)
        queries = self._resolve_queries(context)
        candidates = []
        excluded = set(exclude_uris or [])
        excluded_artists = set(exclude_artists or [])
        seen_uris = set(excluded)
        search_limit = max(count, count + len(excluded), 10)

        for query in queries:
            results = self.controller.search(query, type="track", limit=search_limit)
            for r in results:
                if r["uri"] not in seen_uris:
                    seen_uris.add(r["uri"])
                    candidates.append(r)
                if len(candidates) >= search_limit:
                    break
            if len(candidates) >= search_limit:
                break

        # Filtra rejeitadas pelo perfil de gosto
        filtered = []
        for c in candidates:
            if self.taste._is_rejected(c["uri"]):
                continue
            if self.taste.context_score(c["uri"], context) < 0:
                continue
            if c["artist"] in excluded_artists:
                continue
            filtered.append(c)

        # Filtra por artistas rejeitados
        rejected_artists = set(self.taste.get_rejected_artists())
        filtered = [
            c for c in filtered
            if c["artist"] not in rejected_artists
        ]

        filtered.sort(
            key=lambda c: self.taste.context_score(c["uri"], context),
            reverse=True,
        )

        if max_per_artist:
            limited = []
            artist_counts = {}
            for track in filtered:
                artist = track["artist"]
                if artist_counts.get(artist, 0) >= max_per_artist:
                    continue
                artist_counts[artist] = artist_counts.get(artist, 0) + 1
                limited.append(track)
                if len(limited) >= count:
                    break
            return limited, queries

        return filtered[:count], queries

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
