"""MEDIUM-3: rotação do audit.log por tamanho além de por idade."""
from __future__ import annotations


def test_rota_quando_excede_tamanho_maximo(monkeypatch, tmp_path):
    monkeypatch.setenv("MAESTRA_STATE_DIR", str(tmp_path))
    from maestra_ai.core import audit, storage

    # Grava muitos eventos até ultrapassar o limite.
    monkeypatch.setattr(audit, "_MAX_SIZE_BYTES", 1024)  # 1KB para ser rápido
    for i in range(100):
        audit.log(tool="test", args={"i": i}, result={"ok": True})

    # Deve existir pelo menos um arquivo arquivado .gz
    archives = list(storage.state_dir().glob("audit.*.jsonl.gz"))
    assert len(archives) >= 1, \
        f"esperava arquivo arquivado, veio: {list(storage.state_dir().iterdir())}"

    # E o audit.log ativo deve estar abaixo de ~2x o limite
    active = storage.state_dir() / "audit.jsonl"
    if active.exists():
        assert active.stat().st_size <= 1024 * 2, \
            "audit ativo deveria ter sido rotacionado"


def test_nao_rota_abaixo_do_tamanho(monkeypatch, tmp_path):
    monkeypatch.setenv("MAESTRA_STATE_DIR", str(tmp_path))
    from maestra_ai.core import audit, storage

    monkeypatch.setattr(audit, "_MAX_SIZE_BYTES", 10 * 1024 * 1024)  # 10MB
    audit.log(tool="test", args={}, result={"ok": True})

    archives = list(storage.state_dir().glob("audit.*.jsonl.gz"))
    assert len(archives) == 0, "não deveria rotacionar para 1 evento pequeno"
