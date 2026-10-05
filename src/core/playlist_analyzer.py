"""
Spotify playlist analyzer.

Extracts the data and builds playlist profiles based on the
relative frequency of artists.
"""

import time
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional
from .models import Track, PlaylistProfile
from .client import SpotifyManager
from config.constants import LAPLACE_ALPHA, PLAYLIST_WORKERS


def smoothed_weights(counts: Dict[str, int]) -> Dict[str, float]:
    """
    tf of each artist with Laplace smoothing: (n + α) / (total + α × V).

    The weights always come from the raw counts, so the profile can be updated
    (adding one track) without undoing the formula.
    """
    total = sum(counts.values())
    V = len(counts)
    return {
        artist_id: (count + LAPLACE_ALPHA) / (total + LAPLACE_ALPHA * V)
        for artist_id, count in counts.items()
    }


class SpotifyPlaylistAnalyzer:
    """Analyzes playlists and builds their content profiles."""
    
    def __init__(self, spotify_manager: SpotifyManager):
        """
        Initializes the analyzer with a Spotify client.
        
        Args:
            spotify_manager: SpotifyManager used to access the API
        """
        self.spotify = spotify_manager
    
    def fetch_tracks(self, playlist_id: str) -> tuple[List[Track], int]:
        """
        Fetches every track of a playlist, with pagination.

        Returns:
            (list of Track, total tracks reported by the API)
        """
        tracks = []
        total = 0
        offset = 0

        while True:
            response = self.spotify.sp.playlist_items(playlist_id, limit=100, offset=offset)
            if offset == 0:
                total = response.get('total', 0)

            for item in response.get('items', []):
                track = item.get('track') or item.get('item')
                if track and track.get('id') and track.get('type') == 'track':
                    artists = track.get('artists', [])
                    first_artist = artists[0] if artists else {}

                    track_obj = Track(
                        id=track['id'],
                        name=track.get('name', 'Unknown'),
                        artist=first_artist.get('name', 'Unknown'),
                        artist_id=first_artist.get('id')
                    )
                    tracks.append(track_obj)

            if not response.get('next'):
                break
            offset += 100

        return tracks, total
    
    def build_artist_profile(
        self, playlist_id: str
    ) -> tuple[Dict[str, float], int, list, Dict[str, str], Dict[str, int]]:
        """
        Builds a playlist's profile from the frequency of its artists.

        Returns:
            ({ artist_id: relative_weight }, total_tracks reported by the API, list of track IDs,
             { artist_id: artist_name }, { artist_id: tracks })
        """
        tracks, total_tracks = self.fetch_tracks(playlist_id)

        if not tracks:
            return {}, total_tracks, [], {}, {}

        track_ids = [t.id for t in tracks if t.id]
        artist_names = {t.artist_id: t.artist for t in tracks if t.artist_id and t.artist}
        counts = dict(Counter(t.artist_id for t in tracks if t.artist_id))

        return smoothed_weights(counts), total_tracks, track_ids, artist_names, counts
    
    def build_genre_profile(self, artist_weights: Dict[str, float]) -> Dict[str, float]:
        """
        Derives a genre weight dict from an existing artist_weights dict.
        Each genre inherits the weight of its artist; shared genres accumulate.
        Result is normalized to sum=1.0.
        """
        if not artist_weights:
            return {}
        artist_genres = self.spotify.get_artists_genres(list(artist_weights.keys()))
        raw: Dict[str, float] = {}
        for artist_id, weight in artist_weights.items():
            for genre in artist_genres.get(artist_id, []):
                raw[genre] = raw.get(genre, 0.0) + weight
        total = sum(raw.values())
        return {g: w / total for g, w in raw.items()} if total > 0 else {}

    def build_all_profiles(self, playlists: List[Dict[str, str]]) -> tuple[Dict[str, PlaylistProfile], Dict[str, str]]:
        """
        Builds the profiles of several playlists.

        Returns:
            (playlist_id → PlaylistProfile, artist_id → artist_name)
        """
        profiles = {}
        artist_names: Dict[str, str] = {}
        total = len(playlists)
        t_start = time.time()
        lock = threading.Lock()
        done = [0]

        def process(playlist: Dict) -> Optional[tuple]:
            playlist_id = playlist.get('id')
            playlist_name = playlist.get('name')
            if not playlist_id or not playlist_name:
                return None

            try:
                artist_weights, total_tracks, track_ids, names, counts = self.build_artist_profile(
                    playlist_id
                )
                genre_weights = self.build_genre_profile(artist_weights)
            except Exception as e:
                with lock:
                    done[0] += 1
                    print(f"  [{done[0]}/{total}] {playlist_name}... skipping ({e})")
                return None

            with lock:
                done[0] += 1
                print(f"  [{done[0]}/{total}] {playlist_name}... ok")

            return playlist_id, PlaylistProfile(
                id=playlist_id,
                name=playlist_name,
                artist_weights=artist_weights,
                genre_weights=genre_weights,
                total_tracks=total_tracks,
                track_ids=track_ids,
                artist_counts=counts,
            ), names

        with ThreadPoolExecutor(max_workers=PLAYLIST_WORKERS) as executor:
            for result in as_completed([executor.submit(process, p) for p in playlists]):
                data = result.result()
                if data:
                    pl_id, profile, names = data
                    profiles[pl_id] = profile
                    artist_names.update(names)

        elapsed = time.time() - t_start
        print(f"Analysis done in {elapsed:.1f}s ({len(profiles)}/{total} playlists).")
        return profiles, artist_names
    
