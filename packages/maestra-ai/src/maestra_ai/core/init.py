"""Wizard unificado `maestra init`.

Detecta estado (A/A2/B/C), apresenta menu contextual, executa o fluxo
escolhido. Delega I/O externo para `core.auth` e `core.onboard`.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import TypeVar

from rich.console import Console
from rich.panel import Panel

from maestra_ai.core import storage
from maestra_ai.core.init_types import InitState

T = TypeVar("T")


class UserAbort(Exception):
    """Usuário escolheu sair voluntariamente."""

_console = Console()


_MENU_MESSAGES: dict[InitState, tuple[str, list[str]]] = {
    "A": (
        "Olá! Vamos configurar sua Maestra.",
        ["[1] Começar agora", "[2] Sair"],
    ),
    "A2": (
        "Sua app Spotify já está configurada. Só falta autorizar o acesso.",
        [
            "[1] Continuar — autorizar e analisar preferências",
            "[2] Recomeçar — apagar config e começar de novo",
            "[3] Sair",
        ],
    ),
    "B": (
        "Sua conta Spotify já está conectada. Só falta analisar suas preferências "
        "musicais para eu poder sugerir contextos.",
        [
            "[1] Continuar — analisar preferências agora",
            "[2] Recomeçar — apagar conexão e começar de novo",
            "[3] Sair",
        ],
    ),
    "C": (
        "Tudo pronto por aqui! O que você quer fazer?",
        [
            "[1] Atualizar preferências — re-analisar seu histórico recente",
            "[2] Recomeçar — apagar tudo e refazer",
            "[3] Sair",
        ],
    ),
}


def render_menu(state: InitState) -> None:
    """Imprime o menu apropriado para o estado."""
    header, options = _MENU_MESSAGES[state]
    body = header + "\n\n" + "\n".join(f"  {o}" for o in options)
    _console.print(Panel(body, border_style="cyan", padding=(1, 2)))


def render_update_submenu() -> None:
    """Sub-menu de C→[1]."""
    body = (
        "O que você quer atualizar?\n\n"
        "  [1] Só mood recente (últimas 4 semanas + histórico recente)\n"
        "  [2] Tudo (pode demorar mais)\n"
        "  [3] Voltar"
    )
    _console.print(Panel(body, border_style="cyan", padding=(1, 2)))


def _has_token() -> bool:
    """True se há refresh_token persistido (keyring ou fallback)."""
    from maestra_ai.core.token_store import default_token_store
    try:
        tok = default_token_store().load()
        return bool(tok)
    except Exception:
        return False


def _has_config() -> bool:
    """True se config.json tem client_id e client_secret não-vazios."""
    path = storage.config_dir() / "config.json"
    if not path.exists():
        return False
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(cfg.get("client_id")) and bool(cfg.get("client_secret"))


def _has_taste() -> bool:
    """True se taste_profile tem global_signal não-vazio."""
    path = storage.data_dir() / "taste_profile.json"
    if not path.exists():
        return False
    try:
        profile = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(profile.get("global_signal"))


def detect_state() -> InitState:
    """Retorna o estado atual do setup da Maestra.

    Estados inconsistentes (taste sem token, token sem config) voltam pra A
    — o chamador pode consultar o helper privado pra avisar o usuário.
    """
    has_config = _has_config()
    has_token = _has_token()
    has_taste = _has_taste()

    if has_config and has_token and has_taste:
        return "C"
    if has_config and has_token:
        return "B"
    if has_config and not has_token:
        return "A2"
    # Combinações inconsistentes caem em A
    return "A"


def _ask_retry() -> bool:
    """Pergunta '[1] Tentar de novo / [2] Sair'. Retorna True se tentar."""
    from rich.prompt import Prompt
    _console.print("\n  [1] Tentar de novo")
    _console.print("  [2] Sair")
    choice = Prompt.ask("Escolha", choices=["1", "2"], default="1")
    return choice == "1"


def _ask_smart_exit(error_kind: str, hint: str) -> bool:
    """Pergunta se abre link externo ou sai. Retorna True se quer tentar de novo."""
    from rich.prompt import Prompt
    _console.print(
        f"\nEssa é a terceira tentativa com o mesmo erro ({error_kind}).\n\n"
        f"Parece que o problema precisa de ação externa. {hint}\n"
    )
    _console.print("  [1] Abrir no navegador e tentar de novo")
    _console.print("  [2] Sair e resolver depois (seu progresso foi salvo)")
    choice = Prompt.ask("Escolha", choices=["1", "2"], default="2")
    return choice == "1"


def _retry_loop(
    fn: Callable[[], T],
    *,
    classifier: Callable[[Exception], str],
    hints: dict[str, str],
    max_same_kind: int = 3,
    on_smart_exit_link: Callable[[str], None] | None = None,
) -> T:
    """Executa `fn()` com retry interativo até sucesso ou desistência.

    - Após `max_same_kind` (default 3) falhas consecutivas do MESMO tipo,
      oferece smart exit com link e mensagem específica.
    - Se o usuário escolher sair (seja no prompt comum ou no smart exit),
      levanta `UserAbort`.
    """
    same_kind_count = 0
    last_kind: str | None = None
    while True:
        try:
            return fn()
        except Exception as e:
            kind = classifier(e)
            hint = hints.get(kind, "Tente novamente em alguns segundos.")
            _console.print(f"\n{e}\n\n{hint}\n")

            if kind == last_kind:
                same_kind_count += 1
            else:
                same_kind_count = 1
                last_kind = kind

            if same_kind_count >= max_same_kind:
                _console.print(
                    f"\nEssa é a terceira tentativa com o mesmo tipo de erro "
                    f"({kind}). Vou oferecer uma saída diferente.\n"
                )
                if _ask_smart_exit(kind, hint):
                    if on_smart_exit_link is not None:
                        on_smart_exit_link(kind)
                    # Reseta contador — usuário realizou ação externa
                    same_kind_count = 0
                    last_kind = None
                    continue
                raise UserAbort(
                    f"Desistiu após {same_kind_count} tentativas ({kind})"
                )

            if not _ask_retry():
                raise UserAbort("Usuário escolheu sair")
