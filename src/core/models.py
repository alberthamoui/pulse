"""
Data models for the PULSE project.

Defines the data structures used across the application.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, List


@dataclass
class Track:
    """A Spotify track."""
    id: str
    name: str
    artist: str = ""
    artist_id: Optional[str] = None
    artist_ids: List[str] = field(default_factory=list)
    artist_names: List[str] = field(default_factory=list)

    def __repr__(self) -> str:
        return f"Track(name={self.name!r}, artist={self.artist!r})"


@dataclass
class PlaylistProfile:
    """Profile of a playlist built from its content."""
    id: str
    name: str
    artist_weights: Dict[str, float]  # { artist_id: relative_weight }
    genre_weights: Dict[str, float] = field(default_factory=dict)  # { genre: relative_weight }
    total_tracks: int = 0
    track_ids: list = field(default_factory=list)
    artist_counts: Dict[str, int] = field(default_factory=dict)  # { artist_id: tracks }

    def __repr__(self) -> str:
        return f"PlaylistProfile(name={self.name!r}, artists={len(self.artist_weights)}, genres={len(self.genre_weights)})"


@dataclass
class MatchResult:
    """Result of matching a song against the playlists."""
    playlist_id: str
    playlist_name: str
    score: float  # 0.0 to 1.0
    match_type: str  # 'artist_frequency', 'hybrid' or 'lastfm'
    reason: str = ""

    def __repr__(self) -> str:
        return f"MatchResult({self.playlist_name!r}, score={self.score:.2%})"

