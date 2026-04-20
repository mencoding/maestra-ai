"""Redaction de secrets em saídas do CLI (stdout/stderr/JSON).

Reutiliza `_redact` de `core.audit` para dicts (redaction por chave) e
adiciona `redact_str` (redaction por regex) para strings livres —
mensagens de exceção do spotipy que podem embutir tokens Bearer ou
IDs opacos longos, e o campo `what_happened` do `MaestraError` quando
construído via f-string.
"""
from __future__ import annotations

import re
from typing import Any

from maestra_ai.core.audit import _redact

# MEDIUM-1: redação contextual — só mascara quando houver pista de que
# é secret. Evita falsos positivos em URIs de track, playlist IDs,
# nomes longos de faixa etc.
#  1. Bearer <token>
#  2. <known_key>=<value> ou <known_key>: <value>   (access_token,
#     refresh_token, client_secret, api_key, apikey, authorization, auth)
#  3. JWT shape                                     (3 segmentos
#     base64url separados por '.', começando com 'eyJ')
#
# Limite conhecido do matcher JWT (S6):
# o regex cobre o shape canônico `eyJ...eyJ...eyJ...` (header base64url
# que começa com o caractere `{` codificado — `eyJ`). JWTs com headers
# não-canônicos ou tokens opacos isolados (sem prefixo `Bearer` e sem
# known-key adjacente) NÃO são redigidos por este regex — a defesa
# efetiva nesses casos é a redaction por chave em `_SECRET_KEYS` de
# `core/audit.py` e o prefixo `Bearer ` emitido pelo spotipy.
_KNOWN_SECRET_KEYS = (
    "access_token", "refresh_token", "client_secret",
    "api_key", "apikey", "authorization", "auth",
)
_SECRET_RE = re.compile(
    r"("
    # JWT primeiro (mais específico)
    r"eyJ[A-Za-z0-9_\-]+\.eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+"
    # Bearer <token>
    r"|Bearer\s+[A-Za-z0-9\-_\.]+"
    # known_key=<value> — o valor não pode começar com 'Bearer '
    # (senão consumiria o prefixo e deixaria o token exposto).
    r"|(?:" + "|".join(_KNOWN_SECRET_KEYS) + r")"
    r"\s*[:=]\s*(?!Bearer\s)[A-Za-z0-9\-_\.]+"
    r")",
    re.IGNORECASE,
)


def redact_str(value: Any) -> str:
    """Remove padrões de secret de uma string livre.

    Substitui por "REDACTED" tudo que casar com `_SECRET_RE`.
    """
    if not isinstance(value, str):
        value = str(value)
    return _SECRET_RE.sub("REDACTED", value)


def redact_error_dict(d: dict) -> dict:
    """Redacta um dict de erro (output de MaestraError.to_human_dict).

    Cobre:
    - `where` e `body`: redaction por chave (via `_redact` de audit).
    - `what_happened` e `title`: redaction por regex (via `redact_str`).
    - Outros campos (probable_causes, suggested_actions, agent_hint,
      code) são preservados.
    """
    out = dict(d)
    for field in ("what_happened", "title"):
        if isinstance(out.get(field), str):
            out[field] = redact_str(out[field])
    for field in ("where", "body"):
        if field in out:
            if isinstance(out[field], (dict, list)):
                out[field] = _redact(out[field])
            else:
                out[field] = redact_str(out[field])
    return out
