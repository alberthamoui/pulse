#pragma once

#include <Arduino.h>
#include <ArduinoJson.h>
#include <WiFiClientSecure.h>

#include "backend.h"
#include "config.h"

// Encodes for query strings and x-www-form-urlencoded bodies (RFC 3986).
String urlEncode(const String& s);

struct SpotifyUser {
  String id;
  String displayName;
};

// HTTPS client for the Spotify Web API: refreshes the access token from the
// refresh token, handles 401 (refreshes and retries once) and 429 (honors
// Retry-After) and streams the responses through a filter, without loading the
// whole JSON into RAM.
class SpotifyClient {
 public:
  // Needs LittleFS mounted: that's where the latest refresh token lives.
  void begin();

  // Refreshes the access token if there's none or it expires in less than cfg::TOKEN_MARGIN_MS.
  BackendError ensureToken();

  BackendError getMe(SpotifyUser& out);

  // Longest Retry-After (429) worth waiting before giving up on the call.
  void setMaxRetryAfter(uint32_t seconds) { maxRetryAfterS_ = seconds; }

  // Generic Web API call. url can be a path ("/me") or a full URL (the
  // pagination "next"). status gets the final HTTP code.
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
