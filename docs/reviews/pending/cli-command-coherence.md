# Review pendente — coerência de comandos CLI

**Aberto em:** 2026-04-20
**Origem:** side-note durante brainstorming do spec v0.9 (fontes externas)
**Prioridade:** média — revisitar quando houver janela natural (ex: antes de
cortar v1.0, ou ao adicionar mais comandos)

## Escopo

Fazer passada global em toda a surface de comandos `maestra` para avaliar:

1. **Padrão de estrutura** — comandos estão consistentes em verbo/objeto?
   Ex: `maestra context set`, `maestra config external set-key`,
   `maestra cache refresh`. Todos usam verbo após o grupo? Algum destoa?

2. **Escolha de palavras** — cada comando comunica diretamente a ação que
   realiza? Algum verbo é ambíguo, técnico demais ou fora do tom do projeto?

3. **Agrupamento** — subcomandos estão agrupados de forma coerente? Algum
   grupo inflou demais e deveria ser quebrado? Algum grupo com um único
   comando que poderia virar flat?

4. **Nomes versus ações** — `maestra profile show` mostra, `maestra
   config status` também mostra (mas não se chama `show`). Reconciliar
   `show` × `status` × `list` × `get`.

5. **Flags versus subcomandos** — quando algo virou flag (`--json`,
   `--human`) e quando virou subcomando? Existe padrão?

6. **Help strings** — cada `help=` do argparse descreve a ação com clareza
   e no mesmo registro linguístico?

## Abordagem sugerida

- Inventariar todos os comandos via `maestra --help` recursivo.
- Tabelar em planilha: grupo | comando | verbo | objeto | help string | observações.
- Propor diretrizes de padronização.
- Fazer um spec de rename + deprecation window (releases que mantêm alias
  antigo com warning) antes de cortar os nomes antigos.

## Não fazer agora

- Renames sem spec. Comandos CLI são interface pública; mudar nomes quebra
  scripts de usuários e agents MCP. Sempre com deprecation window.

## Referências

- Padrão atual (v0.8.0-alpha.7):
  - `auth`, `basic`, `config`, `context`, `curate`, `director`, `doctor`,
    `feedback`, `flow`, `help`, `history`, `init`, `onboard`, `playback`,
    `playlist`, `profile`, `rollback`, `taste`
- Backlog consolidado: `docs/reviews/2026-04-19-backlog-consolidado.md`
