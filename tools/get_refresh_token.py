"""
Gera o refresh token do Spotify para o firmware do Pulse (firmware/include/secrets.h).

Antes de rodar, cadastre http://127.0.0.1:8888/callback em "Redirect URIs" no app do
Spotify Developer Dashboard. O Spotify só aceita redirect HTTP em endereço de loopback.

O client id e o secret vêm, nesta ordem, de SPOTIPY_CLIENT_ID/SPOTIPY_CLIENT_SECRET,
de config/settings.py (o mesmo do Pulse em Python) ou são pedidos no terminal.

Uso:
    python tools/get_refresh_token.py
"""

import getpass
import os
import sys
import warnings
from pathlib import Path

from spotipy.cache_handler import MemoryCacheHandler
from spotipy.oauth2 import SpotifyOAuth

REDIRECT_URI = "http://127.0.0.1:8888/callback"
SCOPES = (
    "user-read-currently-playing "
    "playlist-read-private "
    "playlist-read-collaborative "
    "playlist-modify-public "
    "playlist-modify-private"
)


def load_credentials() -> tuple[str, str]:
    client_id = os.environ.get("SPOTIPY_CLIENT_ID", "")
    client_secret = os.environ.get("SPOTIPY_CLIENT_SECRET", "")

    if not (client_id and client_secret):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        try:
            from config import settings

            client_id = client_id or getattr(settings, "SPOTIFY_CLIENT_ID", "")
            client_secret = client_secret or getattr(settings, "SPOTIFY_CLIENT_SECRET", "")
            if client_id and client_secret:
                print("Usando o client id e o secret de config/settings.py")
        except ImportError:
            pass

    client_id = client_id or input("Client ID: ").strip()
    client_secret = client_secret or getpass.getpass("Client secret: ").strip()
    return client_id, client_secret


def main() -> None:
    client_id, client_secret = load_credentials()

    # Sem cache em disco: o token só aparece no terminal.
    auth = SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=REDIRECT_URI,
        scope=SCOPES,
        cache_handler=MemoryCacheHandler(),
        open_browser=True,
        show_dialog=True,
    )

    print("Abrindo o navegador para autorizar o Pulse...")
    code = auth.get_auth_response()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)  # as_dict está obsoleto no spotipy
        token = auth.get_access_token(code, as_dict=True, check_cache=False)

    refresh_token = token.get("refresh_token")
    if not refresh_token:
        sys.exit("O Spotify não devolveu um refresh token.")

    missing = set(SCOPES.split()) - set(token.get("scope", "").split())
    if missing:
        print(f"\nAviso: escopos não concedidos: {', '.join(sorted(missing))}")

    print("\nCole em firmware/include/secrets.h:\n")
    print(f'constexpr char SPOTIFY_REFRESH_TOKEN[] = "{refresh_token}";')


if __name__ == "__main__":
    main()
