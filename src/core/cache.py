"""
Local cache of the playlist profiles (.pulse_cache.json). Reading every playlist takes
about 100 API calls, so a run only re-reads the ones whose snapshot_id changed.
"""

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .models import PlaylistProfile, Track
from .playlist_analyzer import SpotifyPlaylistAnalyzer

CACHE_VERSION = 4  # 4: no genres, weights derived from artist_counts


@dataclass
class Cache:
    profiles: Dict[str, PlaylistProfile]  # playlist_id -> profile
    snapshots: Dict[str, str]             # playlist_id -> snapshot_id the profile was built from
    artist_names: Dict[str, str]          # artist_id -> name, to match Last.fm results
    cached_at: Optional[datetime] = None

    def record_add(self, playlist_id: str, track: Track, new_snapshot: str) -> None:
        """Updates the cache after adding a song, with no extra API call."""
        self.profiles[playlist_id].add_track(track)
        self.snapshots[playlist_id] = new_snapshot


def load_cache(path: Path) -> Optional[Cache]:
    """The saved cache, or None if there's none or it's in an old format."""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        if data.get('version') != CACHE_VERSION:
            print("Cache in an old format: rebuilding the profiles.")
            return None
        return Cache(
            profiles={pid: PlaylistProfile(**p) for pid, p in data['profiles'].items()},
            snapshots=data['snapshots'],
            artist_names=data['artist_names'],
            cached_at=datetime.fromisoformat(data['cached_at']),
        )
    except Exception as e:
        print(f"Error reading the cache: {e}")
        return None


def save_cache(path: Path, cache: Cache) -> None:
    data = {
        'version': CACHE_VERSION,
        'cached_at': datetime.now(timezone.utc).isoformat(),
        'snapshots': cache.snapshots,
        'artist_names': cache.artist_names,
        'profiles': {pid: p.to_dict() for pid, p in cache.profiles.items()},
    }
    try:
        # Write to a temp file and swap: an interruption halfway doesn't corrupt the cache
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix='.tmp')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        except BaseException:
            os.unlink(tmp)
            raise
    except Exception as e:
        print(f"Warning: could not save the cache: {e}")


def build_profiles(spotify, playlists: List[Dict]) -> Tuple[Dict[str, PlaylistProfile], Dict[str, str]]:
    if not playlists:
        return {}, {}
    return SpotifyPlaylistAnalyzer(spotify).build_all_profiles(playlists)


def sync_profiles(spotify, all_playlists: List[Dict], cached: Optional[Cache]) -> Cache:
    """
    Brings the cache up to date with the playlists on Spotify, reading only the ones
    whose snapshot_id changed (all of them without a cache).

    Only the playlists that were actually read get their new snapshot_id. One that
    failed keeps its old snapshot (or none), so the next run reads it again.
    """
    playlists = [p for p in all_playlists if p['id']]
    current_snapshots = {p['id']: p['snapshot_id'] for p in playlists}

    if cached is None:
        print(f"No cache. Analyzing {len(playlists)} playlists...")
        profiles, artist_names = build_profiles(spotify, playlists)
        warn_unread(len(playlists) - len(profiles))
        return Cache(profiles, {pid: current_snapshots[pid] for pid in profiles}, artist_names)

    # A playlist with a snapshot but no profile failed to load before: read it again too
    changed = [p for p in playlists
               if current_snapshots[p['id']] != cached.snapshots.get(p['id'])
               or p['id'] not in cached.profiles]
    removed = [pid for pid in cached.profiles if pid not in current_snapshots]

    if not changed and not removed:
        age_hours = (datetime.now(timezone.utc) - cached.cached_at).total_seconds() / 3600
        print(f"Cache is valid ({age_hours:.1f}h old). No playlist changed.")
        return Cache(cached.profiles, current_snapshots, cached.artist_names)

    print(f"{len(changed)} playlist(s) changed, {len(removed)} removed. Updating...")
    for p in changed:
        print(f"  ~ {p['name']}")
    new_profiles, new_names = build_profiles(spotify, changed)

    profiles = {pid: prof for pid, prof in cached.profiles.items() if pid not in removed}
    profiles.update(new_profiles)

    failed = {p['id'] for p in changed} - new_profiles.keys()
    warn_unread(len(failed))
    snapshots = {pid: snap for pid, snap in current_snapshots.items() if pid not in failed}
    snapshots.update({pid: cached.snapshots[pid] for pid in failed if pid in cached.snapshots})
    return Cache(profiles, snapshots, {**cached.artist_names, **new_names})


def warn_unread(count: int) -> None:
    if count:
        print(f"{count} playlist(s) couldn't be read; they'll be retried next run.")
