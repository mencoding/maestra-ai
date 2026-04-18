# Maestra MCP — integração com agentes de IA

A Maestra expõe 23 ferramentas via MCP stdio. Qualquer agente compatível
com Model Context Protocol (Claude Code, Cursor, Codex, etc.) pode usar
essas ferramentas sem código adicional.

## Instalação

Em um lugar do seu PATH:

```bash
uv tool install --from /caminho/maestra-ai/packages/maestra-mcp maestra-mcp
```

Ou, após publicação no PyPI:

```bash
uv tool install maestra-mcp
```

Isso também instala `maestra-ai` como dependência.

Antes de usar, configure credenciais do app Spotify:

```bash
maestra auth setup --client-id X --client-secret Y --redirect-uri Z
maestra auth login
```

## Configuração por agente

### Claude Code

Em `~/.claude/mcp.json`:

```json
{
  "mcpServers": {
    "maestra": {
      "command": "maestra-mcp"
    }
  }
}
```

Reinicie o Claude Code. Comando `/mcp` no chat deve listar 23 tools do
`maestra`.

### Cursor

Em Settings → MCP, adicione server com:
- Name: `maestra`
- Command: `maestra-mcp`

### Codex CLI

Na config do Codex:

```toml
[mcp.servers.maestra]
command = "maestra-mcp"
```

## Tools (23)

**Playback (7):** `now`, `play`, `pause`, `skip`, `queue`, `search`, `devices`

**Contexto (3):** `set_context`, `get_context`, `clear_context`

**Curadoria (1):** `curate`

**Análise (3):** `flow_review`, `taste_review`, `history_outside_playlist`

**Manutenção (3):** `playlist_prune`, `history_import_outside`, `rollback`

**Director (4):** `director_start`, `director_stop`, `director_status`, `director_once`

**Onboard/Diagnóstico (2):** `onboard`, `doctor`

Todas têm schema JSON estrito. Operações destrutivas exigem
`confirm: true` e fazem snapshot automático — use `rollback` para desfazer.

## Desabilitar tools

Em `~/.config/maestra/config.json`:

```json
{
  "mcp": {
    "disabled_tools": ["playlist_prune", "director_start"]
  }
}
```

Tools bloqueadas não aparecem no `tools/list` e rejeitam chamadas diretas.

## Audit log

Toda chamada MCP é registrada em `~/.local/state/maestra/audit/audit.jsonl`
com redact automático de secrets (Bearer tokens, client_secret, etc.).
Retenção: 15 dias ativos + 30 dias em gzip.

## Debugging

Logs do server vão para stderr (nível INFO). Para ver:

```bash
maestra-mcp 2>/tmp/maestra-mcp.log &
```

Erros estruturados vêm em `result.error` do JSON-RPC, com `agent_hint`
orientando o agente a rodar `maestra auth login`, `maestra doctor`, etc.
