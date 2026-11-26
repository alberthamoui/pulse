"""Spotify client: login, the current song, the user's playlists and adding a song."""

from typing import Dict, List, Optional

import spotipy
from spotipy.oauth2 import SpotifyOAuth

from .models import Track

SCOPES = (
    "user-read-currently-playing "
    "playlist-modify-private "
    "playlist-modify-public "
    "playlist-read-private "
    "playlist-read-collaborative "
    "user-library-read "
    "user-library-modify"
)


class SpotifyManager:
    """Every call Pulse makes to the Spotify API goes through here."""

    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        # The first run opens the browser to log in; spotipy keeps the token in .cache
        self.sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope=SCOPES,
        ))

        # Counts every API call, to show at the end of a run
        self.api_calls = 0
        original_call = self.sp._internal_call

        def counting_call(*args, **kwargs):
            self.api_calls += 1
            return original_call(*args, **kwargs)

        self.sp._internal_call = counting_call

    def get_current_track(self) -> Optional[Track]:
        """
        The current song, playing or paused (like the firmware: pausing to decide
        where it goes is the natural way to use Pulse). None if there's no song:
        no session, a podcast or an ad.

        Spotify and connection errors are raised for main.py to handle.
        """
        result = self.sp.current_user_playing_track()
        is_song = result and result.get('currently_playing_type', 'track') == 'track'
        if not (is_song and result.get('item')):
            return None

        item = result['item']
        first_artist = (item.get('artists') or [{}])[0]
        return Track(
            id=item.get('id'),
            name=item.get('name'),
            artist=first_artist.get('name', 'Unknown'),
            artist_id=first_artist.get('id'),
        )

    def get_user_playlists(self) -> List[Dict]:
        """
        The user's own playlists and the collaborative ones they follow (the same
        ones the firmware considers), as dicts with 'id', 'name' and 'snapshot_id'.
        """
        playlists = []
        try:
            user_id = self.sp.current_user()['id']
            result = self.sp.current_user_playlists(limit=50)
            while result:
                for p in result.get('items', []):
                    mine = p.get('owner', {}).get('id') == user_id
                    if mine or p.get('collaborative'):
                        playlists.append({
                            'id': p['id'],
                            'name': p['name'],
                            'snapshot_id': p.get('snapshot_id', ''),
                        })
                result = self.sp.next(result) if result.get('next') else None
        except Exception as e:
            print(f"Error getting playlists: {e}")
        return playlists

    def is_track_liked(self, track_id: str) -> bool:
        try:
            result = self.sp.current_user_saved_tracks_contains([track_id])
            return bool(result and result[0])
        except Exception:
            return False

    def add_track_to_playlist(self, playlist_id: str, track_id: str) -> Optional[str]:
        """
        Adds a song to a playlist or to Liked Songs (playlist_id="liked").

        Returns the playlist's new snapshot_id, "liked" for Liked Songs, or None on error.
        """
        try:
            if playlist_id == "liked":
                self.sp.current_user_saved_tracks_add([track_id])
                return "liked"
            result = self.sp.playlist_add_items(playlist_id, [track_id])
            return result.get('snapshot_id')
        except Exception as e:
            print(f"Error adding the song: {e}")
            return None
