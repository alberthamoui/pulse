"""
PULSE - Takes the song playing on Spotify and adds it to the playlist it fits best.
If there's no match, it goes to the fallback playlist (FALLBACK_PULSE).

Usage:
    python main.py                 # shows the suggestions and asks where to add
    python main.py --auto          # adds to the best match if it passes the minimum score
    python main.py --dry-run       # only shows the ranking
    python main.py --refresh       # reads every playlist again before running
    python main.py --cache-refresh # only rebuilds the cache, without looking at the current song
"""

import sys
from pathlib import Path
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / 'src'))  # the core package
sys.path.insert(0, str(ROOT))          # config/settings.py
import time
import spotipy
from core.cache import Cache, load_cache, save_cache, sync_profiles
from core.client import SpotifyManager
from core.matcher import PlaylistMatcher
from core.models import Track
from core.user_config import INVALID_FALLBACK, SetupError, Settings, load_config, load_settings


def connect(settings: Settings) -> SpotifyManager:
    print("Connecting to Spotify...")
    return SpotifyManager(
        client_id=settings.client_id,
        client_secret=settings.client_secret,
        redirect_uri=settings.redirect_uri,
    )


def prompt_playlist_choice(candidates: list, fallback_id: str, cache: Cache,
                           spotify: SpotifyManager, track: Track) -> tuple[str, str] | None:
    """
    Shows the playlist menu and returns (playlist_id, playlist_name).
    Returns None if the user cancels.
    """
    fallback = cache.profiles.get(fallback_id)
    in_liked    = spotify.is_track_liked(track.id)
    in_fallback = fallback is not None and track.id in fallback.track_ids

    print()
    if candidates:
        print("Where should it go?")
    else:
        print("No matching playlist found. Pick one manually:")
    for i, r in enumerate(candidates, 1):
        reason = f" ({r.reason})" if r.reason else ""
        marker = " (recommended)" if i == 1 else ""
        print(f"  [{i}] {r.playlist_name}: {r.score:.2%}{reason}{marker}")
    print(f"  [l] Liked Songs{' (already there)' if in_liked else ''}")
    print(f"  [f] FALLBACK_PULSE{' (already there)' if in_fallback else ''}")
    print("  [n] Don't add")
    print()

    options = '/'.join([str(i) for i in range(1, len(candidates) + 1)] + ['l', 'f', 'n'])
    default = '1' if candidates else 'f'  # with no suggestion, Enter goes to the fallback
    while True:
        choice = input(f"Choose [{options}] (Enter = {default}): ").strip() or default

        if choice == 'l':
            return "liked", "Liked Songs"
        if choice == 'f':
            return fallback_id, "FALLBACK_PULSE"
        if choice == 'n':
            return None
        if choice.isdigit() and 1 <= int(choice) <= len(candidates):
            r = candidates[int(choice) - 1]
            return r.playlist_id, r.playlist_name
        print("  Invalid option, try again.")


def run_cache_refresh() -> dict:
    """Rebuilds the playlist cache without checking the current song."""
    t_start = time.time()
    try:
        config = load_config()
        settings = load_settings()
    except SetupError as e:
        return {'success': False, 'error': str(e)}

    spotify = connect(settings)
    print("Fetching playlists...")
    cache = sync_profiles(spotify, spotify.get_user_playlists(), None)  # None forces a full rebuild
    if not cache.profiles:
        return {'success': False, 'error': 'No profile was built'}

    save_cache(config.cache_path, cache)
    elapsed = round(time.time() - t_start, 1)
    print(f"Cache updated: {len(cache.profiles)} playlists [{elapsed}s | {spotify.api_calls} API calls]")
    return {'success': True, 'playlists': len(cache.profiles), 'elapsed': elapsed}


