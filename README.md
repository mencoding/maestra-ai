# Maestra AI

[![CI](https://github.com/mencoding/maestra-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/mencoding/maestra-ai/actions/workflows/ci.yml)

CLI e servidor MCP para controlar Spotify através de agentes de IA, com
curadoria contextual que aprende gosto via feedback conservador.

**Status:** pre-alpha (v0.5.4). Lançamento público planejado em v1.0.0.

## Instalação

Requer Python 3.11+ e [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/mencoding/maestra-ai.git
cd maestra-ai
uv sync --all-extras
```

O binário `maestra` fica disponível via `uv run maestra`. Para instalar global:

```bash
uv tool install ./packages/maestra-ai
```

## Primeiro uso

```bash
# 1. Diagnóstico do ambiente
uv run maestra doctor

# 2. Fluxo completo (explica o resto)
uv run maestra help onboarding
```

Resumo do fluxo:

1. **Criar app Spotify** em https://developer.spotify.com/dashboard — anote
   `client_id`, `client_secret`, e registre um Redirect URI HTTPS
   (Spotify rejeita `localhost` em apps criados após 2025).
2. **`maestra auth setup`** — grava credenciais em `~/.config/maestra/config.json`.
3. **`maestra auth login`** — fluxo OAuth paste-back (abre navegador, cola URL
   de volta no terminal).
4. **`maestra onboard`** — bootstrap do perfil com seu histórico Spotify.
5. **`maestra now`** / **`maestra director start`** — usar.

## Arquitetura

Monorepo uv com dois pacotes:

| Pacote        | Responsabilidade                                          |
|---------------|-----------------------------------------------------------|
| `maestra-ai`  | CLI, controlador Spotify, curadoria, rate limiter, storage |
| `maestra-mcp` | Servidor MCP stdio expondo 23 tools para agentes           |

Estado persistente em XDG (`~/.config`, `~/.local/share`, `~/.local/state`)
com override via env vars (`MAESTRA_CONFIG_DIR`, `MAESTRA_DATA_DIR`,
`MAESTRA_STATE_DIR`).

## Documentação

- **Guia do MCP:** [`docs/MCP.md`](docs/MCP.md)
- **Reviews:** [`docs/reviews/`](docs/reviews/)
- **Planos:** [`docs/superpowers/plans/`](docs/superpowers/plans/)
- **Guias internos:** `maestra help onboarding`, `maestra help mcp`

## Troubleshooting

### 403 Forbidden ao criar playlist

App em Development Mode — adicione seu usuário em **User Management** no
dashboard do app Spotify (email exato da conta Spotify). Detalhes e
contorno via `--playlist-id` em `maestra help onboarding`.

### `env | grep MAESTRA` mostra caminhos inesperados

Remova exports legados de `~/.bashrc`/`~/.profile` e abra terminal novo.
Defaults XDG:
- `~/.config/maestra/` — credenciais
- `~/.local/share/maestra/` — taste_profile, histórico, snapshots
- `~/.local/state/maestra/` — rate limiter

### `maestra doctor` reporta `email: None`

Token antigo sem os scopes `user-read-email`/`user-read-private`. Rode
`maestra auth login` de novo.

## Licença

MIT.
