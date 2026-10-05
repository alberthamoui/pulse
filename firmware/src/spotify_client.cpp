#include "spotify_client.h"

#include <HTTPClient.h>
#include <LittleFS.h>
#include <WiFi.h>
#include <sys/stat.h>

#include "certs.h"
#include "config.h"

#if !__has_include("secrets.h")
#error "Create include/secrets.h from include/secrets.example.h"
#endif
#include "secrets.h"

namespace {

constexpr char API_BASE[] = "https://api.spotify.com/v1";
constexpr char TOKEN_URL[] = "https://accounts.spotify.com/api/token";

// Line 1: the secrets.h refresh token the saved one came from. Line 2: the current one.
// If secrets.h changes (new authorization), the saved file is ignored.
constexpr char AUTH_FILE[] = "/auth.txt";
constexpr char AUTH_TMP[] = "/auth.tmp";

// Transport error (status < 0): no Wi-Fi or a connection/TLS failure.
BackendError transportError() {
  return WiFi.status() == WL_CONNECTED ? BackendError::Api : BackendError::NoWifi;
}

void logHttpError(const char* tag, const char* what, HTTPClient& http, int status) {
  if (status > 0) {
    // Spotify error bodies are short JSONs, with no secrets
    Serial.printf("[%s] %s: HTTP %d %s\n", tag, what, status, http.getString().c_str());
  } else {
    Serial.printf("[%s] %s: %s\n", tag, what, HTTPClient::errorToString(status).c_str());
  }
}

}  // namespace

String urlEncode(const String& s) {
  static const char HEX_DIGITS[] = "0123456789ABCDEF";
  String out;
  out.reserve(s.length() * 3);
  for (size_t i = 0; i < s.length(); ++i) {
    const unsigned char c = s[i];
    if (isalnum(c) || c == '-' || c == '_' || c == '.' || c == '~') {
      out += static_cast<char>(c);
    } else {
      out += '%';
      out += HEX_DIGITS[c >> 4];
      out += HEX_DIGITS[c & 0xF];
    }
  }
  return out;
}

void SpotifyClient::begin() {
  tls_.setCACert(SPOTIFY_ROOT_CAS);
  // WiFiClientSecure has its own _timeout that shadows the one in Stream, so
  // HTTPClient's setTimeout() never reaches the readBytes() used by ArduinoJson,
  // which stays at the 1 s default and cuts large responses in the middle.
  static_cast<Stream&>(tls_).setTimeout(cfg::HTTP_TIMEOUT_MS);
  loadRefreshToken();
}

void SpotifyClient::loadRefreshToken() {
  refreshToken_ = secrets::SPOTIFY_REFRESH_TOKEN;

  // LittleFS.exists() logs an error when the file doesn't exist; stat() doesn't
  struct stat st;
  if (stat((String("/littlefs") + AUTH_FILE).c_str(), &st) != 0) return;

  File f = LittleFS.open(AUTH_FILE, "r");
  if (!f) return;
  String origin = f.readStringUntil('\n');
  String current = f.readStringUntil('\n');
  f.close();
  origin.trim();
  current.trim();

  if (origin == secrets::SPOTIFY_REFRESH_TOKEN && current.length() > 0) {
    refreshToken_ = current;
    Serial.println("[auth] using the refresh token saved on LittleFS");
  }
}

void SpotifyClient::saveRefreshToken(const String& token) {
  // The refresh token can change on every refresh, and the previous one may stop
  // working: write to a temp file and rename, so a power cut doesn't lose the token
  File f = LittleFS.open(AUTH_TMP, "w");
  if (!f) {
    Serial.println("[auth] failed to save the refresh token");
    return;
  }
  f.println(secrets::SPOTIFY_REFRESH_TOKEN);
  f.println(token);
  f.close();
  // LittleFS replaces the target on rename; if this version refuses, remove it first
  if (!LittleFS.rename(AUTH_TMP, AUTH_FILE)) {
    LittleFS.remove(AUTH_FILE);
    if (!LittleFS.rename(AUTH_TMP, AUTH_FILE)) {
      Serial.println("[auth] failed to save the refresh token");
    }
  }
}

BackendError SpotifyClient::ensureToken() {
  const int32_t remaining = static_cast<int32_t>(expiresAt_ - millis());
  if (!accessToken_.isEmpty() && remaining > static_cast<int32_t>(cfg::TOKEN_MARGIN_MS)) {
    return BackendError::None;
  }
  return refreshAccessToken();
}

