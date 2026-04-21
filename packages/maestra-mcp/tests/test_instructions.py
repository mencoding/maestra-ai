"""Testes do serverInfo.instructions injetadas no handshake MCP.

Issue #14. As instructions orientam o agente LLM consumidor (Claude Code,
Codex CLI, Gemini CLI) sobre o modelo mental de uso do maestra-mcp —
especialmente que o agente é o diretor musical e o servidor é seu estúdio
de memória estruturada.
"""
from __future__ import annotations

import pytest


def test_instructions_module_exporta_constante():
    from maestra_mcp.instructions import INSTRUCTIONS
    assert isinstance(INSTRUCTIONS, str)
    assert len(INSTRUCTIONS) > 500, (
        "INSTRUCTIONS muito curta — deve cobrir 4 blocos com profundidade razoável"
    )


def test_instructions_cobre_os_quatro_blocos():
    """Marcadores de seção pra garantir que nenhum bloco some num refactor."""
    from maestra_mcp.instructions import INSTRUCTIONS
    lower = INSTRUCTIONS.lower()
    # Bloco 1: modelo mental
    assert "diretor" in lower or "diretora" in lower, (
        "falta menção ao papel de diretor(a) musical (Bloco 1 — modelo mental)"
    )
    # Bloco 2: leitura de humor
    assert "humor" in lower or "estado cognitivo" in lower or "emocional" in lower, (
        "falta orientação sobre ler humor da sessão (Bloco 2)"
    )
    # Bloco 3: cruzar com variáveis
    assert "taste" in lower and "contexto" in lower, (
        "falta orientação sobre consultar taste e contexto (Bloco 3)"
    )
    # Bloco 4: avisos de estado atual
    assert "bug" in lower or "limitaç" in lower or "limitaçã" in lower, (
        "falta seção de avisos sobre estado atual do servidor (Bloco 4)"
    )


def test_instructions_menciona_tools_criticas_por_nome():
    from maestra_mcp.instructions import INSTRUCTIONS
    criticas = ["taste_review", "get_context", "set_context", "queue", "play_context"]
    for tool in criticas:
        assert tool in INSTRUCTIONS, (
            f"tool crítica '{tool}' não mencionada nas instructions — "
            f"agentes podem não saber quando usá-la"
        )


def test_instructions_alerta_bugs_abertos():
    """Enquanto #6 e #8 não forem fechadas, instructions devem alertar agentes.
    Quando fecharem, remover os alertas e atualizar este teste."""
    from maestra_mcp.instructions import INSTRUCTIONS
    # Referências a números de issue ou descrição dos bugs
    assert "#6" in INSTRUCTIONS or "director" in INSTRUCTIONS.lower(), (
        "alerta sobre issue #6 (director daemon) ausente"
    )
    assert "#8" in INSTRUCTIONS or "negaç" in INSTRUCTIONS.lower() or "evitar" in INSTRUCTIONS.lower(), (
        "alerta sobre issue #8 (negações no contexto) ausente"
    )


def test_create_server_passa_instructions_ao_sdk():
    """O Server do SDK MCP deve receber as instructions no handshake."""
    from maestra_mcp.server import create_server
    from maestra_mcp.instructions import INSTRUCTIONS

    srv = create_server()
    # MCP SDK expõe instructions em server.instructions após init
    assert hasattr(srv, "instructions"), (
        "Server não tem atributo .instructions — versão do SDK incompatível?"
    )
    assert srv.instructions == INSTRUCTIONS, (
        "Server.instructions diverge da constante INSTRUCTIONS — "
        "fonte única da verdade quebrada"
    )


def test_instructions_nao_inclui_segredos_nem_paths_absolutos():
    """Sanity check: a string é pública pra qualquer agente consumidor.
    Nenhum token, nenhum path tipo /home/user, nenhum hostname interno."""
    from maestra_mcp.instructions import INSTRUCTIONS
    banned_patterns = ["/home/", "token", "secret", "password", "api_key"]
    lower = INSTRUCTIONS.lower()
    for pattern in banned_patterns:
        assert pattern not in lower, (
            f"INSTRUCTIONS contém padrão sensível '{pattern}' — revisar"
        )
