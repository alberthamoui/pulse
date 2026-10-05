"""
Hybrid matcher: artist TF-IDF + co-occurrence between artists + genre.

For the song's artist X and each playlist p:
    direct   = tf(X, p) * idf(X)
    indirect = sum of jaccard(X, Y) * tf(Y, p) * idf(Y) over the other artists Y in p
    score    = ALPHA * (direct + BETA * indirect) + (1 - ALPHA) * genre_overlap

If no playlist scores, lastfm_fallback() scores them through the similar artists from Last.fm.
"""

import math
from typing import Dict, List, Optional, Set
from .models import Track, PlaylistProfile, MatchResult
from .matcher_base import Matcher
from config.constants import ALGO_ALPHA as ALPHA, ALGO_BETA as BETA


class HybridMatcher(Matcher):

    def __init__(self, spotify_manager):
        self.profiles: Dict[str, PlaylistProfile] = {}
        self.idf: Dict[str, float] = {}
        self.artist_to_playlists: Dict[str, Set[str]] = {}
        self.name_to_id: Dict[str, str] = {}
        self.spotify = spotify_manager

    def train(self, profiles: Dict[str, PlaylistProfile], artist_names: Dict[str, str] = None) -> None:
        self.profiles = profiles
        self.name_to_id = {name.lower(): aid for aid, name in (artist_names or {}).items()}
        self._compute_idf()
        self._build_cooccurrence_index()

    def _compute_idf(self) -> None:
        """IDF = log(N / df) where df = number of playlists that contain the artist."""
        n = len(self.profiles)
        if n == 0:
            return
        df: Dict[str, int] = {}
        for profile in self.profiles.values():
            for artist_id in profile.artist_weights:
                df[artist_id] = df.get(artist_id, 0) + 1
        self.idf = {artist_id: math.log(n / count) for artist_id, count in df.items()}

    def _build_cooccurrence_index(self) -> None:
        """Index artist -> set of playlist IDs, for the Jaccard computation."""
        self.artist_to_playlists = {}
        for pl_id, profile in self.profiles.items():
            for artist_id in profile.artist_weights:
                self.artist_to_playlists.setdefault(artist_id, set()).add(pl_id)

    def _jaccard(self, artist_a: str, artist_b: str) -> float:
        set_a = self.artist_to_playlists.get(artist_a, set())
        set_b = self.artist_to_playlists.get(artist_b, set())
        if not set_a or not set_b:
            return 0.0
        intersection = len(set_a & set_b)
        union = len(set_a | set_b)
        return intersection / union if union else 0.0

    def _genre_overlap(
        self,
        track_genres: List[str],
        playlist_genre_weights: Dict[str, float],
    ) -> float:
        if not track_genres or not playlist_genre_weights:
            return 0.0
        matched = sum(playlist_genre_weights.get(g, 0.0) for g in track_genres)
        return matched / len(track_genres)

    def _score_all(self, track: Track) -> List[tuple]:
        """Computes and returns [(pl_id, pl_name, score, reason)] sorted by score desc."""
        if not track.artist_id:
            return []

        track_genres = self.spotify.get_artists_genres([track.artist_id]).get(track.artist_id, [])
        idf = self.idf.get(track.artist_id, 0.0)

        # Jaccard of the current artist vs every other one, computed once per match
        jaccard_cache: Dict[str, float] = {}

        results = []
        for pl_id, profile in self.profiles.items():
            tf = profile.artist_weights.get(track.artist_id, 0.0)
            overlap = self._genre_overlap(track_genres, profile.genre_weights)

            tfidf = tf * idf if tf > 0 else 0.0

            # Indirect signal: sum of Jaccard(X, Y) x TF-IDF(Y, playlist) for Y != X
            indirect = 0.0
            for other_artist, other_tf in profile.artist_weights.items():
                if other_artist == track.artist_id:
                    continue
                if other_artist not in jaccard_cache:
                    jaccard_cache[other_artist] = self._jaccard(track.artist_id, other_artist)
                j = jaccard_cache[other_artist]
                if j > 0:
                    indirect += j * other_tf * self.idf.get(other_artist, 0.0)

            artist_score = tfidf + BETA * indirect
            score = ALPHA * artist_score + (1 - ALPHA) * overlap

            if tfidf > 0 and indirect > 0:
                reason = f"direct={tfidf:.4f} + co-oc={indirect:.4f}"
            elif tfidf > 0:
                reason = f"direct: tf={tf:.2%} x idf={idf:.2f}"
            elif indirect > 0:
                reason = f"co-occurrence ({indirect:.4f})"
            else:
                reason = "no signal"

            results.append((pl_id, profile.name, score, reason))

        return sorted(results, key=lambda x: x[2], reverse=True)

    def match(self, track: Track, **kwargs) -> Optional[MatchResult]:
        scored = self._score_all(track)
        if not scored or scored[0][2] <= 0:
            return None
        pl_id, pl_name, score, reason = scored[0]
        return MatchResult(playlist_id=pl_id, playlist_name=pl_name, score=score, match_type='hybrid', reason=reason)

    def top_matches(self, track: Track, n: int = 5) -> List[MatchResult]:
        """Returns the top N matches with score > 0."""
        return [
            MatchResult(playlist_id=pl_id, playlist_name=pl_name, score=score, match_type='hybrid', reason=reason)
            for pl_id, pl_name, score, reason in self._score_all(track)[:n]
            if score > 0
        ]

    def lastfm_fallback(self, track: Track, api_key: str, n: int = 3) -> List[MatchResult]:
        """
        Last resort when every playlist scores 0.
        Looks up similar artists on Last.fm and scores the playlists through them.
        """
        from .lastfm_client import get_similar_artists
        similar = get_similar_artists(track.artist, api_key)
        if not similar:
            print("  Last.fm: no similar artists found.")
            return []

        print(f"  Last.fm: {len(similar)} similar artists found.")
        matched_any = False
        playlist_scores: Dict[str, float] = {}
        playlist_reasons: Dict[str, List[str]] = {}

        for sim in similar:
            artist_id = self.name_to_id.get(sim['name'].lower())
            if not artist_id:
                print(f"    ~ {sim['name']} ({sim['match']:.2f}) - not in any playlist")
                continue
            matched_any = True
            for pl_id, profile in self.profiles.items():
                tf = profile.artist_weights.get(artist_id, 0.0)
                if tf == 0:
                    continue
                idf = self.idf.get(artist_id, 0.0)
                contribution = sim['match'] * tf * idf
                playlist_scores[pl_id] = playlist_scores.get(pl_id, 0.0) + contribution
                playlist_reasons.setdefault(pl_id, []).append(
                    f"{sim['name']} ({sim['match']:.2f})"
                )

        if not matched_any:
            print("  Last.fm: found similar artists, but none of them is in your playlists.")

        results = [
            MatchResult(
                playlist_id=pl_id,
                playlist_name=self.profiles[pl_id].name,
                score=score,
                match_type='lastfm',
                reason=f"via Last.fm: {', '.join(playlist_reasons[pl_id][:3])}",
            )
            for pl_id, score in playlist_scores.items()
            if score > 0
        ]
        return sorted(results, key=lambda x: x.score, reverse=True)[:n]

    def get_name(self) -> str:
        return "Hybrid Matcher (Artist + Genre)"
