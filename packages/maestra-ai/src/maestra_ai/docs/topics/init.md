# Init

Wizard guiado de configuração e análise da Maestra. Substitui o fluxo antigo
`auth setup` + `auth login` + `onboard` por um único comando.

## Modos

- `maestra init` — interativo. Detecta estado (zero, conectado, tudo pronto)
  e oferece menu contextual.
- `maestra init --auto` — sem prompts. Requer estado B ou C (conexão já feita).
- `maestra init --json` — saída JSON estruturada (implica `--auto`).

## Estados

| Estado | Significa | Ação padrão |
|---|---|---|
| A | Nada configurado | Criar app + autorizar + analisar |
| A2 | App criada, sem autorização | Autorizar + analisar |
| B | Conectado, sem análise | Analisar preferências |
| C | Tudo pronto | Atualizar preferências |

## Primeira vez (estado A)

1. Crie um app no dashboard Spotify em https://developer.spotify.com/dashboard
   (o wizard abre pra você).
2. Em "Redirect URI", cole: `https://example.com/callback` (TLD reservado,
   não precisa hospedar nada).
3. Cole Client ID e Client Secret no wizard.
4. Autorize o app no navegador; cole a URL de retorno no wizard.
5. Escolha o nome da playlist onde as sugestões vão aparecer (default: Maestra).
6. Aguarde a análise (~10-30s dependendo da biblioteca).

## Troubleshooting

### 403 ao criar playlist

Apps em Development Mode exigem que seu email esteja em "User Management"
no painel. O wizard detecta esse erro após 3 tentativas e oferece abrir o
painel pra você.

### URL paste-back rejeitada

A URL precisa começar com seu Redirect URI (`https://example.com/callback`)
e conter `?code=...`. Cole a URL completa da barra de endereços DEPOIS de
autorizar o app.

### `--auto` falha em estado A

Estado A requer interação pra criar app Spotify. Rode `maestra init` sem
`--auto` na primeira vez.
