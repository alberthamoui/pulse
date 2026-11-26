"""Data shared by the whole app: the song, the playlist profiles and the ranking results."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .constants import LAPLACE_ALPHA


def smoothed_weights(counts: Dict[str, int]) -> Dict[str, float]:
    """
    tf of each artist with Laplace smoothing: (n + α) / (total + α × V).

    Without the smoothing, small playlists win: one artist in a 3-song playlist
    gets 0.33 and beats everything else.
    """
    total = sum(counts.values())
    V = len(counts)
    return {
        artist_id: (count + LAPLACE_ALPHA) / (total + LAPLACE_ALPHA * V)
        for artist_id, count in counts.items()
    }


@dataclass
class Track:
    """A Spotify track. Only its main artist is used in the ranking."""
    id: Optional[str]  # None for local files, which aren't in the Spotify catalog
    name: str
    artist: str = ""
    artist_id: Optional[str] = None


@dataclass
class PlaylistProfile:
    """
    What a playlist is made of: how many of its tracks are by each artist (main
    artist only) and its track IDs, to spot duplicates. The weights are always
    derived from the raw counts, so adding a track doesn't need to undo the formula.
    """
    id: str
    name: str
    artist_counts: Dict[str, int] = field(default_factory=dict)
    track_ids: List[str] = field(default_factory=list)
    artist_weights: Dict[str, float] = field(init=False, repr=False)

    def __post_init__(self):
        self.artist_weights = smoothed_weights(self.artist_counts)

    def add_track(self, track: Track) -> None:
        """Updates the profile after the track was added to the playlist."""
        self.track_ids.append(track.id)
        if track.artist_id:
            self.artist_counts[track.artist_id] = self.artist_counts.get(track.artist_id, 0) + 1
            self.artist_weights = smoothed_weights(self.artist_counts)

    def to_dict(self) -> dict:
        """What goes in the cache (the weights are derived on load)."""
        return {
            'id': self.id,
            'name': self.name,
            'artist_counts': self.artist_counts,
            'track_ids': self.track_ids,
        }


@dataclass
class MatchResult:
    """A candidate playlist for the current song."""
    playlist_id: str
    playlist_name: str
    score: float  # only meaningful relative to the other candidates
    reason: str = ""
