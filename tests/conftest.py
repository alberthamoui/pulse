import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

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