BackendError SpotifyClient::refreshAccessToken() {
  accessToken_ = "";
  if (WiFi.status() != WL_CONNECTED) return BackendError::NoWifi;

  HTTPClient http;
  http.useHTTP10(true);  // no chunked: getStream() doesn't decode chunked
  http.setTimeout(cfg::HTTP_TIMEOUT_MS);
  if (!http.begin(tls_, TOKEN_URL)) return BackendError::Api;
  http.addHeader("Content-Type", "application/x-www-form-urlencoded");

  // PKCE: the device doesn't store the client secret, only the client id goes in the body
  const int status = http.POST("grant_type=refresh_token&refresh_token=" +
                               urlEncode(refreshToken_) +
                               "&client_id=" + urlEncode(secrets::SPOTIFY_CLIENT_ID));
  if (status <= 0) {
    logHttpError("auth", "failed to refresh the token", http, status);
    http.end();
    return transportError();
  }
  if (status != 200) {
    // 400 invalid_grant: refresh token expired, revoked or generated without PKCE.
    // invalid_client: wrong client id. Either way, the fix is to authorize again.
    const String body = http.getString();
    http.end();
    Serial.printf("[auth] failed to refresh the token: HTTP %d %s\n", status, body.c_str());
    const bool reauthorize =
        body.indexOf("invalid_grant") >= 0 || body.indexOf("invalid_client") >= 0;
    return reauthorize ? BackendError::AuthExpired : BackendError::Api;
  }

  JsonDocument filter;
  filter["access_token"] = true;
  filter["expires_in"] = true;
  filter["refresh_token"] = true;
  JsonDocument doc;
  const DeserializationError jsonErr =
      deserializeJson(doc, http.getStream(), DeserializationOption::Filter(filter));
  http.end();
  if (jsonErr) {
    Serial.printf("[auth] invalid token response: %s\n", jsonErr.c_str());
    return BackendError::Api;
  }

  accessToken_ = doc["access_token"] | "";
  if (accessToken_.isEmpty()) {
    Serial.println("[auth] token response without access_token");
    return BackendError::Api;
  }
  const uint32_t expiresIn = doc["expires_in"] | 3600;
  expiresAt_ = millis() + expiresIn * 1000UL;
  Serial.printf("[auth] access token refreshed (expires in %us)\n", expiresIn);

  // The refresh can return a new refresh token, which becomes the valid one
  const char* rotated = doc["refresh_token"];
  if (rotated != nullptr && refreshToken_ != rotated) {
    refreshToken_ = rotated;
    saveRefreshToken(refreshToken_);
    Serial.println("[auth] new refresh token saved on LittleFS");
  }
  return BackendError::None;
}

BackendError SpotifyClient::call(const char* method, const String& url, const String& body,
                                 const JsonDocument& filter, JsonDocument& out, int& status) {
  // The Bearer token only goes to the Spotify API: full URLs only if they point there
  const String apiPrefix = String(API_BASE) + "/";
  if (url.startsWith("https://") && !url.startsWith(apiPrefix)) {
    Serial.printf("[api] URL outside the Spotify API refused: %s\n", url.c_str());
    return BackendError::Api;
  }
  const String fullUrl = url.startsWith("https://") ? url : String(API_BASE) + url;
  bool retriedAfter401 = false;
  status = 0;
  // Only GET is retried after a network failure: a POST may have reached Spotify
  // before the connection dropped, and retrying would add the song twice
  const bool idempotent = strcmp(method, "GET") == 0;

  for (uint8_t attempt = 0; attempt < cfg::MAX_ATTEMPTS; ++attempt) {
    const bool canRetry =
        idempotent && WiFi.status() == WL_CONNECTED && attempt + 1 < cfg::MAX_ATTEMPTS;
    const BackendError tokenErr = ensureToken();
    if (tokenErr != BackendError::None) return tokenErr;

    HTTPClient http;
    http.useHTTP10(true);
    http.setTimeout(cfg::HTTP_TIMEOUT_MS);
    if (!http.begin(tls_, fullUrl)) return BackendError::Api;
    http.addHeader("Authorization", "Bearer " + accessToken_);
    if (body.length() > 0) http.addHeader("Content-Type", "application/json");
    const char* headers[] = {"Retry-After"};
    http.collectHeaders(headers, 1);

    status = http.sendRequest(method, body);

    if (status == 401 && !retriedAfter401) {
      http.end();
      Serial.println("[api] 401: refreshing the token and retrying");
      retriedAfter401 = true;
      accessToken_ = "";  // forces a refresh on the next ensureToken()
      continue;
    }

    if (status == 429) {
      uint32_t wait = http.header("Retry-After").toInt();
      http.end();
      if (wait == 0) wait = 1;
      if (wait > maxRetryAfterS_) {
        Serial.printf("[api] 429: Retry-After of %us, giving up\n", wait);
        return BackendError::RateLimited;
      }
      Serial.printf("[api] 429: waiting %us\n", wait);
      delay(wait * 1000UL);
      continue;
    }

    // Connection failure (TLS or network): usually works on the next attempt. The
    // free memory in the log shows whether TLS ran out of heap for the handshake.
    if (status < 0 && canRetry) {
      http.end();
      Serial.printf("[api] %s %s: %s (free heap %u, largest block %u), retrying\n", method,
                    url.c_str(), HTTPClient::errorToString(status).c_str(), ESP.getFreeHeap(),
                    ESP.getMaxAllocHeap());
      delay(500);
      continue;
    }

    if (status < 200 || status >= 300) {
      logHttpError("api", (String(method) + " " + url).c_str(), http, status);
      http.end();
      return status > 0 ? BackendError::Api : transportError();
    }

    out.clear();
    if (status == 204) {  // no body (e.g. nothing playing)
      http.end();
      return BackendError::None;
    }
    const DeserializationError jsonErr =
        deserializeJson(out, http.getStream(), DeserializationOption::Filter(filter));
    http.end();
    // IncompleteInput: the connection dropped in the middle of the response
    if (jsonErr == DeserializationError::IncompleteInput && canRetry) {
      Serial.printf("[api] %s %s: response cut off, retrying\n", method, url.c_str());
      delay(500);
      continue;
    }
    if (jsonErr) {
      Serial.printf("[api] %s %s: invalid JSON (%s)\n", method, url.c_str(), jsonErr.c_str());
      return BackendError::Api;
    }
    return BackendError::None;
  }

  return status == 429 ? BackendError::RateLimited : BackendError::Api;
}

BackendError SpotifyClient::getMe(SpotifyUser& out) {
  JsonDocument filter;
  filter["id"] = true;
  filter["display_name"] = true;
  JsonDocument doc;
  int status = 0;

  const BackendError err = call("GET", "/me", "", filter, doc, status);
  if (err != BackendError::None) return err;

  out.id = doc["id"] | "";
  out.displayName = doc["display_name"] | "";
  if (out.displayName.isEmpty()) out.displayName = out.id;
  return out.id.isEmpty() ? BackendError::Api : BackendError::None;
}
