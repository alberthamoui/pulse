"""config/settings.py and config/config.json: clear errors for what the user has to fix."""

import json
import sys

import pytest

from core.user_config import SetupError, load_config, load_settings, parse_playlist_id

PLAYLIST = "37i9dQZF1DXcBWIGoYBM5M"


@pytest.mark.parametrize("value", [
    PLAYLIST,
    f"https://open.spotify.com/playlist/{PLAYLIST}?si=abc123",
    f"https://open.spotify.com/intl-pt/playlist/{PLAYLIST}",
    f"spotify:playlist:{PLAYLIST}",
    f"  {PLAYLIST}\n",
])
def test_parse_playlist_id_accepts_id_link_and_uri(value):
    assert parse_playlist_id(value) == PLAYLIST


@pytest.mark.parametrize("value", [
    None, "", "paste_your_fallback_playlist_link_here", "id_da_playlist_fallback",
    "https://open.spotify.com/track/" + PLAYLIST, PLAYLIST + "x",
])
def test_parse_playlist_id_rejects_placeholders_and_other_links(value):
    assert parse_playlist_id(value) is None


def test_missing_settings_explains_how_to_create_it(monkeypatch):
    monkeypatch.setitem(sys.modules, "config.settings", None)  # makes the import fail
    with pytest.raises(SetupError, match="settings.example.py"):
        load_settings()


@pytest.mark.parametrize("field, value", [("SPOTIFY_CLIENT_ID", "your_client_id"),
                                          ("SPOTIFY_CLIENT_SECRET", "your_client_secret"),
                                          ("SPOTIFY_CLIENT_ID", "  ")])
def test_placeholder_credentials_are_rejected(monkeypatch, field, value):
    monkeypatch.setattr(sys.modules["config.settings"], field, value)
    with pytest.raises(SetupError, match="aren't filled in"):
        load_settings()


def test_older_settings_without_lastfm_key_still_load(monkeypatch):
    monkeypatch.delattr(sys.modules["config.settings"], "LASTFM_API_KEY")
    assert load_settings().lastfm_api_key == ""


def test_config_reads_the_fallback_link_and_defaults(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"fallback_playlist_id": f"https://open.spotify.com/playlist/{PLAYLIST}"}))

    config = load_config(path)
    assert config.fallback_playlist_id == PLAYLIST
    assert config.cache_path.name == ".pulse_cache.json"
    assert config.auto_add_min_score == 0.5


def test_missing_or_invalid_config_is_a_setup_error(tmp_path):
    with pytest.raises(SetupError, match="config.example.json"):
        load_config(tmp_path / "missing.json")

    broken = tmp_path / "config.json"
    broken.write_text("{not json")
    with pytest.raises(SetupError, match="invalid"):
        load_config(broken)
