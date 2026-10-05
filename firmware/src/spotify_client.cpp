#include "spotify_client.h"

#include <HTTPClient.h>
#include <LittleFS.h>
#include <WiFi.h>
#include <sys/stat.h>

#include "certs.h"
#include "config.h"

#if !__has_include("secrets.h")
#error "Crie include/secrets.h a partir de include/secrets.example.h"
#endif
#include "secrets.h"

namespace {

constexpr char API_BASE[] = "https://api.spotify.com/v1";
constexpr char TOKEN_URL[] = "https://accounts.spotify.com/api/token";

// Linha 1: o refresh token do secrets.h que originou o salvo. Linha 2: o atual.
// Se o secrets.h mudar (nova autorização), o arquivo salvo é ignorado.
constexpr char AUTH_FILE[] = "/auth.txt";
constexpr char AUTH_TMP[] = "/auth.tmp";

// Erro de transporte (status < 0): sem Wi-Fi ou falha de conexão/TLS.
BackendError transportError() {
  return WiFi.status() == WL_CONNECTED ? BackendError::Api : BackendError::NoWifi;
}

void logHttpError(const char* tag, const char* what, HTTPClient& http, int status) {
  if (status > 0) {
    // Os corpos de erro do Spotify são JSONs curtos, sem segredos
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
  // O WiFiClientSecure tem um _timeout próprio que esconde o do Stream, então o
  // setTimeout() do HTTPClient não chega no readBytes() usado pelo ArduinoJson,
  // que fica no padrão de 1 s e corta respostas grandes no meio.
  static_cast<Stream&>(tls_).setTimeout(cfg::HTTP_TIMEOUT_MS);
  loadRefreshToken();
}

void SpotifyClient::loadRefreshToken() {
  refreshToken_ = secrets::SPOTIFY_REFRESH_TOKEN;

  // LittleFS.exists() loga um erro quando o arquivo não existe; stat() não
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
    Serial.println("[auth] usando o refresh token salvo no LittleFS");
  }
}

void SpotifyClient::saveRefreshToken(const String& token) {
  // O refresh token pode mudar a cada renovação, e o anterior pode deixar de valer:
  // grava num temporário e renomeia, para uma queda de energia não perder o token
  File f = LittleFS.open(AUTH_TMP, "w");
  if (!f) {
    Serial.println("[auth] falha ao salvar o refresh token");
    return;
  }
  f.println(secrets::SPOTIFY_REFRESH_TOKEN);
  f.println(token);
  f.close();
  // O LittleFS substitui o destino no rename; se esta versão recusar, remove antes
  if (!LittleFS.rename(AUTH_TMP, AUTH_FILE)) {
    LittleFS.remove(AUTH_FILE);
    if (!LittleFS.rename(AUTH_TMP, AUTH_FILE)) {
      Serial.println("[auth] falha ao salvar o refresh token");
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
  http.useHTTP10(true);  // sem chunked: o getStream() não decodifica chunked
  http.setTimeout(cfg::HTTP_TIMEOUT_MS);
  if (!http.begin(tls_, TOKEN_URL)) return BackendError::Api;
  http.addHeader("Content-Type", "application/x-www-form-urlencoded");

  // PKCE: o aparelho não guarda o client secret, só o client id vai no corpo
  const int status = http.POST("grant_type=refresh_token&refresh_token=" +
                               urlEncode(refreshToken_) +
                               "&client_id=" + urlEncode(secrets::SPOTIFY_CLIENT_ID));
  if (status <= 0) {
    logHttpError("auth", "falha ao renovar o token", http, status);
    http.end();
    return transportError();
  }
  if (status != 200) {
    // 400 invalid_grant: refresh token expirado, revogado ou gerado sem PKCE.
    // invalid_client: client id errado. Nos dois casos a saída é autorizar de novo.
    const String body = http.getString();
    http.end();
    Serial.printf("[auth] falha ao renovar o token: HTTP %d %s\n", status, body.c_str());
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
    Serial.printf("[auth] resposta do token invalida: %s\n", jsonErr.c_str());
    return BackendError::Api;
  }

  accessToken_ = doc["access_token"] | "";
  if (accessToken_.isEmpty()) {
    Serial.println("[auth] resposta do token sem access_token");
    return BackendError::Api;
  }
  const uint32_t expiresIn = doc["expires_in"] | 3600;
  expiresAt_ = millis() + expiresIn * 1000UL;
  Serial.printf("[auth] access token renovado (expira em %us)\n", expiresIn);

  // A renovação pode devolver um refresh token novo, que passa a ser o válido
  const char* rotated = doc["refresh_token"];
  if (rotated != nullptr && refreshToken_ != rotated) {
    refreshToken_ = rotated;
    saveRefreshToken(refreshToken_);
    Serial.println("[auth] refresh token novo salvo no LittleFS");
  }
  return BackendError::None;
}

BackendError SpotifyClient::call(const char* method, const String& url, const String& body,
                                 const JsonDocument& filter, JsonDocument& out, int& status) {
  // O Bearer token só vai para a API do Spotify: URL completa só se for de lá
  const String apiPrefix = String(API_BASE) + "/";
  if (url.startsWith("https://") && !url.startsWith(apiPrefix)) {
    Serial.printf("[api] URL fora da API do Spotify recusada: %s\n", url.c_str());
    return BackendError::Api;
  }
  const String fullUrl = url.startsWith("https://") ? url : String(API_BASE) + url;
  bool retriedAfter401 = false;
  status = 0;
  // Só o GET é repetido depois de falha de rede: um POST pode ter chegado ao
  // Spotify antes da conexão cair, e repetir duplicaria a música na playlist
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
      Serial.println("[api] 401: renovando o token e repetindo");
      retriedAfter401 = true;
      accessToken_ = "";  // força a renovação no próximo ensureToken()
      continue;
    }

    if (status == 429) {
      uint32_t wait = http.header("Retry-After").toInt();
      http.end();
      if (wait == 0) wait = 1;
      if (wait > maxRetryAfterS_) {
        Serial.printf("[api] 429: Retry-After de %us, desistindo\n", wait);
        return BackendError::RateLimited;
      }
      Serial.printf("[api] 429: aguardando %us\n", wait);
      delay(wait * 1000UL);
      continue;
    }

    // Falha de conexão (TLS ou rede): costuma passar na tentativa seguinte. A
    // memória livre no log mostra se o TLS ficou sem heap para o handshake.
    if (status < 0 && canRetry) {
      http.end();
      Serial.printf("[api] %s %s: %s (heap livre %u, maior bloco %u), repetindo\n", method,
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
    if (status == 204) {  // sem corpo (ex.: nada tocando)
      http.end();
      return BackendError::None;
    }
    const DeserializationError jsonErr =
        deserializeJson(out, http.getStream(), DeserializationOption::Filter(filter));
    http.end();
    // IncompleteInput: a conexão caiu no meio da resposta
    if (jsonErr == DeserializationError::IncompleteInput && canRetry) {
      Serial.printf("[api] %s %s: resposta cortada, repetindo\n", method, url.c_str());
      delay(500);
      continue;
    }
    if (jsonErr) {
      Serial.printf("[api] %s %s: JSON invalido (%s)\n", method, url.c_str(), jsonErr.c_str());
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
