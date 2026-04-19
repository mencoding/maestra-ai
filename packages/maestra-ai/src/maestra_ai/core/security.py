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

# Captura (a) "Bearer <token>" e (b) strings alfanuméricas longas (>=32)
# que tipicamente são access_token, refresh_token ou API keys opacas.
_SECRET_RE = re.compile(
    r"(Bearer\s+[A-Za-z0-9\-_\.]+|[A-Za-z0-9_\-]{32,})"
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
