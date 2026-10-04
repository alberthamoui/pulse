"""Cliente do Last.fm: leitura da resposta e falhas com o motivo no log."""

import io
import json
import urllib.error
import urllib.request

from core.lastfm_client import get_similar_artists


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def test_parses_names_and_match_as_float(monkeypatch):
    body = {"similarartists": {"artist": [
        {"name": "JVKE", "match": "0.906903", "image": []},
        {"name": "AJR", "match": "0.891089", "image": []},
    ]}}
    calls = []

    def fake_urlopen(url, timeout):
        calls.append(url)
        return FakeResponse(json.dumps(body).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    result = get_similar_artists("Cody Fry", api_key="key", limit=2)

    assert result == [{"name": "JVKE", "match": 0.906903}, {"name": "AJR", "match": 0.891089}]
    assert "artist=Cody%20Fry" in calls[0] and "limit=2" in calls[0]


def test_without_api_key_does_not_call_the_network(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("não deveria chamar a rede")

    monkeypatch.setattr(urllib.request, "urlopen", fail)
    assert get_similar_artists("Cody Fry", api_key="") == []


def test_network_errors_return_empty_list(monkeypatch, capsys):
    def boom(url, timeout):
        raise TimeoutError("timed out")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    assert get_similar_artists("Cody Fry", api_key="key") == []
    assert "timed out" in capsys.readouterr().out


def test_invalid_key_shows_the_reason(monkeypatch, capsys):
    def forbidden(url, timeout):
        body = io.BytesIO(json.dumps({"error": 10, "message": "Invalid API key"}).encode())
        raise urllib.error.HTTPError(url, 403, "Forbidden", {}, body)

    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    assert get_similar_artists("Cody Fry", api_key="wrong") == []
    assert "HTTP 403 Invalid API key" in capsys.readouterr().out


def test_unknown_artist_error_in_body_returns_empty_list(monkeypatch, capsys):
    body = {"error": 6, "message": "The artist you supplied could not be found"}
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda url, timeout: FakeResponse(json.dumps(body).encode()))
    assert get_similar_artists("Nobody", api_key="key") == []
    assert "could not be found" in capsys.readouterr().out
