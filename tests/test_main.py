"""main.py flow: confirmation before adding, auto mode and the errors the user sees."""

import json
import sys

import pytest
import spotipy

import core.cache as cache_module
import main
from core.models import PlaylistProfile, Track
from core.user_config import Config, parse_playlist_id

FALLBACK = "37i9dQZF1DXcBWIGoYBM5M"
PLAYLISTS = [{"id": "p1", "name": "P1", "snapshot_id": "s1"}, {"id": "p2", "name": "P2", "snapshot_id": "s1"}]


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

    def add_track_to_playlist(self, playlist_id, track_id):
        self.added.append((playlist_id, track_id))
        return "s2"


def profiles():
    # Artist a is only in P1, so P1 is the suggestion for a song by a
    return {
        "p1": PlaylistProfile(id="p1", name="P1", artist_counts={"a": 3, "b": 1}, track_ids=["t1", "t2", "t3", "t4"]),
        "p2": PlaylistProfile(id="p2", name="P2", artist_counts={"c": 2}, track_ids=["t5", "t6"]),
    }


@pytest.fixture
def pulse(monkeypatch, tmp_path):
    """run_pulse with a fake Spotify, config and profiles; returns the fake Spotify."""
    FakeSpotifyManager.instances.clear()
    config = {"fallback_playlist_id": FALLBACK}
    monkeypatch.setattr(main, "load_config", lambda: Config(
        fallback_playlist_id=parse_playlist_id(config["fallback_playlist_id"]),
        cache_path=tmp_path / "cache.json",
        auto_add_min_score=config.get("auto_add_min_score", 0.5),
    ))
    monkeypatch.setattr(main, "SpotifyManager", FakeSpotifyManager)
    monkeypatch.setattr(cache_module, "build_profiles", lambda spotify, playlists: (profiles(), {}))

    def run(mode="normal", answer=None, **overrides):
        config.update(overrides)
        prompts = []

        def fake_input(prompt):
            prompts.append(prompt)
            if len(prompts) > 3:
                raise AssertionError(f"asked too many times: {prompts}")
            return answer

        monkeypatch.setattr("builtins.input", fake_input)
        result = main.run_pulse(mode)
        spotify = FakeSpotifyManager.instances[-1] if FakeSpotifyManager.instances else None
        return result, spotify, prompts

    return run


def unknown_artist(monkeypatch):
    monkeypatch.setattr(FakeSpotifyManager, "get_current_track",
                        lambda self: Track(id="new", name="Song", artist="Z", artist_id="unknown"))


def test_normal_mode_asks_before_adding(pulse):
    result, spotify, prompts = pulse(answer="n")

    assert prompts, "normal mode must ask before adding"
    assert spotify.added == []
    assert result["error"] == "Cancelled by user"


def test_confirmed_choice_is_added_and_cached(pulse, tmp_path):
    result, spotify, _ = pulse(answer="1")

    assert result["success"]
    assert spotify.added == [("p1", "new")]
    cache = json.loads((tmp_path / "cache.json").read_text(encoding="utf-8"))
    assert cache["profiles"]["p1"]["artist_counts"] == {"a": 4, "b": 1}
    assert cache["snapshots"]["p1"] == "s2"


def test_auto_mode_adds_without_asking(pulse):
    result, spotify, prompts = pulse(mode="auto", auto_add_min_score=0)

    assert prompts == []
    assert spotify.added == [("p1", "new")]


def test_auto_mode_does_not_add_below_the_minimum(pulse):
    result, spotify, prompts = pulse(mode="auto", auto_add_min_score=1000)

    assert result["error"] == "Score below the auto-add minimum"
    assert spotify.added == [] and prompts == []


def test_dry_run_adds_nothing(pulse):
    result, spotify, prompts = pulse(mode="dry-run")

    assert result["playlist"] == "P1"
    assert spotify.added == [] and prompts == []


def test_without_suggestions_enter_picks_the_fallback(pulse, monkeypatch):
    unknown_artist(monkeypatch)
    result, spotify, prompts = pulse(answer="")

    assert "Enter = f" in prompts[0]
    assert spotify.added == [(FALLBACK, "new")]


def test_fallback_link_is_used_as_its_id(pulse, monkeypatch):
    unknown_artist(monkeypatch)
    result, spotify, _ = pulse(answer="", fallback_playlist_id=f"https://open.spotify.com/playlist/{FALLBACK}?si=x")

    assert spotify.added == [(FALLBACK, "new")]


def test_local_file_is_rejected_before_anything_else(pulse, monkeypatch):
    monkeypatch.setattr(FakeSpotifyManager, "get_current_track",
                        lambda self: Track(id=None, name="demo.mp3", artist="Me"))
    result, spotify, prompts = pulse(answer="1")

    assert not result["success"]
    assert "Local file" in result["error"]
    assert spotify.added == [] and prompts == []


def test_placeholder_fallback_stops_before_connecting(pulse):
    result, spotify, _ = pulse(fallback_playlist_id="paste_your_fallback_playlist_link_here")

    assert "doesn't look like a Spotify playlist" in result["error"]
    assert spotify is None


@pytest.mark.parametrize("run", [main.run_pulse, main.run_cache_refresh])
def test_placeholder_credentials_stop_before_connecting(monkeypatch, tmp_path, run):
    FakeSpotifyManager.instances.clear()
    monkeypatch.setattr(main, "load_config", lambda: Config(FALLBACK, tmp_path / "cache.json", 0.5))
    monkeypatch.setattr(main, "SpotifyManager", FakeSpotifyManager)
    monkeypatch.setattr(sys.modules["config.settings"], "SPOTIFY_CLIENT_ID", "your_client_id")

    result = run()

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


def test_network_error_is_reported_not_raised(pulse, monkeypatch):
    def offline(self):
        raise ConnectionError("no route to host")

    monkeypatch.setattr(FakeSpotifyManager, "get_current_track", offline)
    result, _, _ = pulse()

    assert result["error"] == "Spotify/connection error: no route to host"
