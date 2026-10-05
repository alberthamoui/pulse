"""
PULSE Core - main module with the central classes and models.

Exports the main classes for use in other modules.
"""

from .models import Track, PlaylistProfile, MatchResult
from .client import SpotifyManager
from .playlist_analyzer import SpotifyPlaylistAnalyzer
from .matcher_base import Matcher
from .artist_frequency_matcher import ArtistFrequencyMatcher
from .hybrid_matcher import HybridMatcher

__all__ = [
    'Track',
    'PlaylistProfile',
    'MatchResult',
    'SpotifyManager',
    'SpotifyPlaylistAnalyzer',
    'Matcher',
    'ArtistFrequencyMatcher',
    'HybridMatcher',
]
