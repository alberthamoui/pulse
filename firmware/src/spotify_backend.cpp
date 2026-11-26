#include "spotify_backend.h"

#include <ArduinoJson.h>

#include <algorithm>

#include "config.h"
#include "lastfm.h"
#include "profiles.h"
#include "secrets.h"
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

  // 204: nothing playing. A private session doesn't return the song either.
  JsonObjectConst track = doc["item"];
  if (status == 204 || track.isNull()) return BackendError::NothingPlaying;

  // Podcasts, audiobooks and ads aren't songs
  const char* type = doc["currently_playing_type"] | "track";
  if (strcmp(type, "track") != 0) return BackendError::NothingPlaying;

  out.name = track["name"] | "";
  out.artistName = track["artists"][0]["name"] | "";
  if (track["is_local"] | false) {
    Serial.printf("[spotify] local file: %s\n", out.name.c_str());
    return BackendError::LocalFile;
  }

  out.trackId = track["id"] | "";
  out.artistId = track["artists"][0]["id"] | "";
  if (out.trackId.isEmpty()) return BackendError::LocalFile;
  return BackendError::None;
}

bool SpotifyBackend::rank(const NowPlaying& track, std::vector<Candidate>& out,
                          const ProgressFn& progress) {
  profiles_.weights(track, out);

  // The fallback becomes a fixed option, so it leaves the regular list
  Candidate fallback;
  fallback.playlistId = secrets::FALLBACK_PLAYLIST_ID;
  fallback.name = "Fallback";
  fallback.kind = Candidate::Kind::Fallback;
  auto found = std::find_if(out.begin(), out.end(), [&](const Candidate& c) {
    return c.playlistId == fallback.playlistId;
  });
  if (found != out.end()) {
    fallback.hasTrack = found->hasTrack;
    out.erase(found);
  }

  Candidate cancel;
  cancel.name = "Cancel";
  cancel.kind = Candidate::Kind::Cancel;

  std::vector<Candidate> extras;
  if (!fallback.playlistId.isEmpty()) extras.push_back(fallback);
  extras.push_back(cancel);

  // Artist in no playlist: the suggestions come from similar artists
  size_t maxCount = cfg::MAX_SUGGESTIONS;
  const bool direct = std::any_of(out.begin(), out.end(),
                                  [](const Candidate& c) { return c.weight > 0.0f; });
  if (!direct && lastFmEnabled()) {
    Serial.printf("[lastfm] %s is in no playlist, looking up similar artists\n",
                  track.artistName.c_str());
    progress(80);
    std::vector<SimilarArtist> similar;
    if (fetchSimilarArtists(track.artistName, similar)) {
      progress(90);
      profiles_.similarWeights(similar, out);
      maxCount = cfg::LASTFM_SUGGESTIONS;
    }
  }

  // With a ranking, the best suggestion stays first. Without a match, the
  // fallback is the most likely destination, and Cancel isn't left at the end of a long list.
  const bool matched = selectCandidates(out, maxCount);
  out.insert(matched ? out.end() : out.begin(), extras.begin(), extras.end());
  return matched;
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
