"""
PULSE - Takes the song playing on Spotify and adds it to the playlist it fits best.
If there's no match, it goes to the fallback playlist (FALLBACK_PULSE).

Usage:
    python main.py                 # uses the cache if available
    python main.py --auto          # automatic mode (no prompts)
    python main.py --dry-run       # runs the matching but doesn't add to the playlist
    python main.py --refresh       # forces the playlists to be analyzed again
    python main.py --cache-refresh # rebuilds the cache without checking the current song

"""

import sys
from pathlib import Path
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT))
import json
import os
import re
import tempfile
import time
from datetime import datetime, timezone
import spotipy
from core import SpotifyManager, SpotifyPlaylistAnalyzer, ArtistFrequencyMatcher, HybridMatcher
from core.models import PlaylistProfile
from core.playlist_analyzer import smoothed_weights

try:
    import config.settings as settings
except ModuleNotFoundError as e:
    if e.name != 'config.settings':
        raise
    sys.exit("config/settings.py not found. Copy config/settings.example.py to config/settings.py "
             "and fill in your Spotify app credentials (see Setup in the README).")

# getattr: an older settings.py without one of the optional keys still works
SPOTIFY_CLIENT_ID     = getattr(settings, 'SPOTIFY_CLIENT_ID', '')
SPOTIFY_CLIENT_SECRET = getattr(settings, 'SPOTIFY_CLIENT_SECRET', '')
SPOTIFY_REDIRECT_URI  = getattr(settings, 'SPOTIFY_REDIRECT_URI', 'http://127.0.0.1:8080')
LASTFM_API_KEY        = getattr(settings, 'LASTFM_API_KEY', '')

DEFAULT_AUTO_ADD_MIN_SCORE = 0.5  # used if 'auto_add_min_score' isn't in config.json
DEFAULT_ALGORITHM = 'hybrid'
CACHE_VERSION = 3  # 3: profile keys renamed to English (name, artist_weights)
PLACEHOLDER_CREDENTIALS = {'', 'your_client_id', 'your_client_secret'}  # as in settings.example.py


def check_credentials() -> str | None:
    """Returns an error message if the Spotify credentials in settings.py aren't filled in."""
    if {str(SPOTIFY_CLIENT_ID).strip(), str(SPOTIFY_CLIENT_SECRET).strip()} & PLACEHOLDER_CREDENTIALS:
        return ("SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET in config/settings.py aren't filled in. "
                "Copy them from your app at https://developer.spotify.com/dashboard")
    return None


def parse_playlist_id(value) -> str | None:
    """
    Accepts a playlist ID, its link (https://open.spotify.com/playlist/<id>?si=...)
    or its URI (spotify:playlist:<id>). Returns the ID, or None if it isn't one.
    """
    value = str(value or '').strip()
    match = (re.fullmatch(r'([A-Za-z0-9]{22})', value)
             or re.search(r'playlist[/:]([A-Za-z0-9]{22})(?![A-Za-z0-9])', value))
    return match.group(1) if match else None


def load_config() -> dict:
    config_path = ROOT / 'config' / 'config.json'
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        raise RuntimeError(f"config.json not found at {config_path}")
    except json.JSONDecodeError:
        raise RuntimeError("config.json is invalid")


def load_cache(cache_path: Path, algorithm: str) -> dict | None:
    """Returns the whole cache if it exists and the algorithm matches."""
    if not cache_path.exists():
        return None
    try:
        with open(cache_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if data.get('algorithm') != algorithm:
            print("Cache invalid: built with a different algorithm.")
            return None
        if data.get('version') != CACHE_VERSION:
            print("Cache in an old format: rebuilding the profiles.")
            return None
        return data
    except Exception as e:
        print(f"Error reading the cache: {e}")
        return None


def save_cache(cache_path: Path, algorithm: str, profiles_data: dict, snapshots: dict, artist_names: dict = None) -> None:
    """Saves the profiles, snapshot_ids and artist names to the cache."""
    try:
        data = {
            'version': CACHE_VERSION,
            'algorithm': algorithm,
            'cached_at': datetime.now(timezone.utc).isoformat(),
            'snapshots': snapshots,
            'artist_names': artist_names or {},
            'profiles': profiles_data,
        }
        # Write to a temp file and swap: an interruption halfway doesn't corrupt the cache
        fd, tmp = tempfile.mkstemp(dir=cache_path.parent, prefix=cache_path.name, suffix='.tmp')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, cache_path)
        except BaseException:
            os.unlink(tmp)
            raise
        print(f"Cache saved to {cache_path}")
    except Exception as e:
        print(f"Warning: could not save the cache: {e}")


