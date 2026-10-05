"""Playlist profiles: tf with Laplace smoothing from the API tracks."""

import pytest

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


def test_tf_uses_laplace_smoothing():
    # 3 tracks by artist a, 1 by b: V = 2 distinct artists
    pages = [{"total": 4, "next": None, "items": [
        item("t1", "a", "A"), item("t2", "a", "A"), item("t3", "a", "A"), item("t4", "b", "B"),
    ]}]
    weights, total, track_ids, names, counts = SpotifyPlaylistAnalyzer(
        FakeManager(pages)
    ).build_artist_profile("p")

    assert weights["a"] == pytest.approx((3 + 1) / (4 + 2))
    assert weights["b"] == pytest.approx((1 + 1) / (4 + 2))
    assert total == 4
    assert track_ids == ["t1", "t2", "t3", "t4"]
    assert names == {"a": "A", "b": "B"}
    assert counts == {"a": 3, "b": 1}


def test_smoothing_keeps_small_playlists_from_dominating():
    # Without smoothing, 1 of 3 tracks would give 0.33 in a small playlist
    pages = [{"total": 3, "next": None, "items": [
        item("t1", "a", "A"), item("t2", "b", "B"), item("t3", "c", "C"),
    ]}]
    weights, *_ = SpotifyPlaylistAnalyzer(FakeManager(pages)).build_artist_profile("p")
    assert weights["a"] == pytest.approx(2 / 6)


def test_reads_all_pages_and_skips_episodes():
    pages = [
        {"total": 101, "next": "page2",
         "items": [item(f"t{i}", "a", "A") for i in range(99)] + [item("ep", "x", "X", kind="episode")]},
        {"total": 101, "next": None, "items": [item("t99", "b", "B", field="track")]},
    ]
    tracks, total = SpotifyPlaylistAnalyzer(FakeManager(pages)).fetch_tracks("p")

    assert total == 101
    assert len(tracks) == 100  # the episode is left out
    assert tracks[-1].artist_id == "b"  # the old "track" field is also accepted
