"""
Ranks the playlists for a song: TF-IDF of the song's artist plus a co-occurrence
signal between artists. For the artist X and each playlist p:

    direct   = tf(X, p) * idf(X)
    indirect = sum of jaccard(X, Y) * tf(Y, p) * idf(Y) over the other artists Y in p
    score    = direct + CO_OCCURRENCE_WEIGHT * indirect

tf comes from PlaylistProfile.artist_weights (Laplace smoothed). If no playlist
scores, lastfm_fallback() scores them through the similar artists from Last.fm.
"""

import math
from typing import Dict, List, Set

from . import lastfm_client
from .constants import CO_OCCURRENCE_WEIGHT
from .models import MatchResult, PlaylistProfile, Track


class PlaylistMatcher:

    def __init__(self, profiles: Dict[str, PlaylistProfile], artist_names: Dict[str, str]):
        self.profiles = profiles
        # Last.fm returns artist names: this links them to the IDs in the profiles
        self.name_to_id = {name.lower(): aid for aid, name in artist_names.items()}

        # idf = log(N / df), df = number of playlists that contain the artist
        self.artist_to_playlists: Dict[str, Set[str]] = {}
        for pl_id, profile in profiles.items():
            for artist_id in profile.artist_weights:
                self.artist_to_playlists.setdefault(artist_id, set()).add(pl_id)
        n = len(profiles)
        self.idf = {aid: math.log(n / len(pls)) for aid, pls in self.artist_to_playlists.items()}

    def _jaccard(self, artist_a: str, artist_b: str) -> float:
        """How often the two artists end up in the same playlists (0 to 1)."""
        set_a = self.artist_to_playlists.get(artist_a, set())
        set_b = self.artist_to_playlists.get(artist_b, set())
        union = len(set_a | set_b)
        return len(set_a & set_b) / union if union else 0.0

    def top_matches(self, track: Track, n: int = 3) -> List[MatchResult]:
        """The n best playlists for the track, only those with score > 0."""
        if not track.artist_id:
            return []

        artist = track.artist_id
        idf = self.idf.get(artist, 0.0)
        jaccard: Dict[str, float] = {}  # computed once per artist, shared by every playlist

        results = []
        for pl_id, profile in self.profiles.items():
            tf = profile.artist_weights.get(artist, 0.0)
            direct = tf * idf

            indirect = 0.0
            for other, other_tf in profile.artist_weights.items():
                if other == artist:
                    continue
                if other not in jaccard:
                    jaccard[other] = self._jaccard(artist, other)
                indirect += jaccard[other] * other_tf * self.idf.get(other, 0.0)

            score = direct + CO_OCCURRENCE_WEIGHT * indirect
            if score <= 0:
                continue
            if direct > 0 and indirect > 0:
                reason = f"direct={direct:.4f} + co-oc={indirect:.4f}"
            elif direct > 0:
                reason = f"direct: tf={tf:.2%} x idf={idf:.2f}"
            else:
                reason = f"co-occurrence ({indirect:.4f})"
            results.append(MatchResult(pl_id, profile.name, score, reason))

        return sorted(results, key=lambda r: r.score, reverse=True)[:n]

    def lastfm_fallback(self, track: Track, api_key: str, n: int = 3) -> List[MatchResult]:
        """
        Last resort when no playlist scores: looks up similar artists on Last.fm and
        scores each playlist by sum(match * tf * idf) over the similar artists in it.
        """
        similar = lastfm_client.get_similar_artists(track.artist, api_key)
        if not similar:
            print("  Last.fm: no similar artists found.")
            return []
        print(f"  Last.fm: {len(similar)} similar artists found.")

        scores: Dict[str, float] = {}
        reasons: Dict[str, List[str]] = {}
        for sim in similar:
            artist_id = self.name_to_id.get(sim['name'].lower())
            if not artist_id:
                continue
            for pl_id, profile in self.profiles.items():
                tf = profile.artist_weights.get(artist_id, 0.0)
                if tf == 0:
                    continue
                scores[pl_id] = scores.get(pl_id, 0.0) + sim['match'] * tf * self.idf.get(artist_id, 0.0)
                reasons.setdefault(pl_id, []).append(f"{sim['name']} ({sim['match']:.2f})")

        if not reasons:
            print("  Last.fm: found similar artists, but none of them is in your playlists.")

        results = [
            MatchResult(pl_id, self.profiles[pl_id].name, score,
                        f"via Last.fm: {', '.join(reasons[pl_id][:3])}")
            for pl_id, score in scores.items()
            if score > 0
        ]
        return sorted(results, key=lambda r: r.score, reverse=True)[:n]
