# Onboarding

Bootstrap inicial do perfil Maestra usando seu histórico Spotify.

## Pré-requisitos

1. App Spotify criado no [dashboard](https://developer.spotify.com/dashboard)
   com client_id, client_secret e um redirect URI **HTTPS** (ex:
   `https://example.com/callback` — o TLD `example.com` é reservado por
   RFC 2606 e aceito pelo Spotify via paste-back, não precisa hospedar
   nada). Spotify rejeita `localhost` e `127.0.0.1` em apps criados após
   2025, então o fluxo é sempre paste-back — veja `maestra auth login`.
2. `maestra auth setup --client-id X --client-secret Y --redirect-uri Z`
3. `maestra auth login` — completa OAuth paste-back e salva refresh_token.

## O que o onboard faz

Em 6 etapas:

1. **Autenticação** — valida token Spotify com chamada barata
   (`current_user`).
2. **Playlist** — cria uma playlist privada com nome à sua escolha, ou
   aponta uma existente via `--playlist-id`. Se já existe playlist com
   o nome pedido, acrescenta sufixo `(2)`, `(3)`. Se `--playlist-id` +
   `--playlist-name` com nome atual diferente → renomeia no Spotify.
3. **Top tracks** — puxa suas 50 mais ouvidas em 3 janelas:
   - *long_term* (últimos ~anos) — peso **3** (gosto consolidado)
   - *medium_term* (últimos 6 meses) — peso **2**
   - *short_term* (últimas 4 semanas) — peso **2** (mood recente)
4. **Biblioteca** (Liked Songs ❤️) — paginação defensiva até 5000
   faixas, peso **3** (curadoria explícita tem peso igual ao top
   consolidado).
5. **Recently played** — últimas 50 ouvidas — peso **1**.
6. **Análise** — soma pesos por URI, grava `global_signal` no
   `taste_profile`, semeia `top_short[:N]` na playlist, deriva 5
   contextos sugeridos a partir dos artistas dominantes.

## Custo

~24 requests iniciais + ~N/50 da biblioteca (N = tamanho do Liked Songs).
Biblioteca média ~500 tracks = ~34 requests total, ~60 KB, ~8s com rate
limiter local.

## Flags úteis

- `--playlist-name "Maestra"` (ou `--name`) — nome da playlist buffer.
- `--playlist-id '<URL ou URI ou ID>'` — aponta playlist existente em
  vez de criar. **Use aspas simples** — URLs do Spotify contêm `&` e
  `?` que o shell interpreta se não escapadas.
- `--seed-playlist N` — faixas iniciais na playlist (default 30,
  máximo efetivo 50 pois `top_short_term` tem cap 50 na API Spotify;
  use 0 para só analisar sem popular a playlist).
- `--dry-run` — simula sem criar playlist nem escrever no taste_profile.
- `--yes` — pula confirmação (útil em scripts).
- `--non-interactive` — falha se faltar `--name` ou `--playlist-id`,
  não abre prompt.
- `--json` — output estruturado para pipe/agent (inclui campo
  `warnings` se houver).

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

## Troubleshooting

### 403 "Forbidden" ao criar playlist

Causa quase sempre é o **app em Development Mode**. Spotify exige que o
usuário autenticado esteja listado em **User Management** do dashboard.

1. Abra https://developer.spotify.com/dashboard → seu app → **User
   Management** → **Add new user**.
2. Informe o **email exato** da sua conta Spotify (confira em
   https://spotify.com/account; pode ser diferente do email do Gmail
   se a conta está vinculada a Apple/Google).
3. Aguarde até 30 minutos para propagação.
4. Se ainda falhar, use o contorno:

   ```bash
   # 1. Cria playlist manualmente no app Spotify (vazia, privada).
   # 2. Botão direito → Compartilhar → Copiar link.
   # 3. Passa para o onboard (note as aspas simples):
   maestra onboard \
     --playlist-id 'https://open.spotify.com/playlist/XXXXXXXX?si=...' \
     --playlist-name "Maestra" \
     --seed-playlist 50 --non-interactive --yes
   ```

   O onboard pula a criação, renomeia a playlist se preciso, e segue com
   a análise de gosto normalmente.

### `env` mostra `MAESTRA_CONFIG_DIR` apontando para lugar inesperado

Versões antigas do setup deixavam env vars legadas no `~/.bashrc`.
Remova estas linhas se existirem:

```bash
export MAESTRA_CONFIG_DIR="..."
export MAESTRA_DATA_DIR="..."
```

Abra um terminal novo após remover. Caminhos padrão (XDG) são:
- `~/.config/maestra/` — credenciais
- `~/.local/share/maestra/` — taste_profile, histórico, snapshots
- `~/.local/state/maestra/` — rate limiter, circuit breaker

### `doctor` reporta `product: None`, `email: None`

Precisa rodar `maestra auth login` de novo. Versões ≤ v0.5.1 não pediam
scopes `user-read-email` e `user-read-private`, então tokens antigos
não conseguem ler esses campos.
