"""Reads the playlists from Spotify and builds their profiles (artist counts and track IDs)."""

import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Tuple

from .client import SpotifyManager
from .constants import PLAYLIST_WORKERS
from .models import PlaylistProfile, Track


class SpotifyPlaylistAnalyzer:

    def __init__(self, spotify: SpotifyManager):
        self.spotify = spotify

    def fetch_tracks(self, playlist_id: str) -> List[Track]:
        """Every song in a playlist, with pagination. Episodes and local files are skipped."""
        tracks = []
        offset = 0
        while True:
            response = self.spotify.sp.playlist_items(playlist_id, limit=100, offset=offset)
            for entry in response.get('items', []):
                # Feb/2026: the API renamed "track" to "item"; both are accepted
                item = entry.get('track') or entry.get('item')
                if item and item.get('id') and item.get('type') == 'track':
                    first_artist = (item.get('artists') or [{}])[0]
                    tracks.append(Track(
                        id=item['id'],
                        name=item.get('name', 'Unknown'),
                        artist=first_artist.get('name', 'Unknown'),
                        artist_id=first_artist.get('id'),
                    ))
            if not response.get('next'):
                return tracks
            offset += 100

    def build_profile(self, playlist_id: str, name: str) -> Tuple[PlaylistProfile, Dict[str, str]]:
        """The playlist's profile and the names of its artists ({artist_id: name})."""
        tracks = self.fetch_tracks(playlist_id)
        profile = PlaylistProfile(
            id=playlist_id,
            name=name,
            artist_counts=dict(Counter(t.artist_id for t in tracks if t.artist_id)),
            track_ids=[t.id for t in tracks],
        )
        artist_names = {t.artist_id: t.artist for t in tracks if t.artist_id and t.artist}
        return profile, artist_names

    def build_all_profiles(self, playlists: List[Dict]) -> Tuple[Dict[str, PlaylistProfile], Dict[str, str]]:
        """
        Builds the profiles of several playlists in parallel. A playlist that fails
        to load (rate limit, network) is skipped and left out of the result.

        Returns (playlist_id -> PlaylistProfile, artist_id -> artist name).
        """
        profiles: Dict[str, PlaylistProfile] = {}
        artist_names: Dict[str, str] = {}
        total = len(playlists)
        t_start = time.time()
        lock = threading.Lock()
        done = 0

        def process(playlist: Dict):
            nonlocal done
            try:
                result = self.build_profile(playlist['id'], playlist['name'])
            except Exception as e:
                result, status = None, f"skipping ({e})"
            else:
                status = "ok"
            with lock:
                done += 1
                print(f"  [{done}/{total}] {playlist['name']}... {status}")
            return result

        with ThreadPoolExecutor(max_workers=PLAYLIST_WORKERS) as executor:
            for future in as_completed([executor.submit(process, p) for p in playlists]):
                result = future.result()
                if result:
                    profile, names = result
                    profiles[profile.id] = profile
                    artist_names.update(names)

        print(f"Analysis done in {time.time() - t_start:.1f}s ({len(profiles)}/{total} playlists).")
        return profiles, artist_names
