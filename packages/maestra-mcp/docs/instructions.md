# MCP serverInfo.instructions

Este documento explica o racional, a estrutura e o processo de evolução
das instructions que o servidor `maestra-mcp` expõe no handshake MCP.

## O que são

O protocolo MCP permite que um servidor declare uma string de orientação
(`serverInfo.instructions`) na resposta do handshake inicial. Clientes
compatíveis — Claude Code, Codex CLI, Gemini CLI — injetam essa string
automaticamente no contexto inicial da conversa com o agente LLM.

Exemplo de como Claude Code apresenta as instructions no prompt:

```
## MCP Server Instructions

## maestra
# Maestra MCP — Modelo mental

Você é o diretor musical da sessão. Este servidor é seu estúdio: memória
estruturada de gosto, contexto e histórico do usuário, ...
```

O agente lê isso antes de qualquer interação com o usuário.

## Modelo mental

A arquitetura do maestra distingue duas camadas de inteligência:

- **Maestra (servidor) — órgão sensorial-motor.** Armazena variáveis
  estruturadas do usuário (`taste_profile`, `context`, histórico,
  metadata externa via MB/LF/Reccobeats, scoring composto) e opera o
  Spotify (`play`, `queue`, `skip`, `search`, `playlist_*`).
- **LLM agente — córtex.** Lê o humor cognitivo e emocional da sessão,
  dimensão que só o LLM acessa, e traduz isso em escolha musical,
  operando a fila como extensão desse entendimento.

O scoring composto automático (`play_context`, `director`) existe para
quando não há agente no loop — CLI direto, director autônomo rodando em
background. Com agente ativo, a primazia é do agente; o scoring vira
fallback pra situações sem input recente.

Essa divisão é o núcleo do valor do maestra-ai: curadoria contextual que
combina conhecimento impessoal (o que é próximo estilisticamente de X)
com conhecimento pessoal (o que este usuário gosta dentro desse estilo).
Agente sem servidor = DJ sem conhecer o cliente. Servidor sem agente =
banco de dados de gosto sem leitor do momento. Juntos = a proposta.

## Estrutura das instructions

Quatro blocos, cada um com objetivo específico:

1. **Modelo mental.** Uma frase orientadora no topo: agente é diretor,
   servidor é estúdio, primazia do agente com agente ativo.
2. **Leitura de humor como entrada primária.** Dimensões a considerar
   (tipo de trabalho, ritmo, emocional, temporal, meta), exemplos de
   eixos musicais, afirmação de que só o LLM tem essa dimensão.
3. **Uso das variáveis armazenadas.** Quais tools consultar antes de
   enfileirar (`taste_review`, `get_context`, `queue`,
   `history_outside_playlist`), como reagir a sinais do usuário
   (`skip` = descompasso), quando usar `play_context` como fallback.
4. **Limitações atuais.** Bugs conhecidos que afetam o uso do servidor
   hoje (ex: `director_start` silencioso da issue #6, negações ignoradas
   da issue #8). Avisos marcados com a issue correspondente; são
   removidos quando o fix chega em produção.

## Processo de evolução

As instructions são ativo vivo. Atualizá-las é parte do release cycle
quando houver mudança de comportamento que agentes consumidores precisam
saber.

### Quando atualizar

- **Nova feature user-facing.** Nova tool expondo capacidade importante
  (ex: `taste_review`, `flow_review`) deve aparecer no Bloco 3 ou 4.
- **Fix de bug conhecido.** Quando um bug listado no Bloco 4 for
  resolvido, remover o aviso correspondente no mesmo PR do fix.
- **Mudança de comportamento.** Se semântica de uma tool muda de forma
  não-retrocompatível (ex: default de `dry_run` trocando), mencionar
  explicitamente.
- **Descoberta de padrão de uso ruim.** Se feedback de uso real mostra
  que agentes estão usando o servidor de forma subótima consistente
  (caso que originou esta feature: agentes repondo fila via
  `search + queue` manual em vez de `play_context`), refletir a
  correção aqui.

### Quando NÃO atualizar

- Mudanças internas invisíveis ao agente (refactor, performance, etc.).
- Novas tools auxiliares sem papel central no fluxo principal.
- Bugs que afetam só a CLI, não o MCP.

### Processo

1. Editar `packages/maestra-mcp/src/maestra_mcp/instructions.py`.
2. Rodar `uv run pytest packages/maestra-mcp/tests/test_instructions.py`
   — os testes validam que os 4 blocos continuam presentes e que tools
   críticas são citadas. Se o teste quebrar, revisar se o bloco foi
   removido por engano ou se o teste precisa ser atualizado junto.
3. Em releases, registrar no CHANGELOG no item "MCP server".
4. Após PR merged, reiniciar o Claude Code (ou cliente equivalente) para
   que o novo handshake traga as instructions atualizadas.

## Testes

`packages/maestra-mcp/tests/test_instructions.py` cobre:

- `INSTRUCTIONS` é constante não-vazia e de tamanho razoável (> 500
  chars).
- Os 4 blocos estão presentes (via marcadores-chave: `diretor`,
  `humor`/`cognitivo`/`emocional`, `taste`+`contexto`, `limitaç`/`bug`).
- Tools críticas são citadas por nome (`taste_review`, `get_context`,
  `set_context`, `queue`, `play_context`).
- Bugs abertos são alertados (referência a `#6`, `#8` ou descrição).
- Sanity check de segurança: nenhum path absoluto, nenhum token ou
  credencial vaza.
- `create_server()` passa `INSTRUCTIONS` ao SDK MCP corretamente via
  kwarg `instructions=`.

Os testes são intencionalmente tolerantes a reformulações — validam
presença de conceitos, não de strings literais. Isso permite que as
instructions evoluam sem forçar update constante dos testes.

## Referência cruzada

- **Issue #14** — origem desta feature.
- **Issue #6** — `director_start` silencioso, mencionado no Bloco 4 até
  fix chegar em main.
- **Issue #8** — negações no contexto, mencionadas no Bloco 4 até v0.13.
- **Spec de v0.13** —
  `docs/superpowers/specs/2026-04-20-v0130-query-informada-negacoes-design.md`.
