"""Testes de deps.build_deps — instancia cores uma vez por processo."""
from __future__ import annotations

from unittest.mock import patch


def test_build_deps_retorna_dict_com_chaves_esperadas(monkeypatch, tmp_path):
    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
    from maestra_ai.core import storage
    storage.write_config({
        "client_id": "cid", "client_secret": "sec",
        "redirect_uri": "https://example.com/cb",
    })

    from maestra_mcp.deps import build_deps, _reset
    _reset()  # limpa cache entre testes

    with patch("maestra_ai.core.client.spotipy.Spotify"):
        deps = build_deps()

    assert "controller" in deps
    assert "taste" in deps
    assert "context_state" in deps
    assert "curator" in deps
    assert "history_analyzer" in deps
    assert "flow_analyzer" in deps


def test_build_deps_cacheia_entre_chamadas(monkeypatch, tmp_path):
    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
    from maestra_ai.core import storage
    storage.write_config({
        "client_id": "c", "client_secret": "s",
        "redirect_uri": "https://example.com/cb",
    })

    from maestra_mcp.deps import build_deps, _reset
    _reset()
    with patch("maestra_ai.core.client.spotipy.Spotify"):
        a = build_deps()
        b = build_deps()
    assert a is b


def test_build_deps_usa_playlist_id_do_config(monkeypatch, tmp_path):
    """CRITICAL-2: director_once crashava com playlist_id=None fixo.
    build_deps deve resolver playlist_id via config quando disponível."""
    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
    from maestra_ai.core import storage
    storage.write_config({
        "client_id": "cid", "client_secret": "sec",
        "redirect_uri": "https://example.com/cb",
        "playlist_id": "pl_X",
    })

    from maestra_mcp.deps import _reset, build_deps
    _reset()

    with patch("maestra_ai.core.client.spotipy.Spotify"):
        deps = build_deps()

    assert deps["director"].playlist_id == "pl_X"
    _reset()


def test_build_deps_sem_playlist_id_no_config_fica_none(monkeypatch, tmp_path):
    """Ausente no config: playlist_id fica None (tools que precisam falham
    com erro tipado do core; as que não precisam continuam funcionando)."""
    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
    from maestra_ai.core import storage
    storage.write_config({
        "client_id": "c", "client_secret": "s",
        "redirect_uri": "https://example.com/cb",
    })

    from maestra_mcp.deps import _reset, build_deps
    _reset()
    with patch("maestra_ai.core.client.spotipy.Spotify"):
        deps = build_deps()
    assert deps["director"].playlist_id is None
    _reset()


def test_build_deps_thread_safe(monkeypatch, tmp_path):
    """Fix M1: múltiplas threads chamando build_deps() em paralelo devem
    instanciar SpotifyController exatamente uma vez. Antes, sem lock, o
    double-check permitia corrida quando o bloco de inicialização ainda
    não havia terminado em outra thread."""
    import threading
    import time

    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
    from maestra_ai.core import storage
    storage.write_config({
        "client_id": "c", "client_secret": "s",
        "redirect_uri": "https://example.com/cb",
    })

    from maestra_mcp import deps as deps_mod
    deps_mod._reset()

    # Contador de inicializações do controller. Com sleep dentro do
    # __init__ amplificamos a janela de corrida — sem lock, múltiplas
    # threads passam pelo primeiro check e inicializam em paralelo.
    call_count = {"n": 0}
    count_lock = threading.Lock()

    def counting_init(self, *args, **kwargs):
        with count_lock:
            call_count["n"] += 1
        time.sleep(0.02)  # amplifica janela de corrida
        # Não chama o __init__ real para evitar I/O; atributos essenciais
        # são definidos abaixo.
        self.sp = None

    with patch("maestra_ai.core.client.SpotifyController.__init__",
               new=counting_init):
        results: list[dict] = []
        errors: list[BaseException] = []

        def worker():
            try:
                results.append(deps_mod.build_deps())
            except BaseException as e:  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    assert not errors, f"workers não deveriam falhar: {errors}"
    assert len(results) == 10
    assert all(r is results[0] for r in results), \
        "todas as threads devem receber a mesma instância cacheada"
    assert call_count["n"] == 1, \
        f"SpotifyController deveria ter sido instanciado 1x, veio {call_count['n']}"

    deps_mod._reset()
