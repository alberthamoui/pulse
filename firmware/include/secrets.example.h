#pragma once

// Copie para include/secrets.h (fora do git) e preencha.

namespace secrets {

// A ESP32 só conecta em redes de 2,4 GHz
constexpr char WIFI_SSID[] = "nome-da-rede";
constexpr char WIFI_PASSWORD[] = "senha-da-rede";

// App do Spotify Developer Dashboard
constexpr char SPOTIFY_CLIENT_ID[] = "seu-client-id";
constexpr char SPOTIFY_CLIENT_SECRET[] = "seu-client-secret";

// Gerado por: python tools/get_refresh_token.py
constexpr char SPOTIFY_REFRESH_TOKEN[] = "seu-refresh-token";

// Playlist para músicas sem destino certo (o mesmo fallback_playlist_id do
// config/config.json). Vazio esconde a opção "Fallback".
constexpr char FALLBACK_PLAYLIST_ID[] = "";

// Chave da API do Last.fm (a mesma LASTFM_API_KEY do config/settings.py). Sem
// match direto, as sugestões vêm dos artistas parecidos. Vazio desliga.
constexpr char LASTFM_API_KEY[] = "";

}  // namespace secrets
