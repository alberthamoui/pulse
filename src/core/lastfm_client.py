import json
import urllib.request
import urllib.parse
from typing import List, Dict

LASTFM_BASE = "https://ws.audioscrobbler.com/2.0/"


def get_similar_artists(artist_name: str, api_key: str, limit: int = 20) -> List[Dict]:
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
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read())
        artists = data.get("similarartists", {}).get("artist", [])
        return [{"name": a["name"], "match": float(a["match"])} for a in artists]
    except Exception:
        return []
