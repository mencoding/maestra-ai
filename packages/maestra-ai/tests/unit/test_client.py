"""Testes do SpotifyController — foco em DI e rate limit.

P1-4: construtor aceita `sp` (spotipy.Spotify pré-configurado) ou
`auth_manager` (SpotifyOAuth/outro) via DI, sem passar pelo OAuth
default. Pré-requisito para Fase 3 e para testes que não podem
depender de credenciais reais.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from maestra_ai.core.client import SpotifyController


def test_di_com_sp_pronto_nao_instancia_oauth():
    """Com sp injetado, controller usa direto — não toca SpotifyOAuth."""
    sp = MagicMock()
    controller = SpotifyController(sp=sp)
    assert controller.sp is sp


def test_di_com_auth_manager_custom_passa_para_spotipy(monkeypatch):
    """Com auth_manager injetado, spotipy.Spotify recebe-o; não cria OAuth default."""
    captured = {}

    class FakeSpotify:
        def __init__(self, auth_manager=None):
            captured["auth_manager"] = auth_manager

    monkeypatch.setattr("maestra_ai.core.client.spotipy.Spotify", FakeSpotify)

    fake_auth = object()
    controller = SpotifyController(auth_manager=fake_auth)
    assert captured["auth_manager"] is fake_auth
    assert isinstance(controller.sp, FakeSpotify)
