"""
Generates the Spotify refresh token for the Pulse firmware (firmware/include/secrets.h).

Uses the Authorization Code with PKCE flow: only the client id is needed, and the device
refreshes the token without storing the client secret.

Before running it, add http://127.0.0.1:8888/callback to "Redirect URIs" in the app on the
Spotify Developer Dashboard. Spotify only accepts HTTP redirects on a loopback address.

The client id comes, in this order, from SPOTIPY_CLIENT_ID, from config/settings.py (the
same one used by the Python version of Pulse) or is asked in the terminal.

Usage:
    python tools/get_refresh_token.py
"""

import os
import secrets
import sys
from pathlib import Path

from spotipy.cache_handler import MemoryCacheHandler
from spotipy.oauth2 import SpotifyPKCE

REDIRECT_URI = "http://127.0.0.1:8888/callback"
SCOPES = (
    "user-read-currently-playing "
    "playlist-read-private "
    "playlist-read-collaborative "
    "playlist-modify-public "
    "playlist-modify-private"
)


def load_client_id() -> str:
    client_id = os.environ.get("SPOTIPY_CLIENT_ID", "")

    if not client_id:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        try:
            from config import settings

            client_id = getattr(settings, "SPOTIFY_CLIENT_ID", "")
            if client_id == "your_client_id":  # settings.example.py placeholder: ask instead
                client_id = ""
            if client_id:
                print("Using the client id from config/settings.py")
        except ImportError:
            pass

    return client_id or input("Client ID: ").strip()


def main() -> None:
    client_id = load_client_id()
    if not client_id:
        sys.exit("No client ID: fill in SPOTIFY_CLIENT_ID in config/settings.py or set SPOTIPY_CLIENT_ID.")

    # No cache on disk: the token only shows up in the terminal. The random state is
    # checked in the callback and protects against CSRF.
    auth = SpotifyPKCE(
        client_id=client_id,
        redirect_uri=REDIRECT_URI,
        scope=SCOPES,
        state=secrets.token_urlsafe(16),
        cache_handler=MemoryCacheHandler(),
        open_browser=True,
    )

    print("Opening the browser to authorize Pulse...")
    auth.get_access_token(check_cache=False)
    token = auth.cache_handler.get_cached_token() or {}

    refresh_token = token.get("refresh_token")
    if not refresh_token:
        sys.exit("Spotify did not return a refresh token.")

    missing = set(SCOPES.split()) - set(token.get("scope", "").split())
    if missing:
        print(f"\nWarning: scopes not granted: {', '.join(sorted(missing))}")

    print("\nPaste into firmware/include/secrets.h:\n")
    print(f'constexpr char SPOTIFY_REFRESH_TOKEN[] = "{refresh_token}";')


if __name__ == "__main__":
    main()
