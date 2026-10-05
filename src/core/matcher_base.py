"""
Abstract matcher - interface for algorithms that match songs to playlists.
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional
from .models import Track, MatchResult


class Matcher(ABC):
    """
    Abstract class for algorithms that match songs to playlists.
    
    A matcher takes a song and returns the best playlist for it
    based on some strategy (artist frequency, TF-IDF, etc).
    """
    
    @abstractmethod
    def train(self, data: Dict) -> None:
        """
        Trains the matcher with the playlist data.
        
        Args:
            data: Algorithm-specific data (profiles, features, etc)
        """
        pass
    
    @abstractmethod
    def match(self, track: Track, **kwargs) -> Optional[MatchResult]:
        """
        Finds the best playlist for a track.
        
        Args:
            track: Track to match
            **kwargs: Extra algorithm-specific arguments
            
        Returns:
            MatchResult with the best playlist found, or None if there's no match
        """
        pass
    
    @abstractmethod
    def get_name(self) -> str:
        """Returns the algorithm's descriptive name."""
        pass
