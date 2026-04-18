# Integração MCP

A Maestra é um **MCP server stdio** — subprocesso que seu agente de IA
(Claude Code, Cursor, Codex) inicia para usar as 23 ferramentas.

## Em uma frase

Você instala `maestra-mcp`, adiciona 3 linhas na config do seu agente, e
o agente passa a controlar Spotify com curadoria contextual — sem você
precisar ensinar comandos.

## Arquitetura

- Seu agente ↔ `maestra-mcp` (stdio local) ↔ `maestra-ai` core ↔ Spotify API
- Tudo na sua máquina. Sem hospedagem. Sem telemetria.

## Quando usar MCP vs CLI

- **MCP**: integração com agente conversacional. "Coloca foco denso" →
  agente usa as tools.
- **CLI**: uso direto, debugging, scripts. `maestra flow review` → você
  vê no terminal.

As duas interfaces usam o mesmo core.

Ver `docs/MCP.md` do repo para guia por agente.