def update_cache(profiles_data: dict, snapshots: dict, playlist_id: str, new_snapshot: str, track) -> None:
    """Updates the cache locally after adding a song, with no extra API calls."""
    profile = profiles_data[playlist_id]
    profile.setdefault('track_ids', []).append(track.id)
    profile['total_tracks'] = profile.get('total_tracks', 0) + 1
    snapshots[playlist_id] = new_snapshot

    if track.artist_id:
        counts = profile.setdefault('artist_counts', {})
        counts[track.artist_id] = counts.get(track.artist_id, 0) + 1
        profile['artist_weights'] = smoothed_weights(counts)


def build_profiles_for(spotify: SpotifyManager, playlists: list, matcher_type: str) -> tuple[dict, dict]:
    """
    Builds the profiles for the given playlists.
    Returns (profiles_data, artist_names).
    """
    if not playlists:
        return {}, {}

    analyzer = SpotifyPlaylistAnalyzer(spotify)

    if matcher_type in ('artist_frequency', 'hybrid'):
        profiles, artist_names = analyzer.build_all_profiles(playlists)
        profiles_data = {
            pl_id: {
                'id': p.id,
                'name': p.name,
                'artist_weights': p.artist_weights,
                'genre_weights': p.genre_weights,
                'total_tracks': p.total_tracks,
                'track_ids': p.track_ids,
                'artist_counts': p.artist_counts,
            }
            for pl_id, p in profiles.items()
        }
        return profiles_data, artist_names

    raise RuntimeError(f"Unknown algorithm: '{matcher_type}'")


def sync_profiles(spotify: SpotifyManager, all_playlists: list, cached_data: dict | None,
                    matcher_type: str) -> tuple[dict, dict, dict]:
    """
    Updates only the playlists whose snapshot_id changed since the last cache.
    Returns (profiles_data, snapshots, artist_names).

    Only the playlists that were actually read get their new snapshot_id. One that
    failed keeps its old snapshot (or none), so the next run reads it again.
    """
    playlists = [p for p in all_playlists if p['id']]
    current_snapshots = {p['id']: p['snapshot_id'] for p in playlists}

    if cached_data is None:
        print(f"No cache. Analyzing {len(playlists)} playlists...")
        profiles, artist_names = build_profiles_for(spotify, playlists, matcher_type)
        warn_unread(len(playlists) - len(profiles))
        snapshots = {pid: current_snapshots[pid] for pid in profiles}
        return profiles, snapshots, artist_names

    cached_snapshots = cached_data.get('snapshots', {})
    cached_profiles  = cached_data.get('profiles', {})
    cached_names     = cached_data.get('artist_names', {})

    # A playlist with a snapshot but no profile failed to load before: read it again too
    changed = [p for p in playlists
               if current_snapshots[p['id']] != cached_snapshots.get(p['id'])
               or p['id'] not in cached_profiles]
    removed = [pid for pid in cached_profiles if pid not in current_snapshots]

    if not changed and not removed:
        cached_at = datetime.fromisoformat(cached_data['cached_at'])
        age_hours = (datetime.now(timezone.utc) - cached_at).total_seconds() / 3600
        print(f"Cache is valid ({age_hours:.1f}h old). No playlist changed.")
        return cached_profiles, current_snapshots, cached_names

    print(f"{len(changed)} playlist(s) changed, {len(removed)} removed. Updating...")
    for p in changed:
        print(f"  ~ {p['name']}")
    new_profiles, new_names = build_profiles_for(spotify, changed, matcher_type)

    merged = {pid: prof for pid, prof in cached_profiles.items() if pid not in removed}
    merged.update(new_profiles)
    merged_names = {**cached_names, **new_names}

    failed = {p['id'] for p in changed} - new_profiles.keys()
    warn_unread(len(failed))
    snapshots = {pid: snap for pid, snap in current_snapshots.items() if pid not in failed}
    snapshots.update({pid: cached_snapshots[pid] for pid in failed if pid in cached_snapshots})
    return merged, snapshots, merged_names


