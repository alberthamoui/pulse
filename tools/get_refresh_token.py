"""
Gera o refresh token do Spotify para o firmware do Pulse (firmware/include/secrets.h).

Usa o fluxo Authorization Code with PKCE: só o client id é necessário, e o aparelho
renova o token sem guardar o client secret.

Antes de rodar, cadastre http://127.0.0.1:8888/callback em "Redirect URIs" no app do
Spotify Developer Dashboard. O Spotify só aceita redirect HTTP em endereço de loopback.

O client id vem, nesta ordem, de SPOTIPY_CLIENT_ID, de config/settings.py (o mesmo do
Pulse em Python) ou é pedido no terminal.

Uso:
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
            if client_id:
                print("Usando o client id de config/settings.py")
        except ImportError:
            pass

    return client_id or input("Client ID: ").strip()


def main() -> None:
    # Sem cache em disco: o token só aparece no terminal. O state aleatório é
    # conferido no callback e protege contra CSRF.
    auth = SpotifyPKCE(
        client_id=load_client_id(),
        redirect_uri=REDIRECT_URI,
        scope=SCOPES,
        state=secrets.token_urlsafe(16),
        cache_handler=MemoryCacheHandler(),
        open_browser=True,
    )

    print("Abrindo o navegador para autorizar o Pulse...")
    auth.get_access_token(check_cache=False)
    token = auth.cache_handler.get_cached_token() or {}

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
