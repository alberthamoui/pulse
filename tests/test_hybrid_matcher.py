"""Scoring do HybridMatcher: TF-IDF direto, co-ocorrência e fallback do Last.fm."""

import math

import pytest

import core.lastfm_client
from conftest import profile
from config.constants import ALGO_ALPHA, ALGO_BETA
from core.hybrid_matcher import HybridMatcher
from core.models import Track


def track(artist_id, artist_name=""):
    return Track(id="t", nome="song", artista=artist_name, id_artista=artist_id)


def trained(spotify, profiles, names=None):
    matcher = HybridMatcher(spotify)
    matcher.train(profiles, artist_names=names or {})
    return matcher


def test_idf_is_log_of_playlists_over_document_frequency(spotify):
    matcher = trained(spotify, {
        "p1": profile("p1", {"a": 0.5, "b": 0.5}),
        "p2": profile("p2", {"a": 1.0}),
        "p3": profile("p3", {"c": 1.0}),
    })
    assert matcher.idf["a"] == pytest.approx(math.log(3 / 2))
    assert matcher.idf["b"] == pytest.approx(math.log(3))


def test_artist_in_every_playlist_does_not_discriminate(spotify):
    matcher = trained(spotify, {
        "p1": profile("p1", {"a": 0.5, "b": 0.5}),
        "p2": profile("p2", {"a": 1.0}),
    })
    assert matcher.idf["a"] == 0.0
    # Sem sinal direto, só sobra a co-ocorrência com b, que está apenas em p1
    [only] = matcher.top_matches(track("a"))
    assert only.playlist_id == "p1"
    assert only.reason.startswith("co-ocorrência")


def test_direct_score_is_tf_times_idf(spotify):
    matcher = trained(spotify, {
        "p1": profile("p1", {"x": 0.6, "y": 0.4}),
        "p2": profile("p2", {"z": 1.0}),
    })
    [best] = matcher.top_matches(track("x"))

    assert best.playlist_id == "p1"
    # x e y estão sempre juntos (Jaccard 1), então y soma o sinal indireto
    expected = ALGO_ALPHA * (0.6 * math.log(2) + ALGO_BETA * 0.4 * math.log(2))
    assert best.score == pytest.approx(expected)


def test_co_occurrence_ranks_playlist_without_the_artist(spotify):
    # x só está em p1, junto com y; p2 não tem x, mas tem y
    matcher = trained(spotify, {
        "p1": profile("p1", {"x": 0.5, "y": 0.5}),
        "p2": profile("p2", {"y": 0.5, "w": 0.5}),
        "p3": profile("p3", {"w": 1.0}),
    })
    ranked = {r.playlist_id: r for r in matcher.top_matches(track("x"))}

    assert set(ranked) == {"p1", "p2"}
    assert ranked["p1"].score > ranked["p2"].score
    assert "co-ocorrência" in ranked["p2"].reason


def test_top_matches_is_sorted_and_limited(spotify):
    profiles = {f"p{i}": profile(f"p{i}", {"x": i / 10, f"o{i}": 1 - i / 10}) for i in range(1, 6)}
    profiles["empty"] = profile("empty", {"other": 1.0})
    matcher = trained(spotify, profiles)

    top = matcher.top_matches(track("x"), n=3)
    assert [r.playlist_id for r in top] == ["p5", "p4", "p3"]


def test_unknown_artist_has_no_direct_match(spotify):
    matcher = trained(spotify, {"p1": profile("p1", {"a": 1.0}), "p2": profile("p2", {"b": 1.0})})
    assert matcher.top_matches(track("nobody")) == []
    assert matcher.match(track("nobody")) is None


def test_lastfm_fallback_scores_playlists_through_similar_artists(spotify, monkeypatch):
    matcher = trained(
        spotify,
        {
            "p1": profile("p1", {"jvke": 0.5, "other": 0.5}),
            "p2": profile("p2", {"ajr": 1.0}),
            "p3": profile("p3", {"misc": 1.0}),
        },
        names={"jvke": "JVKE", "ajr": "AJR", "other": "Other", "misc": "Misc"},
    )
    monkeypatch.setattr(core.lastfm_client, "get_similar_artists", lambda name, key: [
        {"name": "jvke", "match": 0.9},  # casa pelo nome, sem diferenciar maiúsculas
        {"name": "AJR", "match": 0.2},
        {"name": "Not In Library", "match": 1.0},
    ])

    results = matcher.lastfm_fallback(track(None, "Cody Fry"), api_key="key")

    assert [r.playlist_id for r in results] == ["p1", "p2"]
    assert results[0].score == pytest.approx(0.9 * 0.5 * math.log(3))
    assert results[1].score == pytest.approx(0.2 * 1.0 * math.log(3))
    assert results[0].match_type == "lastfm"
    assert "JVKE" not in results[0].reason and "jvke (0.90)" in results[0].reason


def test_lastfm_fallback_without_similar_artists_returns_nothing(spotify, monkeypatch):
    matcher = trained(spotify, {"p1": profile("p1", {"a": 1.0})}, names={"a": "A"})
    monkeypatch.setattr(core.lastfm_client, "get_similar_artists", lambda name, key: [])
    assert matcher.lastfm_fallback(track(None, "Someone"), api_key="key") == []