def warn_unread(count: int) -> None:
    if count:
        print(f"{count} playlist(s) couldn't be read; they'll be retried next run.")


def train_matcher(matcher_type: str, profiles_data: dict, spotify=None, artist_names: dict = None):
    """Creates and trains the matcher with the profile data."""
    if matcher_type == 'artist_frequency':
        profiles = {
            pl_id: PlaylistProfile(
                id=d['id'],
                name=d['name'],
                artist_weights=d['artist_weights'],
                total_tracks=d.get('total_tracks', 0),
            )
            for pl_id, d in profiles_data.items()
        }
        matcher = ArtistFrequencyMatcher()
        matcher.train(profiles)
        return matcher

    elif matcher_type == 'hybrid':
        profiles = {
            pl_id: PlaylistProfile(
                id=d['id'],
                name=d['name'],
                artist_weights=d['artist_weights'],
                genre_weights=d.get('genre_weights', {}),
                total_tracks=d.get('total_tracks', 0),
            )
            for pl_id, d in profiles_data.items()
        }
        matcher = HybridMatcher(spotify)
        matcher.train(profiles, artist_names=artist_names)
        return matcher

    raise RuntimeError(f"Unknown algorithm: '{matcher_type}'")


def prompt_playlist_choice(
    candidates: list,
    fallback_id: str,
    profiles_data: dict,
    spotify,
    track,
) -> tuple[str, str] | None:
    """
    Shows the playlist menu and returns (playlist_id, playlist_name).
    Returns None if the user cancels.
    """
    options = candidates
    track_in_liked    = spotify.is_track_liked(track.id)
    track_in_fallback = track.id in profiles_data.get(fallback_id, {}).get('track_ids', [])

    liked_label    = "Liked Songs (already there)"     if track_in_liked    else "Liked Songs"
    fallback_label = "FALLBACK_PULSE (already there)"  if track_in_fallback else "FALLBACK_PULSE"

    print()
    if options:
        print("Where should it go?")
    else:
        print("No matching playlist found. Pick one manually:")
    for i, r in enumerate(options, 1):
        reason = f" ({r.reason})" if r.reason else ""
        marker = " (recommended)" if i == 1 else ""
        print(f"  [{i}] {r.playlist_name}: {r.score:.2%}{reason}{marker}")
    print(f"  [l] {liked_label}")
    print(f"  [f] {fallback_label}")
    print("  [n] Don't add")
    print()

    valid_range = '/'.join(str(i) for i in range(1, len(options) + 1)) + '/l/f/n'
    default = '1' if options else 'f'  # with no suggestion, Enter goes to the fallback
    while True:
        raw    = input(f"Choose [{valid_range.lstrip('/')}] (Enter = {default}): ").strip()
        choice = raw if raw else default

        if choice == 'l':
            return "liked", "Liked Songs"
        elif choice == 'f':
            return fallback_id, "FALLBACK_PULSE"
        elif choice == 'n':
            return None
        elif choice.isdigit() and 1 <= int(choice) <= len(options):
            r = options[int(choice) - 1]
            return r.playlist_id, r.playlist_name
        else:
            print("  Invalid option, try again.")


