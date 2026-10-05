import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

# config/settings.py holds the credentials and stays out of git: the tests use a
# fake one, even on machines that have the file, so they don't depend on it
_settings = types.ModuleType("config.settings")
_settings.SPOTIFY_CLIENT_ID = "test-client-id"
_settings.SPOTIFY_CLIENT_SECRET = "test-client-secret"
_settings.SPOTIFY_REDIRECT_URI = "http://127.0.0.1:8080"
_settings.LASTFM_API_KEY = ""
sys.modules["config.settings"] = _settings

from core.models import PlaylistProfile  # noqa: E402


class FakeSpotify:
    """Stands in for SpotifyManager: no genres, as for apps without extended access."""

    def get_artists_genres(self, artist_ids):
        return {}


@pytest.fixture
def spotify():
    return FakeSpotify()


def profile(pl_id, weights):
    return PlaylistProfile(id=pl_id, name=pl_id, artist_weights=weights)
