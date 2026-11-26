"""Playlist profiles built from the API tracks."""

import pytest

from core.models import PlaylistProfile, Track
from core.playlist_analyzer import SpotifyPlaylistAnalyzer


def item(track_id, artist_id, artist_name, kind="track", field="item"):
    return {field: {"id": track_id, "type": kind,
                    "name": track_id, "artists": [{"id": artist_id, "name": artist_name}]}}


class FakeSp:
    def __init__(self, pages):
        self.pages = pages

    def playlist_items(self, playlist_id, limit, offset):
        return self.pages[offset // limit]


class FakeManager:
    def __init__(self, pages):
        self.sp = FakeSp(pages)


def analyzer(pages):
    return SpotifyPlaylistAnalyzer(FakeManager(pages))


def test_profile_counts_main_artists_and_keeps_track_ids():
    pages = [{"next": None, "items": [
        item("t1", "a", "A"), item("t2", "a", "A"), item("t3", "a", "A"), item("t4", "b", "B"),
    ]}]
    profile, names = analyzer(pages).build_profile("p", "P")

    assert profile.artist_counts == {"a": 3, "b": 1}
    assert profile.track_ids == ["t1", "t2", "t3", "t4"]
    assert names == {"a": "A", "b": "B"}


def test_tf_uses_laplace_smoothing():
    # 3 tracks by artist a, 1 by b: V = 2 distinct artists
    profile = PlaylistProfile(id="p", name="P", artist_counts={"a": 3, "b": 1})
    assert profile.artist_weights["a"] == pytest.approx((3 + 1) / (4 + 2))
    assert profile.artist_weights["b"] == pytest.approx((1 + 1) / (4 + 2))


def test_smoothing_keeps_small_playlists_from_dominating():
    # Without smoothing, 1 of 3 tracks would give 0.33 in a small playlist
    profile = PlaylistProfile(id="p", name="P", artist_counts={"a": 1, "b": 1, "c": 1})
    assert profile.artist_weights["a"] == pytest.approx(2 / 6)


def test_add_track_updates_counts_and_weights():
    profile = PlaylistProfile(id="p", name="P", artist_counts={"a": 3, "b": 1}, track_ids=["t1"])
    profile.add_track(Track(id="t2", name="x", artist_id="c"))

    assert profile.artist_counts == {"a": 3, "b": 1, "c": 1}
    assert profile.artist_weights == PlaylistProfile(id="q", name="Q", artist_counts={"a": 3, "b": 1, "c": 1}).artist_weights
    assert profile.track_ids == ["t1", "t2"]


def test_reads_all_pages_and_skips_episodes():
    pages = [
        {"next": "page2",
         "items": [item(f"t{i}", "a", "A") for i in range(99)] + [item("ep", "x", "X", kind="episode")]},
        {"next": None, "items": [item("t99", "b", "B", field="track")]},
    ]
    tracks = analyzer(pages).fetch_tracks("p")

    assert len(tracks) == 100  # the episode is left out
    assert tracks[-1].artist_id == "b"  # the old "track" field is also accepted
