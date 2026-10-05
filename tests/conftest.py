import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

# config/settings.py tem as credenciais e fica fora do git: os testes usam um
# falso, também na máquina de quem tem o arquivo, para não depender dele
_settings = types.ModuleType("config.settings")
_settings.SPOTIFY_CLIENT_ID = "test-client-id"
_settings.SPOTIFY_CLIENT_SECRET = "test-client-secret"
_settings.SPOTIFY_REDIRECT_URI = "http://127.0.0.1:8080"
_settings.LASTFM_API_KEY = ""
sys.modules["config.settings"] = _settings

from core.models import PlaylistProfile  # noqa: E402


class FakeSpotify:
    """Substitui o SpotifyManager: sem gêneros, como para apps sem acesso estendido."""

    def get_artists_genres(self, artist_ids):
        return {}


@pytest.fixture
def spotify():
    return FakeSpotify()


def profile(pl_id, weights):
    return PlaylistProfile(id=pl_id, nome=pl_id, artista_weights=weights)
