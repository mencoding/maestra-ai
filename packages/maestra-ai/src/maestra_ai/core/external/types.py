"""TypedDicts + Protocol das fontes externas de metadata."""
from __future__ import annotations

from typing import Literal, Protocol, TypedDict


class TrackInfo(TypedDict):
    uri: str
    name: str
    artists: list[str]
    isrc: str | None


class MusicBrainzData(TypedDict):
    mbid: str
    genres: list[str]
    tags: list[str]


class LastfmData(TypedDict):
    top_tags: list[str]
    playcount: int
    listeners: int
    similar_artists: list[str]


class AudioFeaturesData(TypedDict):
    tempo: float
    key: int
    mode: int
    loudness: float
    acousticness: float
    danceability: float
    energy: float
    instrumentalness: float
    liveness: float
    speechiness: float
    valence: float


class EnhancedTrack(TypedDict):
    uri: str
    isrc: str | None
    artist_mbid: str | None
    musicbrainz: MusicBrainzData | None
    lastfm: LastfmData | None
    reccobeats: AudioFeaturesData | None
    sources: list[str]
    enhanced_at: str
    match_method: Literal["isrc", "name"]


class SourceResult(TypedDict, total=False):
    musicbrainz: MusicBrainzData
    lastfm: LastfmData
    reccobeats: AudioFeaturesData
    artist_mbid: str
    match_method: Literal["isrc", "name"]


class EnhancementSource(Protocol):
    name: str

    def is_configured(self) -> bool: ...

    def enhance_track(self, track: TrackInfo) -> SourceResult | None: ...
