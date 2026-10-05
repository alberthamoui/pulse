"""SpotifyManager: playlist filter and genres, without network."""

from core.client import SpotifyManager


class FakeSp:
    def __init__(self, playlists=None, artists_error=None):
        self.playlists = playlists or []
        self.artists_error = artists_error

    def current_user(self):
        return {"id": "me"}

    def current_user_playlists(self, limit):
        return {"items": self.playlists, "next": None}

    def _get(self, path, **params):
        raise self.artists_error


def manager(sp, genres_available=True):
    # Skips __init__, which would do the OAuth login
    m = SpotifyManager.__new__(SpotifyManager)
    m.sp = sp
    m._genres_available = genres_available
    return m


def playlist(pl_id, owner, collaborative=False):
    return {"id": pl_id, "name": pl_id, "snapshot_id": "s",
            "owner": {"id": owner}, "collaborative": collaborative}


def test_playlists_include_own_and_collaborative_only():
    sp = FakeSp([
        playlist("mine", "me"),
        playlist("collab", "friend", collaborative=True),
        playlist("followed", "friend"),
    ])
    assert [p["id"] for p in manager(sp).get_user_playlists()] == ["mine", "collab"]


def test_genre_failure_does_not_break_matching():
    sp = FakeSp(artists_error=RuntimeError("429 Too Many Requests"))
    assert manager(sp).get_artists_genres(["a", "b"]) == {"a": [], "b": []}
