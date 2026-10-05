"""main.py flow: confirmation before adding, cache and edge cases."""

import json

import pytest

import main
from core.models import Track
from core.playlist_analyzer import smoothed_weights

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
    config = {"fallback_playlist_id": "fb", "cache_file": str(tmp_path / "cache.json")}
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
    assert spotify.added == [("fb", "new")]


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