def run_pulse(mode: str = 'normal') -> dict:
    """
    Runs the whole Pulse cycle: current song, playlist sync, ranking, choice and add.

    Returns:
        {'success': True,  'track': '...', 'playlist': '...', 'elapsed': 1.2}
        {'success': False, 'error': 'message'}
    """
    t_start = time.time()
    try:
        config = load_config()
        if not config.fallback_playlist_id:
            raise SetupError(INVALID_FALLBACK)
        settings = load_settings()
    except SetupError as e:
        return {'success': False, 'error': str(e)}
    fallback_id = config.fallback_playlist_id

    spotify = connect(settings)

    def stats() -> str:
        return f"[{time.time() - t_start:.1f}s | {spotify.api_calls} API calls]"

    try:
        track = spotify.get_current_track()
    except (spotipy.exceptions.SpotifyBaseException, OSError) as e:
        # A Spotify app in development mode only lets in the accounts registered on it
        if getattr(e, 'http_status', None) == 403:
            return {'success': False, 'error': "Spotify refused access (403). If this account doesn't own "
                                               "the Spotify app, add it under User Management in the "
                                               "developer dashboard (see Troubleshooting in the README)."}
        return {'success': False, 'error': f'Spotify/connection error: {e}'}

    if not track:
        print(f"Nothing is playing right now. {stats()}")
        return {'success': False, 'error': 'Nothing playing'}

    print(f"Current song: {track.name} - {track.artist}")
    if not track.id:
        return {'success': False, 'error': "Local file: not in the Spotify catalog, it can't be added"}

    print("Checking playlists...")
    cached = None if mode == 'refresh' else load_cache(config.cache_path)
    cache = sync_profiles(spotify, spotify.get_user_playlists(), cached)
    if cache.profiles:
        save_cache(config.cache_path, cache)

    candidates = []
    if cache.profiles:
        matcher = PlaylistMatcher(cache.profiles, cache.artist_names)
        candidates = matcher.top_matches(track, n=3)
        if not candidates and settings.lastfm_api_key:
            print("No direct match. Trying Last.fm...")
            candidates = matcher.lastfm_fallback(track, settings.lastfm_api_key)
            if candidates:
                print("Match found through Last.fm.")
    best = candidates[0] if candidates else None

    already_in = [p.name for p in cache.profiles.values() if track.id in p.track_ids]
    if already_in:
        print(f"\nWarning: this song is already in: {', '.join(already_in)}")
        if mode == 'auto':
            print(f"Automatic mode: not adding a duplicate. {stats()}")
            return {'success': False, 'error': 'Song is already in a playlist'}
        if mode != 'dry-run':
            if input("Continue anyway? [y/n] (Enter = n): ").strip().lower() != 'y':
                print(f"Cancelled. {stats()}")
                return {'success': False, 'error': 'Cancelled - song already in a playlist'}
            print()

    if mode == 'dry-run':
        if not candidates:
            print("No candidate found.")
        for r in candidates:
            print(f"  {r.playlist_name}: {r.score:.2%} ({r.reason})")
        destination = best.playlist_name if best else 'FALLBACK_PULSE'
        print(f"\nWould be added to: {destination} {stats()}\n")
        return {'success': True, 'track': f"{track.name} - {track.artist}", 'playlist': destination,
                'elapsed': round(time.time() - t_start, 1)}

    if mode == 'auto':
        # Only adds without asking if the best match passes the minimum score
        if not best:
            print(f"No candidates for auto-add. {stats()}")
            return {'success': False, 'error': 'No candidates for auto-add'}
        if best.score < config.auto_add_min_score:
            print(f"Low score ({best.score:.2%} < {config.auto_add_min_score:.2%}). "
                  f"Not adding automatically. {stats()}")
            return {'success': False, 'error': 'Score below the auto-add minimum'}
        playlist_id, playlist_name = best.playlist_id, best.playlist_name
    else:
        choice = prompt_playlist_choice(candidates, fallback_id, cache, spotify, track)
        if choice is None:
            print(f"Cancelled. {stats()}")
            return {'success': False, 'error': 'Cancelled by user'}
        playlist_id, playlist_name = choice
        print()

    new_snapshot = spotify.add_track_to_playlist(playlist_id, track.id)
    if new_snapshot is None:
        return {'success': False, 'error': 'Failed to add to the playlist'}

    if playlist_id in cache.profiles and new_snapshot:
        cache.record_add(playlist_id, track, new_snapshot)
        save_cache(config.cache_path, cache)

    print(f"Added to: {playlist_name}")
    print(stats())
    return {'success': True, 'track': f"{track.name} - {track.artist}", 'playlist': playlist_name,
            'elapsed': round(time.time() - t_start, 1)}


def main():
    if '--auto' in sys.argv:
        mode = 'auto'
    elif '--dry-run' in sys.argv:
        mode = 'dry-run'
    elif '--refresh' in sys.argv:
        mode = 'refresh'
    elif '--cache-refresh' in sys.argv:
        mode = 'cache-refresh'
    else:
        mode = 'normal'

    result = run_cache_refresh() if mode == 'cache-refresh' else run_pulse(mode)
    if not result['success']:
        print(f"Error: {result.get('error')}")
        sys.exit(1)


if __name__ == '__main__':
    main()
