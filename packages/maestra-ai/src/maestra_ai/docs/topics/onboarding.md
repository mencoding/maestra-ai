# Onboarding

Bootstrap inicial do perfil Maestra usando seu histórico Spotify.

## Pré-requisitos

1. App Spotify criado no [dashboard](https://developer.spotify.com/dashboard)
   com client_id, client_secret e um redirect URI HTTPS (ex:
   `https://example.com/callback`). Spotify rejeita localhost/127.0.0.1
   em apps novos, então o fluxo é "paste-back" — veja `maestra auth login`.
2. `maestra auth setup --client-id X --client-secret Y --redirect-uri Z`
3. `maestra auth login` — completa OAuth paste-back e salva refresh_token.

## O que o onboard faz

Em 6 etapas:

1. **Autenticação** — valida token Spotify com chamada barata
   (`current_user`).
2. **Playlist** — cria uma playlist privada com nome à sua escolha.
   Se já existe playlist com esse nome, acrescenta sufixo `(2)`, `(3)`.
3. **Top tracks** — puxa suas 50 mais ouvidas em 3 janelas:
   - *long_term* (últimos ~anos) — peso **3** (gosto consolidado)
   - *medium_term* (últimos 6 meses) — peso **2**
   - *short_term* (últimas 4 semanas) — peso **2** (mood recente)
4. **Biblioteca** — puxa até 1000 faixas salvas (❤️), paginando de 50
   em 50 — peso **1**.
5. **Recently played** — últimas 50 ouvidas — peso **1**.
6. **Análise** — soma pesos por URI, grava `global_signal` no
   `taste_profile`, semeia `top_short[:N]` na playlist recém-criada,
   deriva 5 contextos sugeridos a partir dos artistas dominantes.

## Custo

~24 requests à API Spotify (~40 KB transferidos). Leva ~8s com rate
limiter local (60 req/min).

## Flags úteis

- `--playlist-name "Trabalho profundo"` — nome da playlist buffer.
- `--seed-playlist 10` — faixas iniciais (default 30; use 0 para
  só analisar sem popular a playlist).
- `--dry-run` — simula sem criar playlist nem escrever no taste_profile.
- `--yes` — pula confirmação (útil em scripts).
- `--json` — output estruturado para pipe/agent.

## Depois do onboard

Escolha um dos contextos sugeridos no panel final e rode:

```bash
maestra context set "ambient instrumental para trabalho analítico"
maestra curate
maestra play
```

Ou deixe o `director` rodando em background para curar conforme o
contexto mudar:

```bash
maestra director start --interval 60
```
