"""main.py flow: confirmation before adding, cache and edge cases."""

import json

import pytest
import spotipy

import main
from core.models import Track
from core.playlist_analyzer import smoothed_weights

FALLBACK = "37i9dQZF1DXcBWIGoYBM5M"
PLAYLISTS = [{"id": "p1", "name": "P1", "snapshot_id": "s1"}]
PROFILES = {
    "p1": {
        "id": "p1",
        "name": "P1",
        "artist_weights": smoothed_weights({"a": 3, "b": 1}),
        "genre_weights": {},
        "total_tracks": 4,
        "track_ids": ["t1", "t2", "t3", "t4"],
        "artist_counts": {"a": 3, "b": 1},
    }
}


class FakeSpotifyManager:
    instances = []

    def __init__(self, **kwargs):
        self.api_calls = 0
        self.added = []
        self.track = Track(id="new", name="Song", artist="A", artist_id="a")
        FakeSpotifyManager.instances.append(self)

    def get_current_track(self):
        return self.track

    def get_user_playlists(self):
        return PLAYLISTS

    def is_track_liked(self, track_id):
        return False

    def get_artists_genres(self, artist_ids):
        return {}

    def add_track_to_playlist(self, playlist_id, track_id):
        self.added.append((playlist_id, track_id))
        return "s2"


@pytest.fixture
def pulse(monkeypatch, tmp_path):
    """run_pulse with a fake Spotify, config and profiles; returns the fake Spotify."""
    FakeSpotifyManager.instances.clear()
    config = {"fallback_playlist_id": FALLBACK, "cache_file": str(tmp_path / "cache.json")}
    monkeypatch.setattr(main, "load_config", lambda: dict(config))
    monkeypatch.setattr(main, "SpotifyManager", FakeSpotifyManager)
    monkeypatch.setattr(main, "build_profiles_for",
                        lambda spotify, playlists, matcher_type: (json.loads(json.dumps(PROFILES)), {}))

    def run(mode="normal", answer=None, **overrides):
        config.update(overrides)
        prompts = []

        def fake_input(prompt):
            prompts.append(prompt)
            return answer

        monkeypatch.setattr("builtins.input", fake_input)
        result = main.run_pulse(mode)
        return result, FakeSpotifyManager.instances[-1], prompts

    return run


@pytest.mark.parametrize("algorithm", ["hybrid", "artist_frequency"])
def test_normal_mode_asks_before_adding_with_any_algorithm(pulse, algorithm):
    result, spotify, prompts = pulse(answer="n", algorithm=algorithm)

    assert prompts, "normal mode must ask before adding"
    assert spotify.added == []
    assert result["error"] == "Cancelled by user"


def test_confirmed_choice_is_added_and_cached(pulse, tmp_path):
    result, spotify, _ = pulse(answer="1", algorithm="artist_frequency")

    assert result["success"]
    assert spotify.added == [("p1", "new")]
    cache = json.loads((tmp_path / "cache.json").read_text(encoding="utf-8"))
    assert cache["profiles"]["p1"]["artist_counts"] == {"a": 4, "b": 1}
    assert cache["snapshots"]["p1"] == "s2"


def test_default_algorithm_is_hybrid(pulse, tmp_path):
    pulse(answer="n")
    cache = json.loads((tmp_path / "cache.json").read_text(encoding="utf-8"))
    assert cache["algorithm"] == "hybrid"


def test_auto_mode_adds_without_asking(pulse):
    result, spotify, prompts = pulse(mode="auto", algorithm="artist_frequency", auto_add_min_score=0)

    assert prompts == []
    assert spotify.added == [("p1", "new")]


def test_without_suggestions_enter_picks_the_fallback(pulse, monkeypatch):
    monkeypatch.setattr(FakeSpotifyManager, "get_current_track",
                        lambda self: Track(id="new", name="Song", artist="Z", artist_id="unknown"))
    result, spotify, prompts = pulse(answer="")

    assert "Enter = f" in prompts[0]
    assert spotify.added == [(FALLBACK, "new")]


def test_local_file_is_rejected_before_anything_else(pulse, monkeypatch):
    monkeypatch.setattr(FakeSpotifyManager, "get_current_track",
                        lambda self: Track(id=None, name="demo.mp3", artist="Me"))
    result, spotify, prompts = pulse(answer="1")

    assert not result["success"]
    assert "Local file" in result["error"]
    assert spotify.added == [] and prompts == []


def test_update_cache_recomputes_weights_from_raw_counts():
    profiles = json.loads(json.dumps(PROFILES))
    snapshots = {"p1": "s1"}

    main.update_cache(profiles, snapshots, "p1", "s2", Track(id="t5", name="x", artist_id="a"))
    main.update_cache(profiles, snapshots, "p1", "s3", Track(id="t6", name="y", artist_id="c"))

    profile = profiles["p1"]
    assert profile["artist_counts"] == {"a": 4, "b": 1, "c": 1}
    assert profile["artist_weights"] == pytest.approx(smoothed_weights({"a": 4, "b": 1, "c": 1}))
    assert profile["total_tracks"] == 6
    assert profile["track_ids"][-2:] == ["t5", "t6"]
    assert snapshots["p1"] == "s3"


@pytest.mark.parametrize("value", [
    FALLBACK,
    f"https://open.spotify.com/playlist/{FALLBACK}?si=abc123",
    f"https://open.spotify.com/intl-pt/playlist/{FALLBACK}",
    f"spotify:playlist:{FALLBACK}",
    f"  {FALLBACK}\n",
])
def test_parse_playlist_id_accepts_id_link_and_uri(value):
    assert main.parse_playlist_id(value) == FALLBACK


