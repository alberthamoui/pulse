"""
The user's own configuration: the credentials in config/settings.py and the options
in config/config.json. Both stay out of git; the .example files are the templates.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = ROOT / 'config' / 'config.json'

PLACEHOLDER_CREDENTIALS = {'', 'your_client_id', 'your_client_secret'}  # as in settings.example.py
DEFAULT_AUTO_ADD_MIN_SCORE = 0.5
DEFAULT_CACHE_FILE = '.pulse_cache.json'

INVALID_FALLBACK = ("'fallback_playlist_id' in config/config.json doesn't look like a Spotify playlist. "
                    "Paste the playlist link there (Share > Copy link to playlist).")


class SetupError(Exception):
    """Something in the user's configuration that they have to fix."""


@dataclass
class Settings:
    """config/settings.py"""
    client_id: str
    client_secret: str
    redirect_uri: str
    lastfm_api_key: str  # empty turns the Last.fm fallback off


@dataclass
class Config:
    """config/config.json"""
    fallback_playlist_id: Optional[str]  # None if the value isn't a playlist
    cache_path: Path
    auto_add_min_score: float


def load_settings() -> Settings:
    """Reads config/settings.py; raises SetupError if it's missing or not filled in."""
    try:
        import config.settings as settings
    except ModuleNotFoundError as e:
        if e.name != 'config.settings':
            raise
        raise SetupError("config/settings.py not found. Copy config/settings.example.py to "
                         "config/settings.py and fill in your Spotify app credentials "
                         "(see Setup in the README).")

    # getattr: an older settings.py without one of the optional keys still works
    loaded = Settings(
        client_id=str(getattr(settings, 'SPOTIFY_CLIENT_ID', '')).strip(),
        client_secret=str(getattr(settings, 'SPOTIFY_CLIENT_SECRET', '')).strip(),
        redirect_uri=getattr(settings, 'SPOTIFY_REDIRECT_URI', 'http://127.0.0.1:8080'),
        lastfm_api_key=getattr(settings, 'LASTFM_API_KEY', ''),
    )
    if {loaded.client_id, loaded.client_secret} & PLACEHOLDER_CREDENTIALS:
        raise SetupError("SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET in config/settings.py aren't "
                         "filled in. Copy them from your app at https://developer.spotify.com/dashboard")
    return loaded


def load_config(path: Path = CONFIG_PATH) -> Config:
    """Reads config/config.json; raises SetupError if it's missing or invalid."""
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        raise SetupError("config/config.json not found. Copy config/config.example.json to config/config.json.")
    except json.JSONDecodeError as e:
        raise SetupError(f"config/config.json is invalid: {e}")

    return Config(
        fallback_playlist_id=parse_playlist_id(data.get('fallback_playlist_id')),
        cache_path=ROOT / data.get('cache_file', DEFAULT_CACHE_FILE),
        auto_add_min_score=data.get('auto_add_min_score', DEFAULT_AUTO_ADD_MIN_SCORE),
    )


def parse_playlist_id(value) -> Optional[str]:
    """
    Accepts a playlist ID, its link (https://open.spotify.com/playlist/<id>?si=...)
    or its URI (spotify:playlist:<id>). Returns the ID, or None if it isn't one.
    """
    value = str(value or '').strip()
    match = (re.fullmatch(r'([A-Za-z0-9]{22})', value)
             or re.search(r'playlist[/:]([A-Za-z0-9]{22})(?![A-Za-z0-9])', value))
    return match.group(1) if match else None
