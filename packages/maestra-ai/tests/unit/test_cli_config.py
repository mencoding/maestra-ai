"""Testes do subcomando `maestra config` (get/set/list).

Invoca os handlers direto (em vez de subprocess) para velocidade.
"""
from __future__ import annotations

import argparse
import json

import pytest

from maestra_ai.cli import config as cli_config
from maestra_ai.core import storage

_ID = "37i9dQZF1DXcBWIGoYBM5M"


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("MAESTRA_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("MAESTRA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("MAESTRA_STATE_DIR", str(tmp_path / "state"))
    yield


def _ns(**kwargs):
    ns = argparse.Namespace(human=False, json=False)
    for k, v in kwargs.items():
        setattr(ns, k, v)
    return ns


def test_config_set_playlist_id_normaliza_url(capsys):
    url = f"https://open.spotify.com/playlist/{_ID}?si=abc"
    cli_config.cmd_config_set(_ns(key="playlist_id", value=url))
    assert storage.read_config()["playlist_id"] == _ID


def test_config_set_playlist_id_normaliza_uri(capsys):
    uri = f"spotify:playlist:{_ID}"
    cli_config.cmd_config_set(_ns(key="playlist_id", value=uri))
    assert storage.read_config()["playlist_id"] == _ID


def test_config_set_playlist_id_id_puro_passa(capsys):
    cli_config.cmd_config_set(_ns(key="playlist_id", value=_ID))
    assert storage.read_config()["playlist_id"] == _ID


def test_config_set_key_invalida_erro(capsys):
    with pytest.raises(SystemExit) as exc:
        cli_config.cmd_config_set(_ns(key="hacker_key", value="x"))
    assert exc.value.code != 0
    err = capsys.readouterr().err
    # Mensagem deve listar keys aceitas.
    assert "playlist_id" in err


def test_config_get_retorna_valor(capsys):
    cli_config.cmd_config_set(_ns(key="playlist_name", value="Sincronia Iris"))
    capsys.readouterr()  # descarta saída do set
    cli_config.cmd_config_get(_ns(key="playlist_name"))
    out = capsys.readouterr().out
    assert "Sincronia Iris" in out


def test_config_get_playlist_id_retorna_id_puro(capsys):
    url = f"https://open.spotify.com/playlist/{_ID}?si=xyz"
    cli_config.cmd_config_set(_ns(key="playlist_id", value=url))
    capsys.readouterr()
    cli_config.cmd_config_get(_ns(key="playlist_id"))
    out = capsys.readouterr().out
    assert _ID in out
    assert "open.spotify" not in out


def test_config_list_redacta_secrets(capsys):
    cli_config.cmd_config_set(_ns(key="client_id", value="public_id_123"))
    cli_config.cmd_config_set(
        _ns(key="client_secret", value="super_secret_xxxxxxxxxxxxxxxxxxxxxxx"),
    )
    capsys.readouterr()
    cli_config.cmd_config_list(_ns())
    out = capsys.readouterr().out
    assert "super_secret_xxxxxxxxxxxxxxxxxxxxxxx" not in out
    assert "public_id_123" in out


def test_config_get_chave_ausente(capsys):
    # Chave válida mas sem valor — retorna null/None sem crash.
    cli_config.cmd_config_get(_ns(key="playlist_id"))
    out = capsys.readouterr().out
    # Deve ser parseável como JSON e null.
    data = json.loads(out)
    assert data is None