def run_cache_refresh() -> dict:
    """Rebuilds the playlist cache without checking the current song."""
    t_start = time.time()

    try:
        config = load_config()
    except RuntimeError as e:
        return {'success': False, 'error': str(e)}

    matcher_type = config.get('algorithm', DEFAULT_ALGORITHM)
    cache_file   = config.get('cache_file', '.pulse_cache.json')
    cache_path   = ROOT / cache_file

    credentials_error = check_credentials()
    if credentials_error:
        return {'success': False, 'error': credentials_error}

    print("Connecting to Spotify...")
    spotify = SpotifyManager(
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET,
        redirect_uri=SPOTIFY_REDIRECT_URI
    )

    print("Fetching playlists...")
    all_playlists = spotify.get_user_playlists()

    profiles_data, snapshots, artist_names = sync_profiles(
        spotify, all_playlists, None, matcher_type  # None forces a full rebuild
    )

    if profiles_data:
        save_cache(cache_path, matcher_type, profiles_data, snapshots, artist_names)
        elapsed = round(time.time() - t_start, 1)
        print(f"Cache updated: {len(profiles_data)} playlists [{elapsed}s | {spotify.api_calls} API calls]")
        return {'success': True, 'playlists': len(profiles_data), 'elapsed': elapsed}

    return {'success': False, 'error': 'No profile was built'}


