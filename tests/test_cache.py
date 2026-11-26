"""Profile cache: save/load, update after adding and sync with the playlists on Spotify."""

import json
from datetime import datetime, timezone

import core.cache as cache_module
from core.cache import CACHE_VERSION, Cache, load_cache, save_cache, sync_profiles
from core.models import PlaylistProfile, Track


def cache_with(snapshots, profiles):
    return Cache(profiles, snapshots, {}, cached_at=datetime(2026, 10, 4, tzinfo=timezone.utc))


def old(pl_id):
    return PlaylistProfile(id=pl_id, name="old")


def fake_build(monkeypatch, readable):
    """build_profiles that only reads the playlists in readable, like a 429 on the rest."""
    calls = []

    def build(spotify, playlists):
        calls.append([p["id"] for p in playlists])
        return {p["id"]: PlaylistProfile(id=p["id"], name="new") for p in playlists if p["id"] in readable}, {}

    monkeypatch.setattr(cache_module, "build_profiles", build)
    return calls


def test_save_and_load_round_trip_leaves_no_temp_files(tmp_path):
    path = tmp_path / "cache.json"
    profile = PlaylistProfile(id="p1", name="P1", artist_counts={"a": 3, "b": 1}, track_ids=["t1"])
    save_cache(path, Cache({"p1": profile}, {"p1": "s1"}, {"a": "A"}))

    loaded = load_cache(path)
    assert loaded.profiles == {"p1": profile}
    assert loaded.profiles["p1"].artist_weights == profile.artist_weights
    assert (loaded.snapshots, loaded.artist_names) == ({"p1": "s1"}, {"a": "A"})
    assert [p.name for p in tmp_path.iterdir()] == ["cache.json"]


def test_cache_from_an_older_version_is_rebuilt(tmp_path):
    path = tmp_path / "cache.json"
    path.write_text(json.dumps({"version": CACHE_VERSION - 1, "profiles": {}}), encoding="utf-8")
    assert load_cache(path) is None


def test_record_add_updates_the_profile_and_snapshot():
    cache = cache_with({"p1": "s1"}, {"p1": PlaylistProfile(id="p1", name="P1", artist_counts={"a": 1})})
    cache.record_add("p1", Track(id="t9", name="x", artist_id="a"), "s2")

    assert cache.profiles["p1"].artist_counts == {"a": 2}
    assert cache.profiles["p1"].track_ids == ["t9"]
    assert cache.snapshots["p1"] == "s2"


def test_changed_playlist_that_fails_keeps_old_snapshot_and_is_retried(monkeypatch):
    playlists = [{"id": "a", "name": "A", "snapshot_id": "s2"}, {"id": "b", "name": "B", "snapshot_id": "s1"}]
    calls = fake_build(monkeypatch, readable=set())

    synced = sync_profiles(None, playlists, cache_with({"a": "s1", "b": "s1"}, {"a": old("a"), "b": old("b")}))

    assert synced.profiles["a"].name == "old"
    assert synced.snapshots == {"a": "s1", "b": "s1"}

    sync_profiles(None, playlists, cache_with(synced.snapshots, synced.profiles))
    assert calls == [["a"], ["a"]]


def test_new_playlist_that_fails_has_no_snapshot(monkeypatch):
    playlists = [{"id": "a", "name": "A", "snapshot_id": "s1"}, {"id": "b", "name": "B", "snapshot_id": "s1"}]
    fake_build(monkeypatch, readable={"a"})

    synced = sync_profiles(None, playlists, None)

    assert set(synced.profiles) == {"a"}
    assert synced.snapshots == {"a": "s1"}


def test_playlist_read_successfully_gets_new_snapshot(monkeypatch):
    playlists = [{"id": "a", "name": "A", "snapshot_id": "s2"}]
    fake_build(monkeypatch, readable={"a"})

    synced = sync_profiles(None, playlists, cache_with({"a": "s1"}, {"a": old("a")}))

    assert synced.profiles["a"].name == "new"
    assert synced.snapshots == {"a": "s2"}


def test_snapshot_without_profile_is_read_again(monkeypatch):
    playlists = [{"id": "a", "name": "A", "snapshot_id": "s1"}]
    calls = fake_build(monkeypatch, readable={"a"})

    synced = sync_profiles(None, playlists, cache_with({"a": "s1"}, {}))

    assert calls == [["a"]]
    assert "a" in synced.profiles


def test_removed_playlist_leaves_the_cache(monkeypatch):
    fake_build(monkeypatch, readable=set())
    playlists = [{"id": "a", "name": "A", "snapshot_id": "s1"}]

    synced = sync_profiles(None, playlists, cache_with({"a": "s1", "gone": "s1"}, {"a": old("a"), "gone": old("gone")}))

    assert set(synced.profiles) == {"a"}
    assert synced.snapshots == {"a": "s1"}


def test_unchanged_playlists_are_not_read(monkeypatch):
    calls = fake_build(monkeypatch, readable={"a"})
    synced = sync_profiles(None, [{"id": "a", "name": "A", "snapshot_id": "s1"}],
                           cache_with({"a": "s1"}, {"a": old("a")}))

    assert calls == []
    assert synced.profiles["a"].name == "old"
