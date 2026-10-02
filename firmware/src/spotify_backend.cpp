#include "spotify_backend.h"

#include <ArduinoJson.h>

#include "profiles.h"
#include "spotify_client.h"

BackendError SpotifyBackend::fetchNowPlaying(NowPlaying& out, const ProgressFn& progress) {
  JsonDocument filter;
  filter["currently_playing_type"] = true;
  JsonObject item = filter["item"].to<JsonObject>();
  item["id"] = true;
  item["name"] = true;
  item["is_local"] = true;
  item["artists"][0]["id"] = true;
  item["artists"][0]["name"] = true;

  progress(20);
  JsonDocument doc;
  int status = 0;
  const BackendError err =
      client_.call("GET", "/me/player/currently-playing", "", filter, doc, status);
  progress(70);
  if (err != BackendError::None) return err;

  // 204: nada tocando. Sessão privada também não devolve a música.
  JsonObjectConst track = doc["item"];
  if (status == 204 || track.isNull()) return BackendError::NothingPlaying;

  // Podcast, audiobook e anúncio não são músicas
  const char* type = doc["currently_playing_type"] | "track";
  if (strcmp(type, "track") != 0) return BackendError::NothingPlaying;

  out.name = track["name"] | "";
  out.artistName = track["artists"][0]["name"] | "";
  if (track["is_local"] | false) {
    Serial.printf("[spotify] arquivo local: %s\n", out.name.c_str());
    return BackendError::LocalFile;
  }

  out.trackId = track["id"] | "";
  out.artistId = track["artists"][0]["id"] | "";
  if (out.trackId.isEmpty()) return BackendError::LocalFile;
  return BackendError::None;
}

bool SpotifyBackend::rank(const NowPlaying& track, std::vector<Candidate>& out) {
  profiles_.weights(track, out);
  return selectCandidates(out);
}

BackendError SpotifyBackend::addTrack(const NowPlaying& track, const Candidate& playlist,
                                      const ProgressFn& progress) {
  JsonDocument body;
  body["uris"][0] = "spotify:track:" + track.trackId;
  String payload;
  serializeJson(body, payload);

  JsonDocument filter;
  filter["snapshot_id"] = true;
  JsonDocument doc;
  int status = 0;

  progress(20);
  const BackendError err = client_.call("POST", "/playlists/" + playlist.playlistId + "/items",
                                        payload, filter, doc, status);
  progress(80);
  if (err != BackendError::None) return err;

  profiles_.recordAdd(playlist.playlistId, track, doc["snapshot_id"] | "");
  progress(100);
  return BackendError::None;
}

BackendError SpotifyBackend::resyncAll(const ProgressFn& progress) {
  return profiles_.sync(true, progress);
}
