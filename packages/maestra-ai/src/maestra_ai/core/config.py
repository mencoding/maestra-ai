"""Helpers de configuração do core.

Centraliza utilitários puros de parsing/normalização que precisam ser
compartilhados entre CLI, MCP e core — evita duplicação inline de regex
em múltiplos módulos.
"""
from __future__ import annotations

import logging
import re

try:
    import keyring  # type: ignore[import-untyped]
except ImportError:
    keyring = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# --- Keyring: API keys de fontes externas ---

_KEYRING_SERVICE = "maestra-ai"
_KEY_USERNAMES: dict[str, str] = {
    "lastfm": "lastfm-api-key",
    "getsongbpm": "getsongbpm-api-key",
}


def get_source_key(source: str) -> str | None:
    """Lê API key de uma source via keyring. None se não configurada."""
    username = _KEY_USERNAMES.get(source)
    if not username:
        return None
    if keyring is None:
        return None
    try:
        return keyring.get_password(_KEYRING_SERVICE, username)
    except Exception:
        return None


def set_source_key(source: str, key: str) -> None:
    """Grava API key no keyring. Levanta ValueError se source desconhecida."""
    username = _KEY_USERNAMES.get(source)
    if not username:
        raise ValueError(f"source sem keyring: {source}")
    if keyring is None:
        raise RuntimeError("keyring não disponível neste ambiente")
    keyring.set_password(_KEYRING_SERVICE, username, key)


def delete_source_key(source: str) -> None:
    """Remove API key do keyring. Idempotente — não levanta se ausente."""
    username = _KEY_USERNAMES.get(source)
    if not username:
        return
    if keyring is None:
        return
    try:
        keyring.delete_password(_KEYRING_SERVICE, username)
    except Exception:
        pass  # PasswordDeleteError se inexistente, ou backend indisponível

# ID Spotify = 22 caracteres base62.
# Regex canônica: prefere URIs/URLs oficiais para evitar que lixo de 22
# chars antes da URI seja capturado pelo fallback permissivo (S10).
_PLAYLIST_CANONICAL_RE = re.compile(
    r"(?:spotify:playlist:|open\.spotify\.com/playlist/)([a-zA-Z0-9]{22})"
)
_PLAYLIST_ID_RE = re.compile(r"[a-zA-Z0-9]{22}")


def normalize_playlist_id(value: str) -> str:
    """Extrai o ID canônico de 22 chars base62 de um identificador Spotify.

    Aceita:
    - ID puro (`37i9dQZF1DXcBWIGoYBM5M`)
    - URI (`spotify:playlist:<ID>`)
    - URL (`https://open.spotify.com/playlist/<ID>?si=...`)

    Quando a entrada contém uma URI/URL canônica, o ID dela é preferido
    sobre qualquer outra sequência de 22 chars base62 presente na string
    (evita capturar lixo que apareça antes da URI). Caso não haja forma
    canônica, cai no fallback permissivo (primeiro match de 22 base62).

    Levanta ValueError se o valor for vazio, não-string ou não contiver
    22 caracteres base62 consecutivos.
    """
    if not value or not isinstance(value, str):
        raise ValueError(f"playlist vazia ou tipo inválido: {value!r}")
    canonical = _PLAYLIST_CANONICAL_RE.search(value)
    if canonical:
        return canonical.group(1)
    fallback = _PLAYLIST_ID_RE.search(value)
    if fallback:
        return fallback.group(0)
    raise ValueError(f"formato de playlist inválido: {value!r}")


def _default_external_sources() -> dict:
    return {
        "musicbrainz": {"enabled": False},
        "lastfm":      {"enabled": False},
        "getsongbpm":  {"enabled": False},
    }


def _migrate_plaintext_key(cfg_sources: dict, source: str) -> None:
    """Move api_key plaintext de cfg_sources[source] para keyring (best-effort).

    Se keyring estiver indisponível, mantém o valor em plaintext e emite
    warning. Nunca loga o valor da key.
    """
    entry = cfg_sources.get(source, {})
    raw_key = entry.get("api_key")
    if not raw_key:
        # Sem chave ou já removida — noop
        entry.pop("api_key", None)
        return
    try:
        set_source_key(source, raw_key)
        entry.pop("api_key")
        logger.debug("API key de '%s' migrada para keyring.", source)
    except Exception:
        logger.warning(
            "Keyring indisponível: API key de '%s' permanece em config.json "
            "(melhorar segurança configurando o keyring do SO).",
            source,
        )


