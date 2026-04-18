# maestra-mcp

MCP stdio server for Maestra AI.

Instale junto com maestra-ai:

```bash
uv tool install maestra-mcp
```

Configure no seu agente (Claude Code `~/.claude/mcp.json`):

```json
{ "mcpServers": { "maestra": { "command": "maestra-mcp" } } }
```

Veja `docs/MCP.md` no repo para guia completo.
