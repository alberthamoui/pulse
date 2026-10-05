"""
Matcher based on the relative frequency of artists.

Baseline algorithm, simpler than the HybridMatcher:
- Each playlist has a profile { artist_id: relative_weight }
- A song goes to the playlist where its artist has the highest weight
"""

from typing import Dict, Optional
from .models import Track, PlaylistProfile, MatchResult
from .matcher_base import Matcher


class ArtistFrequencyMatcher(Matcher):
    """
    Matcher that uses the relative frequency of artists in each playlist.
    
    The algorithm is simple and fast: it looks for the playlist where the artist
    of the current song has the highest weight (relative frequency).
    """
    
    def __init__(self):
        """Initializes the matcher."""
        self.profiles: Dict[str, PlaylistProfile] = {}
    
    def train(self, profiles: Dict[str, PlaylistProfile]) -> None:
        """
        Trains the matcher with the playlist profiles.
        
        Args:
            profiles: Dict mapping playlist_id → PlaylistProfile
        """
        self.profiles = profiles
    
    def match(self, track: Track, **kwargs) -> Optional[MatchResult]:
        """
        Finds the best playlist based on the artist's frequency.
        
        Args:
            track: Track with artist_id set
            **kwargs: Extra arguments (not used by this matcher)
            
        Returns:
            MatchResult with the best playlist, or None if the artist isn't found
        """
        if not track.artist_id:
            return None
        
        best_playlist_id = None
        best_playlist_name = None
        best_score = 0.0
        
        # Finds the playlist where this artist has the highest weight
        for playlist_id, profile in self.profiles.items():
            artist_weight = profile.artist_weights.get(track.artist_id, 0.0)
            
            if artist_weight > best_score:
                best_score = artist_weight
                best_playlist_id = playlist_id
                best_playlist_name = profile.name
        
        if best_playlist_id and best_score > 0:
            return MatchResult(
                playlist_id=best_playlist_id,
                playlist_name=best_playlist_name,
                score=best_score,
                match_type='artist_frequency'
            )
        
        return None
    
    def get_name(self) -> str:
        """Returns the algorithm's name."""
        return "Artist Frequency Matcher"
    
    def get_artist_stats(self, playlist_id: str) -> Dict[str, float]:
        """
        Returns the artist stats of a playlist.
        
        Args:
            playlist_id: Playlist ID
            
        Returns:
            Dict with the artists sorted by descending weight
        """
        if playlist_id not in self.profiles:
            return {}
        
        profile = self.profiles[playlist_id]
        # Sorts the artists by weight (highest first)
        return dict(sorted(
            profile.artist_weights.items(),
            key=lambda x: x[1],
            reverse=True
        ))
