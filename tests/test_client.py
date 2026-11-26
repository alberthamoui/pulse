"""SpotifyManager: current song and playlist filter, without network."""

from core.client import SpotifyManager


class FakeSp:
    def __init__(self, playlists=None, playing=None):
        self.playlists = playlists or []
        self.playing = playing

    def current_user_playing_track(self):
        return self.playing

    def current_user(self):
        return {"id": "me"}

    def current_user_playlists(self, limit):
        return {"items": self.playlists, "next": None}


def manager(sp):
    # Skips __init__, which would do the OAuth login
    m = SpotifyManager.__new__(SpotifyManager)
    m.sp = sp
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


def playing(is_playing=True, item="song", kind="track"):
    song = {"id": "t1", "name": "Song", "artists": [{"id": "a1", "name": "Artist"}]}
    return {"is_playing": is_playing, "currently_playing_type": kind,
            "item": song if item == "song" else item}


def test_paused_song_is_the_current_song():
    track = manager(FakeSp(playing=playing(is_playing=False))).get_current_track()
    assert (track.id, track.name, track.artist_id) == ("t1", "Song", "a1")


def test_playing_song_is_the_current_song():
    assert manager(FakeSp(playing=playing())).get_current_track().id == "t1"


def test_no_session_podcast_or_ad_is_no_song():
    assert manager(FakeSp(playing=None)).get_current_track() is None
    assert manager(FakeSp(playing=playing(item=None, kind="episode"))).get_current_track() is None
    assert manager(FakeSp(playing=playing(item=None, kind="ad"))).get_current_track() is None
