"""Fontes externas de metadata musical (MusicBrainz, Last.fm, GetSongBPM).

v0.9: só MusicBrainz. v0.10+ adiciona Last.fm e GetSongBPM.
"""
from maestra_ai.core.external.enhancer import Enhancer, default_enhancer
from maestra_ai.core.external.types import (
    EnhancedTrack,
    EnhancementSource,
    MusicBrainzData,
    TrackInfo,
)

__all__ = [
    "EnhancedTrack",
    "EnhancementSource",
    "Enhancer",
    "MusicBrainzData",
    "TrackInfo",
    "default_enhancer",
]
