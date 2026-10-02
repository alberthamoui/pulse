"""
PULSE Core - Módulo principal com classes e modelos centrais.

Exporta as principais classes para uso em outros módulos.
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