@pytest.mark.parametrize("value", [
    None, "", "paste_your_fallback_playlist_link_here", "id_da_playlist_fallback",
    "https://open.spotify.com/track/" + FALLBACK, FALLBACK + "x",
])
def test_parse_playlist_id_rejects_placeholders_and_other_links(value):
    assert main.parse_playlist_id(value) is None


def test_fallback_link_is_used_as_its_id(pulse, monkeypatch):
    monkeypatch.setattr(FakeSpotifyManager, "get_current_track",
                        lambda self: Track(id="new", name="Song", artist="Z", artist_id="unknown"))
    result, spotify, _ = pulse(answer="", fallback_playlist_id=f"https://open.spotify.com/playlist/{FALLBACK}?si=x")

    assert spotify.added == [(FALLBACK, "new")]


def test_placeholder_fallback_stops_before_connecting(monkeypatch):
    FakeSpotifyManager.instances.clear()
    monkeypatch.setattr(main, "load_config",
                        lambda: {"fallback_playlist_id": "paste_your_fallback_playlist_link_here"})
    monkeypatch.setattr(main, "SpotifyManager", FakeSpotifyManager)

    result = main.run_pulse()

    assert "doesn't look like a Spotify playlist" in result["error"]
    assert FakeSpotifyManager.instances == []


def test_placeholder_credentials_stop_before_connecting(monkeypatch):
    FakeSpotifyManager.instances.clear()
    monkeypatch.setattr(main, "load_config", lambda: {"fallback_playlist_id": FALLBACK})
    monkeypatch.setattr(main, "SpotifyManager", FakeSpotifyManager)
    monkeypatch.setattr(main, "SPOTIFY_CLIENT_ID", "your_client_id")

    for run in (main.run_pulse, main.run_cache_refresh):
        result = run()
        assert not result["success"]
        assert "config/settings.py" in result["error"]
    assert FakeSpotifyManager.instances == []


def test_403_points_to_user_management(pulse, monkeypatch):
    def forbidden(self):
        raise spotipy.SpotifyException(403, -1, "Check settings on developer.spotify.com/dashboard, "
                                                "the user may not be registered.")

    monkeypatch.setattr(FakeSpotifyManager, "get_current_track", forbidden)
    result, spotify, prompts = pulse()

    assert "User Management" in result["error"]
    assert spotify.added == [] and prompts == []


def cached(snapshots, profiles):
    return {"snapshots": snapshots, "profiles": profiles, "artist_names": {},
            "cached_at": "2026-10-04T00:00:00+00:00"}


def fake_build(monkeypatch, readable):
    """build_profiles_for that only reads the playlists in readable, like a 429 on the rest."""
    calls = []

    def build(spotify, playlists, matcher_type):
        calls.append([p["id"] for p in playlists])
        return {p["id"]: {"id": p["id"], "name": "new"} for p in playlists if p["id"] in readable}, {}

    monkeypatch.setattr(main, "build_profiles_for", build)
    return calls


def test_changed_playlist_that_fails_keeps_old_snapshot_and_is_retried(monkeypatch):
    playlists = [{"id": "a", "name": "A", "snapshot_id": "s2"}, {"id": "b", "name": "B", "snapshot_id": "s1"}]
    calls = fake_build(monkeypatch, readable=set())

    profiles, snapshots, _ = main.sync_profiles(
        None, playlists, cached({"a": "s1", "b": "s1"}, {"a": {"name": "old"}, "b": {"name": "B"}}), "hybrid")

    assert profiles["a"] == {"name": "old"}
    assert snapshots == {"a": "s1", "b": "s1"}

    main.sync_profiles(None, playlists, cached(snapshots, profiles), "hybrid")
    assert calls == [["a"], ["a"]]


def test_new_playlist_that_fails_has_no_snapshot(monkeypatch):
    playlists = [{"id": "a", "name": "A", "snapshot_id": "s1"}, {"id": "b", "name": "B", "snapshot_id": "s1"}]
    fake_build(monkeypatch, readable={"a"})

    profiles, snapshots, _ = main.sync_profiles(None, playlists, None, "hybrid")

    assert set(profiles) == {"a"}
    assert snapshots == {"a": "s1"}


def test_playlist_read_successfully_gets_new_snapshot(monkeypatch):
    playlists = [{"id": "a", "name": "A", "snapshot_id": "s2"}]
    fake_build(monkeypatch, readable={"a"})

    profiles, snapshots, _ = main.sync_profiles(None, playlists, cached({"a": "s1"}, {"a": {"name": "old"}}), "hybrid")

    assert profiles["a"]["name"] == "new"
    assert snapshots == {"a": "s2"}


def test_snapshot_without_profile_from_an_old_cache_is_read_again(monkeypatch):
    playlists = [{"id": "a", "name": "A", "snapshot_id": "s1"}]
    calls = fake_build(monkeypatch, readable={"a"})

    profiles, _, _ = main.sync_profiles(None, playlists, cached({"a": "s1"}, {}), "hybrid")

    assert calls == [["a"]]
    assert "a" in profiles


def test_cache_from_older_version_is_rebuilt(tmp_path):
    path = tmp_path / "cache.json"
    path.write_text(json.dumps({"algorithm": "hybrid", "profiles": PROFILES}), encoding="utf-8")
    assert main.load_cache(path, "hybrid") is None


def test_save_cache_round_trip_leaves_no_temp_files(tmp_path):
    path = tmp_path / "cache.json"
    main.save_cache(path, "hybrid", PROFILES, {"p1": "s1"}, {"a": "A"})

    loaded = main.load_cache(path, "hybrid")
    assert loaded["profiles"] == PROFILES
    assert [p.name for p in tmp_path.iterdir()] == ["cache.json"]
