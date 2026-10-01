#pragma once

#include <Arduino.h>
#include <ArduinoJson.h>
#include <WiFiClientSecure.h>

#include "backend.h"
#include "config.h"

struct SpotifyUser {
  String id;
  String displayName;
};

// Cliente HTTPS da Web API do Spotify: renova o access token a partir do refresh
// token, trata 401 (renova e repete uma vez) e 429 (respeita o Retry-After) e lê
// as respostas em streaming com filtro, sem carregar o JSON inteiro na RAM.
class SpotifyClient {
 public:
  // Exige o LittleFS montado: é onde fica o refresh token mais recente.
  void begin();

  // Renova o access token se ele não existe ou expira em menos de cfg::TOKEN_MARGIN_MS.
  BackendError ensureToken();

  BackendError getMe(SpotifyUser& out);

  // Maior Retry-After (429) que vale esperar antes de desistir da chamada.
  void setMaxRetryAfter(uint32_t seconds) { maxRetryAfterS_ = seconds; }

  // Chamada genérica à Web API. url pode ser um caminho ("/me") ou uma URL
  // completa (o "next" da paginação). status recebe o código HTTP final.
  BackendError call(const char* method, const String& url, const String& body,
                    const JsonDocument& filter, JsonDocument& out, int& status);

 private:
  BackendError refreshAccessToken();
  void loadRefreshToken();
  void saveRefreshToken(const String& token);

  WiFiClientSecure tls_;
  String refreshToken_;
  String accessToken_;
  uint32_t expiresAt_ = 0;  // millis()
  uint32_t maxRetryAfterS_ = cfg::MAX_RETRY_AFTER_S;
};
