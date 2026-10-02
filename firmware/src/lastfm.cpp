#include "lastfm.h"

#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>

#include "certs.h"
#include "config.h"
#include "secrets.h"
#include "spotify_client.h"

namespace {

constexpr char API_URL[] = "https://ws.audioscrobbler.com/2.0/";

}  // namespace

bool lastFmEnabled() { return secrets::LASTFM_API_KEY[0] != '\0'; }

bool fetchSimilarArtists(const String& artist, std::vector<SimilarArtist>& out) {
  out.clear();
  if (!lastFmEnabled() || artist.isEmpty() || WiFi.status() != WL_CONNECTED) return false;

  WiFiClientSecure tls;
#ifdef PULSE_INSECURE_TLS
  tls.setInsecure();
#else
  tls.setCACert(LASTFM_ROOT_CAS);
#endif
  static_cast<Stream&>(tls).setTimeout(cfg::HTTP_TIMEOUT_MS);  // ver SpotifyClient::begin()

  HTTPClient http;
  http.useHTTP10(true);  // sem chunked: o getStream() não decodifica chunked
  http.setTimeout(cfg::HTTP_TIMEOUT_MS);
  http.setUserAgent("Pulse/1.0");
  // A URL leva a chave da API: não vai para o log
  const String url = String(API_URL) + "?method=artist.getsimilar&format=json&limit=" +
                     String(cfg::LASTFM_SIMILAR_LIMIT) + "&artist=" + urlEncode(artist) +
                     "&api_key=" + secrets::LASTFM_API_KEY;
  if (!http.begin(tls, url)) return false;

  const int status = http.GET();
  if (status != 200) {
    if (status > 0) {
      // Os erros do Last.fm são JSONs curtos ({"error":10,"message":"Invalid API key"})
      Serial.printf("[lastfm] HTTP %d %s\n", status, http.getString().c_str());
    } else {
      Serial.printf("[lastfm] %s\n", HTTPClient::errorToString(status).c_str());
    }
    http.end();
    return false;
  }

  // A resposta tem ~40 KB, quase tudo URLs de imagens: o filtro guarda só nome e match
  JsonDocument filter;
  filter["error"] = true;
  filter["message"] = true;
  JsonObject item = filter["similarartists"]["artist"].add<JsonObject>();
  item["name"] = true;
  item["match"] = true;

  JsonDocument doc;
  const DeserializationError jsonErr =
      deserializeJson(doc, http.getStream(), DeserializationOption::Filter(filter));
  http.end();
  if (jsonErr) {
    Serial.printf("[lastfm] JSON invalido: %s\n", jsonErr.c_str());
    return false;
  }
  if (!doc["error"].isNull()) {
    Serial.printf("[lastfm] erro %d: %s\n", doc["error"].as<int>(), doc["message"] | "");
    return false;
  }

  for (JsonObjectConst a : doc["similarartists"]["artist"].as<JsonArrayConst>()) {
    SimilarArtist s;
    s.name = a["name"] | "";
    // O Last.fm manda o match como texto ("0.906903")
    s.match = a["match"].is<const char*>() ? atof(a["match"].as<const char*>())
                                           : a["match"].as<float>();
    if (!s.name.isEmpty() && s.match > 0.0f) out.push_back(std::move(s));
  }
  Serial.printf("[lastfm] %u artistas parecidos com %s\n", static_cast<unsigned>(out.size()),
                artist.c_str());
  return !out.empty();
}
