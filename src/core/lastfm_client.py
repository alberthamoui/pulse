import json
import urllib.error
import urllib.request
import urllib.parse
from typing import List, Dict
from config.constants import LASTFM_SIMILAR_LIMIT, LASTFM_TIMEOUT

LASTFM_BASE = "https://ws.audioscrobbler.com/2.0/"


def get_similar_artists(artist_name: str, api_key: str, limit: int = LASTFM_SIMILAR_LIMIT) -> List[Dict]:
    """
    Retorna lista de {'name': str, 'match': float} ordenada por match desc.
    Retorna [] se api_key não configurada ou em caso de erro.
    """
    if not api_key:
        return []
    url = (
        f"{LASTFM_BASE}?method=artist.getSimilar"
        f"&artist={urllib.parse.quote(artist_name)}"
        f"&api_key={api_key}&format=json&limit={limit}"
    )
    try:
        with urllib.request.urlopen(url, timeout=LASTFM_TIMEOUT) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        # O corpo traz o motivo ({"error": 10, "message": "Invalid API key ..."})
        try:
            detail = json.loads(e.read()).get("message", "")
        except Exception:
            detail = ""
        print(f"  Last.fm: HTTP {e.code} {detail}".rstrip())
        return []
    except Exception as e:
        print(f"  Last.fm: falha na requisição ({e})")
        return []

    if "error" in data:
        print(f"  Last.fm: erro {data['error']}: {data.get('message', '')}")
        return []
    artists = data.get("similarartists", {}).get("artist", [])
    return [{"name": a["name"], "match": float(a["match"])} for a in artists]
