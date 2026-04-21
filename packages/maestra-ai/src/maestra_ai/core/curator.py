"""Curator — traduz contexto livre em buscas e retorna faixas filtradas."""

import logging

# Import de módulo (não de símbolo) para permitir monkeypatch em testes de
# `_track_tags` sem exigir patch do caminho `maestra_ai.core.external.cache`.
from maestra_ai.core.external import cache as cache_mod

logger = logging.getLogger(__name__)

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

    def _build_informed_query(self, parsed) -> str | None:
        """Query informada a partir de ParsedContext + taste.

        Formato: "{artist_hint_ou_top_taste} {positive} {bpm_qualifier}".
        Skip top taste que aparecem em negative. Retorna None se nenhum sinal.
        """
        negative = set(parsed.negative) if parsed.negative else set()

        # Parte 1: artista (artist_hint tem prioridade sobre top taste)
        artist_part: str | None = None
        if parsed.artists_hint:
            artist_part = parsed.artists_hint[0]
        else:
            # Top preferred artist que não bata com negative
            top = self.taste.get_preferred_artists() or []
            for a in top[:5]:
                if not any(n in a.lower() for n in negative):
                    artist_part = a
                    break

        # Parte 2: positive (primeiro termo, se houver)
        positive_part = parsed.positive[0] if parsed.positive else None

        # Parte 3: bpm qualifier — usa atributos do BpmRange (não dict)
        bpm_part = None
        if parsed.bpm is not None and parsed.bpm.min is not None and parsed.bpm.max is not None:
            mid = (parsed.bpm.min + parsed.bpm.max) // 2
            bpm_part = f"{mid}bpm"

        # Se nenhuma parte produziu sinal, retorna None
        parts = [p for p in (artist_part, positive_part, bpm_part) if p]
        if not parts:
            return None
        return " ".join(parts)

    def _active_sources(self) -> list[str]:
        from maestra_ai.core.config import load_and_migrate
        cfg = load_and_migrate()
        ext = cfg.get("external_sources") or {}
        return [s for s in ("musicbrainz", "lastfm", "reccobeats") if (ext.get(s) or {}).get("enabled")]

    def curate(self, context, count=5, exclude_uris=None, exclude_artists=None, max_per_artist=None, enhance_candidates=True):
        """Gera lista de faixas para um contexto.

        `context` aceita `str` ou `ParsedContext` (duck-typing via `hasattr`).
        Quando `ParsedContext`, pulamos o parse (evita duplicar trabalho do caller).

        Retorna tupla (tracks, queries_used, sources_used).
        tracks: lista de dicts com track, artist, uri.
        queries_used: lista de queries efetivamente usadas.
        sources_used: lista de fontes externas ativas.
        """
        from maestra_ai.core.context_parser import parse as parse_context_text
        from maestra_ai.core.scoring import anti_tag_penalty

        # Normaliza: aceita `str` ou `ParsedContext` (duck-typing)
        if hasattr(context, "text"):
            parsed = context
            context_text = parsed.text
        else:
            context_text = self._normalize_context(context)
            parsed = parse_context_text(context_text, bpm=self._active_bpm_target())

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

        # 1) Query informada a partir do ParsedContext
        informed = self._build_informed_query(parsed)
        if informed:
            _search_and_collect(informed)

        # 2) Fallback SEMANTIC_MAP se abaixo do mínimo
        if len(candidates) < MIN_CANDIDATES:
            for q in self._resolve_queries(context_text):
                if q in queries_used:
                    continue
                _search_and_collect(q)
                if len(candidates) >= MIN_CANDIDATES:
                    break

        # 3) v0.12.0: enrich candidates com metadata externa antes do re-rank.
        # Skip se usuário passou --no-enhance (enhance_candidates=False).
        if enhance_candidates and candidates:
            from maestra_ai.core.external import default_enhancer
            from maestra_ai.core.external.types import TrackInfo

            enhancer = default_enhancer()
            if enhancer._sources:  # Só se há pelo menos 1 source ativa
                track_infos: list[TrackInfo] = []
                for c in candidates:
                    track_infos.append({
                        "uri": c["uri"],
                        "name": c.get("track", c.get("name", "Unknown")),
                        "artists": [c["artist"]],
                        "isrc": c.get("isrc"),
                    })
                try:
                    enhancer.enhance_many(track_infos)
                except Exception as e:
                    logger.warning("Enhancement de candidatos falhou: %s", e)

        # 4) Hard filter adaptativo (v0.13): remove candidatos com tag negada.
        # Se o filtro deixar < MIN_CANDIDATES, mantém originais com degraded=True
        # para o scoring aplicar penalty suave no re-rank.
        candidates, degraded = self._apply_negative_filter(candidates, parsed)

        # 5) Filtra rejeitadas pelo perfil de gosto (URI + context_score + artistas excluídos pelo caller)
        filtered = []
        for c in candidates:
            if self.taste.is_rejected(c["uri"]):
                continue
            if self.taste.context_score(c["uri"], context_text) < 0:
                continue
            if c["artist"] in excluded_artists:
                continue
            filtered.append(c)

        # Filtra por artistas rejeitados no perfil (delegação ao TasteProfile)
        filtered = self.taste.filter_with_artist_info(filtered)

        # 6) Re-rank por compose_score (taste + decade + tag + bpm ponderados).
        # Quando degraded=True, soma anti_tag_penalty para afastar candidatos com tag negada.
        from maestra_ai.core.config import load_and_migrate, load_curate_weights
        cfg = load_and_migrate()
        weights = load_curate_weights(cfg)
        has_lf = (cfg.get("external_sources") or {}).get("lastfm", {}).get("enabled", False)
        negative_set = set(parsed.negative)

        def _score(c):
            base = self._compose_score_for(c, context_text, weights, has_lf)
            if degraded and negative_set:
                base += anti_tag_penalty(
                    self._track_tags(c), negative_set, degraded=True,
                )
            return base

        filtered.sort(key=_score, reverse=True)

        # 7) max_per_artist
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
        """Tags do artista/track via cache external.

        Merge MB (canônico) + LF (filtrado via tag_filter). Retorna set vazio
        quando o cache não tem entrada pro URI ou nenhuma source populou.

        Nota sobre a shape real do cache (external_cache.json v2):
        - `musicbrainz.tags` é `list[str]` — tags canônicas entram direto.
        - `lastfm.top_tags` é `list[str]` (nomes só, sem count), pois o
          `LastfmSource` flattena via `_artist_top_tags`. Wrappamos em
          `[{"name": s, "count": 0}]` para reaproveitar `filter_lastfm_tags`
          (remoção de meta-tags). O corte top_n por count vira no-op, mas o
          filtro de ruído (décadas, avaliativos, países) continua valendo.
        """
        from maestra_ai.core.external.tag_filter import filter_lastfm_tags

        uri = track.get("uri") or ""
        if not uri:
            return set()
        cached = cache_mod.get_track(uri)
        if not cached:
            return set()

        tags: set[str] = set()

        # MusicBrainz: tags já canônicas, union direto (lowercased).
        mb = cached.get("musicbrainz") or {}
        mb_tags = mb.get("tags") or []
        tags.update(t.lower() for t in mb_tags if t)

        # Last.fm: wrap strings no shape esperado pelo filtro; garante dedup/filtro.
        lf = cached.get("lastfm") or {}
        lf_raw = lf.get("top_tags") or []
        lf_wrapped = [{"name": t, "count": 0} for t in lf_raw if t]
        tags.update(filter_lastfm_tags(lf_wrapped))

        return tags

    def _apply_negative_filter(
        self,
        candidates: list[dict],
        parsed,  # ParsedContext — tipagem leve pra evitar import circular
    ) -> tuple[list[dict], bool]:
        """Hard filter removendo candidatos com tag em parsed.negative.

        Se len(filtered) < MIN_CANDIDATES, retorna originais com degraded=True.
        Caller usa degraded pra ativar anti_tag_penalty no scoring.
        """
        if not parsed.negative:
            return candidates, False

        negative_set = set(parsed.negative)
        filtered = [
            c for c in candidates
            if not (self._track_tags(c) & negative_set)
        ]

        if len(filtered) >= MIN_CANDIDATES:
            return filtered, False

        logger.warning(
            "hard filter on %s would leave %d candidates (< %d); "
            "degrading to soft penalty",
            sorted(negative_set), len(filtered), MIN_CANDIDATES,
        )
        return candidates, True

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
        """Retorna contexto utilizavel quando mood veio vazio.

        Aceita string, dict com campo 'text' (shape de ContextState.show()) ou None.
        Evita vazar repr de dict como query literal ao Spotify (bug #20-2).
        """
        if context is None:
            return DEFAULT_CONTEXT
        # Desempacota dict {"text": "...", "bpm": ...} sem serializar com str()
        if isinstance(context, dict):
            context = context.get("text", "") or ""
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