def migrate_external_sources(cfg: dict) -> dict:
    """Migra config de fontes externas para o shape v0.10.4+.

    Operações realizadas (todas idempotentes):
    1. `external_sources_enabled: bool` flat → `external_sources: {...}` nested.
    2. `api_key` plaintext em nested → keyring (best-effort; fallback graceful).
    3. Completa campos faltantes com defaults.

    Muta `cfg` in-place e retorna o mesmo objeto.
    """
    if "external_sources" in cfg and isinstance(cfg["external_sources"], dict):
        # Migrar api_keys em plaintext para keyring
        for source in ("lastfm", "getsongbpm"):
            if source in cfg["external_sources"]:
                _migrate_plaintext_key(cfg["external_sources"], source)

        # Completar campos faltantes (sem tocar em api_key — gerenciada por _migrate_plaintext_key)
        defaults = _default_external_sources()
        for source, default_val in defaults.items():
            cfg["external_sources"].setdefault(source, default_val)
            cfg["external_sources"][source].setdefault("enabled", False)

        cfg.pop("external_sources_enabled", None)
        return cfg

    enabled_flat = cfg.pop("external_sources_enabled", None)
    cfg["external_sources"] = _default_external_sources()
    if enabled_flat is True:
        cfg["external_sources"]["musicbrainz"]["enabled"] = True
    return cfg


def source_enabled(cfg: dict, source: str) -> bool:
    """Retorna True se `source` em {musicbrainz, lastfm, getsongbpm} está habilitado.

    Lê tanto shape nested quanto legacy flat (nesse caso, só `musicbrainz` pode ficar True).
    """
    nested = cfg.get("external_sources")
    if isinstance(nested, dict):
        entry = nested.get(source)
        if isinstance(entry, dict):
            return bool(entry.get("enabled"))
        return False
    # legacy flat: apenas musicbrainz pode estar ligado
    if source == "musicbrainz":
        return bool(cfg.get("external_sources_enabled"))
    return False


def any_source_enabled(cfg: dict) -> bool:
    """True se qualquer fonte externa está habilitada."""
    return any(source_enabled(cfg, s) for s in ("musicbrainz", "lastfm", "getsongbpm"))


def load_and_migrate() -> dict:
    """Carrega config, aplica migrações e persiste se mudou."""
    import copy

    from maestra_ai.core import storage

    data = storage.read_config()
    original = copy.deepcopy(data)
    data = migrate_external_sources(data)
    if data != original:
        storage.write_config(data)
    return data


DEFAULT_CURATE_WEIGHTS = {"taste": 0.4, "tag": 0.3, "decade": 0.2, "bpm": 0.1}
_WEIGHT_SUM_TOLERANCE = 0.01


def validate_curate_weights(weights: dict) -> bool:
    """Valida weights de curação: todas as chaves obrigatórias, valores em [0,1] e soma ≈ 1.0."""
    required = {"taste", "tag", "decade", "bpm"}
    if not isinstance(weights, dict) or set(weights.keys()) != required:
        return False
    for v in weights.values():
        if not isinstance(v, (int, float)):
            return False
        if v < 0 or v > 1:
            return False
    total = sum(weights.values())
    if abs(total - 1.0) > _WEIGHT_SUM_TOLERANCE:
        return False
    return True


def load_curate_weights(cfg: dict) -> dict:
    """Retorna weights configurados se válidos; defaults caso contrário."""
    raw = cfg.get("curate_weights")
    if raw is None:
        return dict(DEFAULT_CURATE_WEIGHTS)
    if validate_curate_weights(raw):
        return dict(raw)
    logger.warning("curate_weights inválidos em config.json, usando defaults")
    return dict(DEFAULT_CURATE_WEIGHTS)
