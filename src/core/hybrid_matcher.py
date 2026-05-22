"""
Matcher híbrido: combina frequência de artista + overlap de gênero.

- Artista conhecido na playlist: score = 0.8 * artist_weight + 0.2 * genre_overlap
- Artista desconhecido:           score = genre_overlap

Resolve casos onde o artista não está em nenhuma playlist mas seus gêneros coincidem.
"""

from typing import Dict, List, Optional
from .models import Track, PlaylistProfile, MatchResult
from .matcher_base import Matcher

ALPHA = 0.8  # peso do sinal de artista vs gênero


class HybridMatcher(Matcher):

    def __init__(self, spotify_manager):
        self.profiles: Dict[str, PlaylistProfile] = {}
        self.spotify = spotify_manager

    def train(self, profiles: Dict[str, PlaylistProfile]) -> None:
        self.profiles = profiles

    def _genre_overlap(
        self,
        track_genres: List[str],
        playlist_genre_weights: Dict[str, float],
    ) -> float:
        if not track_genres or not playlist_genre_weights:
            return 0.0
        matched = sum(playlist_genre_weights.get(g, 0.0) for g in track_genres)
        return matched / len(track_genres)

    def match(self, track: Track, **kwargs) -> Optional[MatchResult]:
        if not track.id_artista:
            return None

        track_genres = self.spotify.get_artists_genres([track.id_artista]).get(track.id_artista, [])

        best_id: Optional[str] = None
        best_name: Optional[str] = None
        best_score = -1.0

        for pl_id, profile in self.profiles.items():
            artist_w = profile.artista_weights.get(track.id_artista, 0.0)
            overlap = self._genre_overlap(track_genres, profile.genre_weights)

            score = ALPHA * artist_w + (1 - ALPHA) * overlap if artist_w > 0 else overlap

            if score > best_score:
                best_score, best_id, best_name = score, pl_id, profile.nome

        if best_id and best_score > 0:
            return MatchResult(
                playlist_id=best_id,
                playlist_name=best_name,
                score=best_score,
                match_type='hybrid',
            )
        return None

    def get_name(self) -> str:
        return "Hybrid Matcher (Artist + Genre)"
