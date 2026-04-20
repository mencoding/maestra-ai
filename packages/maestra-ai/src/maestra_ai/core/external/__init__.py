"""Fontes externas de metadata musical (MusicBrainz, Last.fm, GetSongBPM).

v0.9: só MusicBrainz. v0.10+ adiciona Last.fm e GetSongBPM.
"""
from maestra_ai.core.external.enhancer import Enhancer, default_enhancer
from maestra_ai.core.external.getsongbpm import GetSongBpmSource
from maestra_ai.core.external.lastfm import LastfmSource
from maestra_ai.core.external.seed_expander import SeedExpander
from maestra_ai.core.external.types import (
    BpmData,
    EnhancedTrack,
    EnhancementSource,
    LastfmData,
    MusicBrainzData,
    TrackInfo,
)

__all__ = [
    "BpmData",
    "EnhancedTrack",
    "EnhancementSource",
    "Enhancer",
    "GetSongBpmSource",
    "LastfmData",
    "LastfmSource",
    "MusicBrainzData",
    "SeedExpander",
    "TrackInfo",
    "default_enhancer",
]
