"""Fontes externas de metadata musical (MusicBrainz, Last.fm, Reccobeats).

v0.9: só MusicBrainz. v0.10+ adiciona Last.fm. v0.11+ adiciona Reccobeats.
"""
from maestra_ai.core.external.enhancer import Enhancer, default_enhancer
from maestra_ai.core.external.lastfm import LastfmSource
from maestra_ai.core.external.reccobeats import ReccoBeatsSource
from maestra_ai.core.external.seed_expander import SeedExpander
from maestra_ai.core.external.types import (
    AudioFeaturesData,
    EnhancedTrack,
    EnhancementSource,
    LastfmData,
    MusicBrainzData,
    TrackInfo,
)

__all__ = [
    "AudioFeaturesData",
    "EnhancedTrack",
    "EnhancementSource",
    "Enhancer",
    "LastfmData",
    "LastfmSource",
    "MusicBrainzData",
    "ReccoBeatsSource",
    "SeedExpander",
    "TrackInfo",
    "default_enhancer",
]