def run_pulse(mode: str = 'normal') -> dict:
    """
    Runs the whole Pulse cycle.

    Returns:
        {'success': True,  'track': '...', 'playlist': '...', 'elapsed': 1.2}
        {'success': False, 'error': 'message'}
    """
    t_start = time.time()

    try:
        config = load_config()
    except RuntimeError as e:
        return {'success': False, 'error': str(e)}

    matcher_type = config.get('algorithm', DEFAULT_ALGORITHM)
    fallback_id  = parse_playlist_id(config.get('fallback_playlist_id'))
    cache_file   = config.get('cache_file', '.pulse_cache.json')
    cache_path   = ROOT / cache_file

    if not fallback_id:
        return {'success': False, 'error': "'fallback_playlist_id' in config/config.json doesn't look like "
                                           "a Spotify playlist. Paste the playlist link there "
                                           "(Share > Copy link to playlist)."}

    credentials_error = check_credentials()
    if credentials_error:
        return {'success': False, 'error': credentials_error}

    print("Connecting to Spotify...")
    spotify = SpotifyManager(
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET,
        redirect_uri=SPOTIFY_REDIRECT_URI
    )

    try:
        track = spotify.get_current_track()
    except (spotipy.exceptions.SpotifyException, ConnectionError, TimeoutError) as e:
        # A Spotify app in development mode only lets in the accounts registered on it
        if getattr(e, 'http_status', None) == 403:
            return {'success': False, 'error': "Spotify refused access (403). If this account doesn't own "
                                               "the Spotify app, add it under User Management in the "
                                               "developer dashboard (see Troubleshooting in the README)."}
        return {'success': False, 'error': f'Spotify/connection error: {e}'}

    if not track:
        print("Nothing is playing right now.")
        elapsed = round(time.time() - t_start, 1)
        print(f"[{elapsed}s | {spotify.api_calls} API calls]")
        return {'success': False, 'error': 'Nothing playing'}

    print(f"Current song: {track.name} - {track.artist}")

    if not track.id:
        return {'success': False, 'error': "Local file: not in the Spotify catalog, it can't be added"}

    print("Checking playlists...")
    all_playlists = spotify.get_user_playlists()

    cached_data   = None if (mode == 'refresh') else load_cache(cache_path, matcher_type)
    profiles_data, snapshots, artist_names = sync_profiles(
        spotify, all_playlists, cached_data, matcher_type
    )

    if profiles_data:
        save_cache(cache_path, matcher_type, profiles_data, snapshots, artist_names)

    playlist_id   = None
    playlist_name = None
    candidates    = []
    result        = None

    if profiles_data:
        matcher = train_matcher(matcher_type, profiles_data, spotify, artist_names=artist_names)

        if matcher_type == 'hybrid':
            candidates = matcher.top_matches(track, n=3)
            if not candidates and LASTFM_API_KEY:
                print("No direct match. Trying Last.fm...")
                candidates = matcher.lastfm_fallback(track, LASTFM_API_KEY)
                if candidates:
                    print("Match found through Last.fm.")
        else:
            best = matcher.match(track)
            candidates = [best] if best else []

        result = candidates[0] if candidates else None

        if result:
            playlist_id   = result.playlist_id
            playlist_name = result.playlist_name

    # Duplicate warning
    track_to_playlists: dict = {}
    for pd in profiles_data.values():
        for tid in pd.get('track_ids', []):
            track_to_playlists.setdefault(tid, []).append(pd['name'])

    already_in = track_to_playlists.get(track.id, [])
    if already_in:
        print(f"\nWarning: this song is already in: {', '.join(already_in)}")
        if mode == 'auto':
            elapsed = round(time.time() - t_start, 1)
            print(f"Automatic mode: not adding a duplicate. [{elapsed}s | {spotify.api_calls} API calls]")
            return {'success': False, 'error': 'Song is already in a playlist'}
    if already_in and mode != 'dry-run':
        raw = input("Continue anyway? [y/n] (Enter = n): ").strip().lower()
        if raw != 'y':
            elapsed = round(time.time() - t_start, 1)
            print(f"Cancelled. [{elapsed}s | {spotify.api_calls} API calls]")
            return {'success': False, 'error': 'Cancelled - song already in a playlist'}
        print()

    if mode == 'auto':
        # Automatic confirmation: only adds if the best match passes the minimum score
        min_score = config.get('auto_add_min_score', DEFAULT_AUTO_ADD_MIN_SCORE)
        elapsed   = round(time.time() - t_start, 1)
        if not result:
            print(f"No candidates for auto-add. [{elapsed}s | {spotify.api_calls} API calls]")
            return {'success': False, 'error': 'No candidates for auto-add'}
        if result.score < min_score:
            print(f"Low score ({result.score:.2%} < {min_score:.2%}). Not adding automatically. "
                  f"[{elapsed}s | {spotify.api_calls} API calls]")
            return {'success': False, 'error': 'Score below the auto-add minimum'}

    if mode == 'dry-run':
        # Won't add anything, just shows the candidates and exits
        if candidates:
            for r in candidates:
                print(f"  {r.playlist_name}: {r.score:.2%} ({r.reason})")
        elif not result:
            print("No candidate found.")

        elapsed = round(time.time() - t_start, 1)
        print(f"\nWould be added to: {playlist_name or 'FALLBACK_PULSE'} [{elapsed}s | {spotify.api_calls} API calls]\n")
        return {
            'success':  True,
            'track':    f"{track.name} - {track.artist}",
            'playlist': playlist_name or 'FALLBACK_PULSE',
            'elapsed':  elapsed,
        }

    # Interactive confirmation: only --auto adds without asking
    if mode != 'auto':
        choice = prompt_playlist_choice(candidates, fallback_id, profiles_data, spotify, track)
        if choice is None:
            elapsed = round(time.time() - t_start, 1)
            print(f"Cancelled. [{elapsed}s | {spotify.api_calls} API calls]")
            return {'success': False, 'error': 'Cancelled by user'}
        playlist_id, playlist_name = choice
        print()

    if not playlist_id:
        playlist_id   = fallback_id
        playlist_name = "FALLBACK_PULSE"
        print("No match. Using FALLBACK_PULSE.")

    new_snapshot = spotify.add_track_to_playlist(playlist_id, track.id)
    if new_snapshot is None:
        return {'success': False, 'error': 'Failed to add to the playlist'}

    if playlist_id in profiles_data and new_snapshot:
        update_cache(profiles_data, snapshots, playlist_id, new_snapshot, track)
        save_cache(cache_path, matcher_type, profiles_data, snapshots, artist_names)

    elapsed = round(time.time() - t_start, 1)
    print(f"Added to: {playlist_name}")
    print(f"[{elapsed}s | {spotify.api_calls} API calls]")

    return {
        'success':  True,
        'track':    f"{track.name} - {track.artist}",
        'playlist': playlist_name,
        'elapsed':  elapsed,
    }


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

    if mode == 'cache-refresh':
        result = run_cache_refresh()
        if not result['success']:
            print(f"Error: {result.get('error')}")
            sys.exit(1)
        return

    result = run_pulse(mode)
    if not result['success']:
        print(f"Error: {result.get('error')}")
        sys.exit(1)


if __name__ == '__main__':
    main()
