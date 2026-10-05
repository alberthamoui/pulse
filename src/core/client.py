"""
Spotify client - handles the communication with the Spotify API.

Provides methods for authentication, fetching songs and managing playlists.
"""

import json
import spotipy
from pathlib import Path
from spotipy.oauth2 import SpotifyOAuth
from typing import List, Dict, Optional
from .models import Track

_GENRES_FLAG_FILE = Path(__file__).parent.parent.parent / '.pulse_genres_flag.json'


class SpotifyManager:
    """Central manager for every operation on the Spotify API."""
    
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        """
        Initializes the Spotify client with OAuth credentials.
        
        Args:
            client_id: Spotify client ID
            client_secret: Spotify client secret
            redirect_uri: Redirect URI after authentication
        """
        scopes = (
            "user-read-currently-playing "
            "playlist-modify-private "
            "playlist-modify-public "
            "playlist-read-private "
            "playlist-read-collaborative "
            "user-library-read "
            "user-library-modify"
        )
        
        self.sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope=scopes
        ))
        self.api_calls = 0
        _orig = self.sp._internal_call
        def _counting_call(*args, **kwargs):
            self.api_calls += 1
            return _orig(*args, **kwargs)
        self.sp._internal_call = _counting_call

        self._genres_available = self._check_genres_available()

    def get_current_user(self) -> Optional[Dict]:
        """
        Gets the authenticated user's info.
        
        Returns:
            Dict with 'display_name' and 'id', or None on error
        """
        try:
            user = self.sp.current_user()
            return {
                'display_name': user.get('display_name'),
                'id': user.get('id')
            }
        except Exception as e:
            print(f"Error getting the user: {e}")
            return None

    def get_current_track(self) -> Optional[Track]:
        """
        Gets the current song, playing or paused (like the firmware: pausing to
        decide where it goes is the natural way to use Pulse).
        
        Returns:
            Track, or None if there's no song (no session, podcast or ad)
        """
        try:
            result = self.sp.current_user_playing_track()
            is_song = result and result.get('currently_playing_type', 'track') == 'track'
            if is_song and result.get('item'):
                item = result['item']
                artists = item.get('artists', [])
                artist_ids = [a.get('id') for a in artists if a.get('id')]
                artist_names = [a.get('name') for a in artists if a.get('name')]
                first_artist = artists[0] if artists else {}
                
                return Track(
                    id=item.get('id'),
                    name=item.get('name'),
                    artist=first_artist.get('name', 'Unknown'),
                    artist_id=first_artist.get('id'),
                    artist_ids=artist_ids,  # [a1, a2]
                    artist_names=artist_names,  # ["Name1", "Name2"]
                )

            return None  # no song
        except (spotipy.exceptions.SpotifyException, ConnectionError, TimeoutError):
            raise  # re-raises serious errors for main.py to handle
        except Exception as e:
            print(f"Unexpected error getting the current song: {e}")
            return None

    def get_user_playlists(self) -> List[Dict]:
        """
        Gets, with pagination, the user's playlists and the collaborative ones they follow
        (the same ones the firmware considers).

        Returns:
            List of dicts with 'id', 'name' and 'snapshot_id'
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

    def _check_genres_available(self) -> bool:
        if _GENRES_FLAG_FILE.exists():
            try:
                data = json.loads(_GENRES_FLAG_FILE.read_text())
                available = data.get('available', False)
                if not available:
                    print("Warning: genres endpoint unavailable (403). Matching by artist only.")
                return available
            except Exception:
                pass

        import logging
        spotipy_logger = logging.getLogger('spotipy.client')
        prev_level = spotipy_logger.level
        spotipy_logger.setLevel(logging.CRITICAL)
        try:
            self.sp._get('artists', ids='0TnOYISbd1XYRBk9myaseg')
            available = True
        except Exception:
            print("Warning: genres endpoint unavailable (403). Matching by artist only.")
            available = False
        finally:
            spotipy_logger.setLevel(prev_level)

        try:
            _GENRES_FLAG_FILE.write_text(json.dumps({'available': available}))
        except Exception:
            pass
        return available

    def get_artists_genres(self, artist_ids: List[str]) -> Dict[str, List[str]]:
        """
        Fetches genres for a list of artist IDs, batching 50 at a time.
        Returns empty dicts silently if the endpoint is unavailable.
        """
        if not self._genres_available:
            return {aid: [] for aid in artist_ids}

        import logging
        spotipy_logger = logging.getLogger('spotipy.client')
        result: Dict[str, List[str]] = {}
        for i in range(0, len(artist_ids), 50):
            batch = artist_ids[i:i + 50]
            prev_level = spotipy_logger.level
            spotipy_logger.setLevel(logging.CRITICAL)
            try:
                response = self.sp._get('artists', ids=','.join(batch))
                for artist in response.get('artists') or []:
                    if artist:
                        result[artist['id']] = artist.get('genres', [])
            except Exception as e:
                # Genre is a secondary signal: a failure (e.g. 429) doesn't break the matching
                print(f"Warning: failed to fetch genres, continuing without them ({e})")
                break
            finally:
                spotipy_logger.setLevel(prev_level)
        return {aid: result.get(aid, []) for aid in artist_ids}



    def is_track_liked(self, track_id: str) -> bool:
        try:
            result = self.sp.current_user_saved_tracks_contains([track_id])
            return bool(result and result[0])
        except Exception:
            return False

    def add_track_to_playlist(self, playlist_id: str, track_id: str) -> Optional[str]:
        """
        Adds a song to a playlist or to Liked Songs (id="liked").

        Returns:
            The playlist's new snapshot_id, "liked" for Liked Songs, None on error.
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

