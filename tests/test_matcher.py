"""PlaylistMatcher ranking: direct TF-IDF, co-occurrence and the Last.fm fallback."""

import math

import pytest

import core.lastfm_client
from conftest import profile
from core.constants import CO_OCCURRENCE_WEIGHT
from core.matcher import PlaylistMatcher
from core.models import Track


def track(artist_id, artist_name=""):
    return Track(id="t", name="song", artist=artist_name, artist_id=artist_id)


def matcher(profiles, names=None):
    return PlaylistMatcher(profiles, names or {})


def test_idf_is_log_of_playlists_over_document_frequency():
    m = matcher({
        "p1": profile("p1", {"a": 0.5, "b": 0.5}),
        "p2": profile("p2", {"a": 1.0}),
        "p3": profile("p3", {"c": 1.0}),
    })
    assert m.idf["a"] == pytest.approx(math.log(3 / 2))
    assert m.idf["b"] == pytest.approx(math.log(3))


def test_artist_in_every_playlist_does_not_discriminate():
    m = matcher({
        "p1": profile("p1", {"a": 0.5, "b": 0.5}),
        "p2": profile("p2", {"a": 1.0}),
    })
    assert m.idf["a"] == 0.0
    # With no direct signal, only the co-occurrence with b is left, and b is only in p1
    [only] = m.top_matches(track("a"))
    assert only.playlist_id == "p1"
    assert only.reason.startswith("co-occurrence")


def test_direct_score_is_tf_times_idf():
    m = matcher({
        "p1": profile("p1", {"x": 0.6, "y": 0.4}),
        "p2": profile("p2", {"z": 1.0}),
    })
    [best] = m.top_matches(track("x"))

    assert best.playlist_id == "p1"
    # x and y are always together (Jaccard 1), so y adds the indirect signal
    expected = 0.6 * math.log(2) + CO_OCCURRENCE_WEIGHT * 0.4 * math.log(2)
    assert best.score == pytest.approx(expected)


def test_co_occurrence_ranks_playlist_without_the_artist():
    # x is only in p1, together with y; p2 doesn't have x, but has y
    m = matcher({
        "p1": profile("p1", {"x": 0.5, "y": 0.5}),
        "p2": profile("p2", {"y": 0.5, "w": 0.5}),
        "p3": profile("p3", {"w": 1.0}),
    })
    ranked = {r.playlist_id: r for r in m.top_matches(track("x"))}

    assert set(ranked) == {"p1", "p2"}
    assert ranked["p1"].score > ranked["p2"].score
    assert "co-occurrence" in ranked["p2"].reason


def test_top_matches_is_sorted_and_limited():
    profiles = {f"p{i}": profile(f"p{i}", {"x": i / 10, f"o{i}": 1 - i / 10}) for i in range(1, 6)}
    profiles["empty"] = profile("empty", {"other": 1.0})

    top = matcher(profiles).top_matches(track("x"), n=3)
    assert [r.playlist_id for r in top] == ["p5", "p4", "p3"]


def test_unknown_artist_has_no_match():
    m = matcher({"p1": profile("p1", {"a": 1.0}), "p2": profile("p2", {"b": 1.0})})
    assert m.top_matches(track("nobody")) == []
    assert m.top_matches(track(None)) == []


def test_lastfm_fallback_scores_playlists_through_similar_artists(monkeypatch):
    m = matcher(
        {
            "p1": profile("p1", {"jvke": 0.5, "other": 0.5}),
            "p2": profile("p2", {"ajr": 1.0}),
            "p3": profile("p3", {"misc": 1.0}),
        },
        names={"jvke": "JVKE", "ajr": "AJR", "other": "Other", "misc": "Misc"},
    )
    monkeypatch.setattr(core.lastfm_client, "get_similar_artists", lambda name, key: [
        {"name": "jvke", "match": 0.9},  # matched by name, case-insensitive
        {"name": "AJR", "match": 0.2},
        {"name": "Not In Library", "match": 1.0},
    ])

    results = m.lastfm_fallback(track(None, "Cody Fry"), api_key="key")

    assert [r.playlist_id for r in results] == ["p1", "p2"]
    assert results[0].score == pytest.approx(0.9 * 0.5 * math.log(3))
    assert results[1].score == pytest.approx(0.2 * 1.0 * math.log(3))
    assert results[0].reason == "via Last.fm: jvke (0.90)"


def test_lastfm_fallback_without_similar_artists_returns_nothing(monkeypatch):
    m = matcher({"p1": profile("p1", {"a": 1.0})}, names={"a": "A"})
    monkeypatch.setattr(core.lastfm_client, "get_similar_artists", lambda name, key: [])
    assert m.lastfm_fallback(track(None, "Someone"), api_key="key") == []
