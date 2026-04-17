# Teste de paridade manual

Roda periodicamente durante a janela de 7 dias após migração.

## Comandos

```bash
maestra now
maestra flow review --window 10
maestra taste review --top 5
maestra context show
```

## Critério

Estruturas JSON equivalentes ao que o `workspace/maestra` antigo retornava com
os mesmos arquivos em `$MAESTRA_DATA_DIR`.

Teste automatizado (`test_parity.py`) entra no Plano 2.
