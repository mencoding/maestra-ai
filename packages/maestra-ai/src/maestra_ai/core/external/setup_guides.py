"""Guias interativos para criação de API keys das fontes opcionais.

Padrão inspirado em `core/init.py::_flow_A_collect_credentials`:
passos numerados, instruções literais do que preencher, validação leve,
prompt final com escape (Enter vazio = pular).
"""
from __future__ import annotations

import re

import questionary
from rich.console import Console

_console = Console()

_LASTFM_CREATE_URL = "https://www.last.fm/api/account/create"
_LASTFM_KEY_PATTERN = re.compile(r"^[0-9a-fA-F]{32}$")


def _validate_lastfm_key(key: str) -> bool:
    return bool(_LASTFM_KEY_PATTERN.match(key))


def guide_lastfm() -> tuple[bool, str | None]:
    """Guia passo-a-passo para criar conta Last.fm e obter API key.

    Retorna (enabled, api_key). Enter vazio em qualquer prompt = skip.
    """
    _console.print()
    _console.print("[bold]━━━ Configurar Last.fm (opcional) ━━━[/bold]")
    _console.print("Last.fm fornece tags ricas e descobre artistas similares.")
    _console.print()
    _console.print("Passos:")
    _console.print(f"  1. Abrir {_LASTFM_CREATE_URL}")
    _console.print("  2. Preencher:")
    _console.print("     • Application name:        Maestra")
    _console.print("     • Application description: Uso pessoal")
    _console.print("     • Callback URL:            deixar em branco")
    _console.print("     • Application homepage:    deixar em branco")
    _console.print("  3. Submeter. A próxima tela mostra a \"API key\" (32 chars).")
    _console.print()

    while True:
        raw = questionary.text(
            "  4. Cole aqui (Enter para pular):",
        ).ask()
        if raw is None or raw.strip() == "":
            _console.print("[yellow]Pulando Last.fm. Configure depois com:[/yellow]")
            _console.print("[yellow]  maestra config external set-key lastfm <key>[/yellow]")
            return False, None
        key = raw.strip()
        if _validate_lastfm_key(key):
            _console.print("[green]Chave aceita. Last.fm ativado.[/green]")
            return True, key
        _console.print("[red]A chave parece estranha (esperava 32 caracteres hex).[/red]")
        retry = questionary.confirm("Tentar de novo?", default=False).ask()
        if not retry:
            return False, None


_GETSONGBPM_API_URL = "https://getsongbpm.com/api"
_GETSONGBPM_KEY_MIN_LEN = 8


def _validate_getsongbpm_key(key: str) -> bool:
    if not key or " " in key or "\t" in key:
        return False
    return len(key) >= _GETSONGBPM_KEY_MIN_LEN


def guide_getsongbpm() -> tuple[bool, str | None]:
    """Guia passo-a-passo para criar conta GetSongBPM e obter API key.

    Retorna (enabled, api_key). Enter vazio em qualquer prompt = skip.
    """
    _console.print()
    _console.print("[bold]━━━ Configurar GetSongBPM (opcional) ━━━[/bold]")
    _console.print("GetSongBPM fornece BPM, tonalidade e time signature.")
    _console.print()
    _console.print("Passos:")
    _console.print(f"  1. Abrir {_GETSONGBPM_API_URL}")
    _console.print("  2. Preencher email + URL do projeto onde a atribuição")
    _console.print("     ficará visível (pode usar:")
    _console.print("     https://github.com/mencoding/maestra-ai).")
    _console.print("  3. Receber a API key por email (alguns minutos).")
    _console.print()
    _console.print("[yellow]Atribuição obrigatória: 'maestra curate --human' mostra[/yellow]")
    _console.print("[yellow]link para getsongbpm.com/about em toda execução com BPM.[/yellow]")
    _console.print()
    while True:
        raw = questionary.text("  4. Cole aqui quando receber (Enter para pular):").ask()
        if raw is None or raw.strip() == "":
            return False, None
        key = raw.strip()
        if _validate_getsongbpm_key(key):
            _console.print("[green]Chave aceita. GetSongBPM ativado.[/green]")
            return True, key
        _console.print("[red]A chave parece estranha (8+ chars sem espaço).[/red]")
        retry = questionary.confirm("Tentar de novo?", default=False).ask()
        if not retry:
            return False, None
