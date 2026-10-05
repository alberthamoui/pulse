#include "profiles.h"

#include <ArduinoJson.h>
#include <LittleFS.h>
#include <sys/stat.h>

#include <algorithm>
#include <cmath>

#include "config.h"
#include "spotify_client.h"

namespace {

constexpr char PROFILE_DIR[] = "/p";
constexpr char FORMAT_TAG[] = "PULSE3";
constexpr int HEADER_LINES = 4;  // format, snapshot, name and total

String profilePath(const String& id) { return String(PROFILE_DIR) + "/" + id + ".txt"; }

// LittleFS.exists() logs an error when the file doesn't exist; stat() doesn't
bool fileExists(const String& path) {
  struct stat st;
  return stat((String("/littlefs") + path).c_str(), &st) == 0;
}

// Names go on a single line of the profile
String cleanName(String s) {
  s.replace('\r', ' ');
  s.replace('\n', ' ');
  return s;
}

String readLine(File& f) {
  String line = f.readStringUntil('\n');
  line.trim();  // println writes "\r\n"
  return line;
}

bool idEquals(const char* s, size_t len, const String& id) {
  return len == id.length() && strncmp(s, id.c_str(), len) == 0;
}

// Calls fn(line, length) for each "x ..." line after the first skip lines,
// until the end or until fn returns false. Reads in blocks, much faster than
// readStringUntil. Lines longer than the buffer are truncated.
template <typename Fn>
void forEachLine(File& f, int skip, Fn fn) {
  char buf[256];
  char line[160];
  size_t len = 0;
  int lineNo = 0;
  int n;
  while ((n = f.read(reinterpret_cast<uint8_t*>(buf), sizeof(buf))) > 0) {
    for (int i = 0; i < n; ++i) {
      const char c = buf[i];
      if (c == '\r') continue;
      if (c != '\n') {
        if (len < sizeof(line) - 1) line[len++] = c;
        continue;
      }
      line[len] = '\0';
      const size_t lineLen = len;
      len = 0;
      if (++lineNo <= skip || lineLen < 3 || line[1] != ' ') continue;
      if (!fn(line, lineLen)) return;
    }
  }
}

// Walks the profile: how many tracks are by artistId and whether trackId is already in the playlist.
void scanProfile(File& f, const String& artistId, const String& trackId, uint32_t& count,
                 bool& hasTrack) {
  count = 0;
  hasTrack = false;
  forEachLine(f, HEADER_LINES, [&](const char* line, size_t len) {
    const char* id = line + 2;
    if (line[0] == 'a' && count == 0) {
      const char* sep = strchr(id, ' ');
      if (sep != nullptr && idEquals(id, sep - id, artistId)) {
        count = strtoul(sep + 1, nullptr, 10);
      }
    } else if (line[0] == 't' && idEquals(id, len - 2, trackId)) {
      hasTrack = true;
      return false;  // the "t" lines come after the "a" ones: nothing left to look for
    }
    return true;
  });
}

// Walks the "a <id> <n> <name>" lines: counts[j] gets the tracks of the
// similar artist j in the playlist.
void scanSimilar(File& f, const std::vector<SimilarArtist>& similar,
                 std::vector<uint16_t>& counts) {
  counts.assign(similar.size(), 0);
  forEachLine(f, HEADER_LINES, [&](const char* line, size_t) {
    if (line[0] != 'a') return false;  // the "t" lines started
    const char* sep = strchr(line + 2, ' ');
    if (sep == nullptr) return true;
    char* name = nullptr;
    const unsigned long n = strtoul(sep + 1, &name, 10);
    if (name == nullptr || *name != ' ') return true;
    ++name;
    for (size_t j = 0; j < similar.size(); ++j) {
      if (strcasecmp(name, similar[j].name.c_str()) == 0) counts[j] += n;
    }
    return true;
  });
}

// Copies the "t" lines from src (skipping the first skip lines) to dst.
void copyTrackLines(File& src, int skip, File& dst) {
  forEachLine(src, skip, [&](const char* line, size_t) {
    if (line[0] == 't') dst.println(line);
    return true;
  });
}

}  // namespace

bool selectCandidates(std::vector<Candidate>& ranked, size_t maxCount) {
  std::vector<Candidate> matches;
  for (const Candidate& c : ranked) {
    if (c.weight > 0.0f) matches.push_back(c);
  }

  if (matches.empty()) {
    std::sort(ranked.begin(), ranked.end(), [](const Candidate& a, const Candidate& b) {
      return strcasecmp(a.name.c_str(), b.name.c_str()) < 0;
    });
    return false;
  }

  std::stable_sort(matches.begin(), matches.end(),
                   [](const Candidate& a, const Candidate& b) { return a.weight > b.weight; });
  if (matches.size() > maxCount) matches.resize(maxCount);
  ranked = std::move(matches);
  return true;
}

void Profiles::begin() {
  if (!fileExists(PROFILE_DIR)) LittleFS.mkdir(PROFILE_DIR);

  File dir = LittleFS.open(PROFILE_DIR);
  for (File f = dir.openNextFile(); f; f = dir.openNextFile()) {
    const String name = f.name();
    f.close();
    if (!name.endsWith(".txt")) continue;
    Playlist p;
    if (readHeader(name.substring(0, name.length() - 4), p)) playlists_.push_back(std::move(p));
  }
  dir.close();
  Serial.printf("[profiles] %u playlists in the cache\n", static_cast<unsigned>(playlists_.size()));
}

bool Profiles::readHeader(const String& id, Playlist& p) const {
  const String path = profilePath(id);
  if (!fileExists(path)) return false;
  File f = LittleFS.open(path, "r");
  if (!f) return false;
  const bool current = readLine(f) == FORMAT_TAG;
  p.id = id;
  p.snapshot = readLine(f);
  p.name = readLine(f);
  p.total = readLine(f).toInt();
  f.close();
  return current && !p.snapshot.isEmpty();
}

bool Profiles::load(const String& id, Playlist& p, Counts& counts) const {
  if (!readHeader(id, p)) return false;
  File f = LittleFS.open(profilePath(id), "r");
  if (!f) return false;
  for (int i = 0; i < HEADER_LINES; ++i) readLine(f);
  while (f.available()) {
    const String line = readLine(f);
    if (line.startsWith("a ")) {
      const int sep = line.indexOf(' ', 2);
      if (sep <= 2) continue;
      const int nameSep = line.indexOf(' ', sep + 1);
      ArtistCount& a = counts[line.substring(2, sep)];
      a.n = line.substring(sep + 1, nameSep < 0 ? line.length() : nameSep).toInt();
      if (nameSep > 0) a.name = line.substring(nameSep + 1);
    } else if (line.startsWith("t ")) {
      break;  // the "t" lines come after the "a" ones
    }
  }
  f.close();
  return true;
}

bool Profiles::write(const Playlist& p, const Counts& counts,
                     const std::function<void(File&)>& writeTracks) const {
  // Writes to a temp file and renames: a power cut doesn't leave a half-written profile
  const String path = profilePath(p.id);
  const String tmp = String(PROFILE_DIR) + "/" + p.id + ".tmp";
  File f = LittleFS.open(tmp, "w");
  if (!f) return false;
  f.println(FORMAT_TAG);
  f.println(p.snapshot);
  f.println(p.name);
  f.println(p.total);
  for (const auto& [artist, a] : counts) {
    f.print("a ");
    f.print(artist);
    f.print(' ');
    f.print(a.n);
    f.print(' ');
    f.println(a.name);
  }
  writeTracks(f);
  f.close();
  if (fileExists(path)) LittleFS.remove(path);
  return LittleFS.rename(tmp, path);
}

BackendError Profiles::fetchPlaylists(std::vector<Playlist>& out) {
  JsonDocument filter;
  filter["next"] = true;
  JsonObject item = filter["items"].add<JsonObject>();
  item["id"] = true;
  item["name"] = true;
  item["snapshot_id"] = true;
  item["collaborative"] = true;
  item["owner"]["id"] = true;
  item["items"]["total"] = true;   // Feb/2026: "tracks" became "items"
  item["tracks"]["total"] = true;  // old name, as a fallback

  JsonDocument doc;
  for (uint32_t offset = 0;; offset += cfg::PAGE_LIMIT) {
    int status = 0;
    const String url =
        "/me/playlists?limit=" + String(cfg::PAGE_LIMIT) + "&offset=" + String(offset);
    const BackendError err = client_.call("GET", url, "", filter, doc, status);
    if (err != BackendError::None) return err;

    for (JsonObjectConst p : doc["items"].as<JsonArrayConst>()) {
      const bool mine = userId_ == (p["owner"]["id"] | "");
      const bool collaborative = p["collaborative"] | false;
      if (!mine && !collaborative) continue;

      Playlist pl;
      pl.id = p["id"] | "";
      pl.name = cleanName(p["name"] | "");
      pl.snapshot = p["snapshot_id"] | "";
      pl.apiTotal = p["items"]["total"] | (p["tracks"]["total"] | 0);
      // The API sometimes repeats a playlist in the listing
      const bool duplicate = std::any_of(out.begin(), out.end(),
                                         [&](const Playlist& o) { return o.id == pl.id; });
      if (!pl.id.isEmpty() && !duplicate) out.push_back(std::move(pl));
    }
    if (doc["next"].isNull()) break;
  }
  return BackendError::None;
}

BackendError Profiles::build(Playlist& p, uint32_t& done, uint32_t toFetch,
                             const ProgressFn& progress, int& status) {
  Serial.printf("[profiles] reading '%s' (%u tracks)\n", p.name.c_str(), p.apiTotal);

  // The track IDs go straight to a file: hundreds of Strings in RAM fragment
  // the heap and the TLS handshake for the next pages fails
  const String tracksPath = String(PROFILE_DIR) + "/" + p.id + ".trk";
  File tracks = LittleFS.open(tracksPath, "w");
  if (!tracks) return BackendError::Api;

  Counts counts;
  uint32_t total = 0;
  JsonDocument filter;
  JsonDocument doc;
  uint32_t offset = 0;
  BackendError err = BackendError::None;

  while (true) {
    // Feb/2026: the track comes in "item"; "track" is kept as a fallback
    const char* field = useTrackField_ ? "track" : "item";
    filter.clear();
    filter["next"] = true;
    filter["items"][0][field]["id"] = true;
    filter["items"][0][field]["artists"][0]["id"] = true;
    filter["items"][0][field]["artists"][0]["name"] = true;
    const String url = "/playlists/" + p.id + "/items?limit=" + String(cfg::PAGE_LIMIT) +
                       "&offset=" + String(offset) + "&fields=next,items(" + field +
                       "(id,artists(id,name)))";

    err = client_.call("GET", url, "", filter, doc, status);
    if (err == BackendError::Api && status == 400 && !useTrackField_) {
      Serial.println("[profiles] the API rejected fields with 'item'; using 'track'");
      useTrackField_ = true;
      continue;
    }
    if (err != BackendError::None) break;

    JsonArrayConst items = doc["items"];
    size_t withField = 0;
    for (JsonObjectConst it : items) {
      JsonObjectConst track = it[field];
      if (track.isNull()) continue;
      ++withField;
      const char* trackId = track["id"];
      if (trackId != nullptr && *trackId != '\0') {
        tracks.print("t ");
        tracks.println(trackId);
      }
      JsonObjectConst artist = track["artists"][0];
      const char* artistId = artist["id"];
      if (artistId == nullptr || *artistId == '\0') continue;  // local track, episode or unavailable
      ArtistCount& a = counts[artistId];
      if (a.n++ == 0) a.name = cleanName(artist["name"] | "");
      ++total;
    }

    // If the API ignores the requested field, the tracks come back empty: try the other name
    if (offset == 0 && items.size() > 0 && withField == 0 && !useTrackField_) {
      Serial.println("[profiles] tracks without 'item' in the response; using 'track'");
      useTrackField_ = true;
      continue;
    }

    done += items.size();
    if (toFetch > 0) progress(std::min<uint32_t>(99, done * 100 / toFetch));
    if (doc["next"].isNull()) break;
    offset += cfg::PAGE_LIMIT;
  }

  tracks.close();
  if (err == BackendError::None) {
    p.total = total;
    tracks = LittleFS.open(tracksPath, "r");
    const bool saved = tracks && write(p, counts, [&](File& f) {
      copyTrackLines(tracks, 0, f);
      tracks.close();
    });
    if (!saved) {
      Serial.printf("[profiles] failed to save '%s'\n", p.name.c_str());
      err = BackendError::Api;
    }
  }
  LittleFS.remove(tracksPath);
  if (err != BackendError::None) return err;

  Serial.printf("[profiles] '%s': %u tracks, %u artists\n", p.name.c_str(), total,
                static_cast<unsigned>(counts.size()));
  return BackendError::None;
}

void Profiles::removeStale() const {
  std::vector<String> stale;
  File dir = LittleFS.open(PROFILE_DIR);
  for (File f = dir.openNextFile(); f; f = dir.openNextFile()) {
    const String name = f.name();
    f.close();
    const String id = name.substring(0, name.lastIndexOf('.'));
    const bool known =
        name.endsWith(".txt") &&
        std::any_of(playlists_.begin(), playlists_.end(),
                    [&](const Playlist& p) { return p.id == id; });
    if (!known) stale.push_back(String(PROFILE_DIR) + "/" + name);
  }
  dir.close();

  for (const String& path : stale) {
    LittleFS.remove(path);
    Serial.printf("[profiles] removed %s\n", path.c_str());
  }
}

BackendError Profiles::sync(bool force, const ProgressFn& progress) {
  const uint32_t start = millis();
  progress(0);

  if (userId_.isEmpty()) {
    SpotifyUser me;
    const BackendError err = client_.getMe(me);
    if (err != BackendError::None) return err;
    userId_ = me.id;
  }

  std::vector<Playlist> fresh;
  BackendError err = fetchPlaylists(fresh);
  if (err != BackendError::None) return err;

  // Only rebuilds what changed: the snapshot_id changes on every playlist edit
  std::vector<bool> rebuild(fresh.size(), false);
  uint32_t toFetch = 0;
  size_t toRebuild = 0;
  for (size_t i = 0; i < fresh.size(); ++i) {
    Playlist cached;
    if (!force && readHeader(fresh[i].id, cached) && cached.snapshot == fresh[i].snapshot) {
      fresh[i].total = cached.total;
    } else {
      rebuild[i] = true;
      toFetch += fresh[i].apiTotal;
      ++toRebuild;
    }
  }
  Serial.printf("[profiles] %u playlists, %u to rebuild (%u tracks)\n",
                static_cast<unsigned>(fresh.size()), static_cast<unsigned>(toRebuild), toFetch);

  // Keeps the old profile (if any) of a playlist that failed; since the saved
  // snapshot is still the old one, it's rebuilt on the next sync
  std::vector<Playlist> kept;
  auto keepOld = [&](const Playlist& p) {
    Playlist cached;
    if (readHeader(p.id, cached)) {
      cached.name = p.name;
      kept.push_back(std::move(cached));
    }
  };

  client_.setMaxRetryAfter(cfg::SYNC_MAX_RETRY_AFTER_S);
  uint32_t done = 0;
  size_t rebuilt = 0;
  for (size_t i = 0; i < fresh.size(); ++i) {
    if (!rebuild[i]) {
      kept.push_back(fresh[i]);
      continue;
    }
    if (err != BackendError::None) {  // sync interrupted: only reuses what already exists
      keepOld(fresh[i]);
      continue;
    }

    int status = 0;
    const BackendError buildErr = build(fresh[i], done, toFetch, progress, status);
    if (buildErr == BackendError::None) {
      kept.push_back(fresh[i]);
      ++rebuilt;
    } else if (status == 403) {
      Serial.printf("[profiles] no access to '%s', skipped\n", fresh[i].name.c_str());
    } else if (buildErr == BackendError::RateLimited || buildErr == BackendError::NoWifi ||
               buildErr == BackendError::AuthExpired) {
      Serial.println("[profiles] sync interrupted");
      err = buildErr;
      keepOld(fresh[i]);
    } else {
      Serial.printf("[profiles] failed on '%s', keeping the previous profile\n",
                    fresh[i].name.c_str());
      keepOld(fresh[i]);
    }
  }
  client_.setMaxRetryAfter(cfg::MAX_RETRY_AFTER_S);

  playlists_ = std::move(kept);
  removeStale();
  progress(100);
  Serial.printf("[profiles] %u playlists ready, %u rebuilt, in %.1fs\n",
                static_cast<unsigned>(playlists_.size()), static_cast<unsigned>(rebuilt),
                (millis() - start) / 1000.0f);
  return err;
}

void Profiles::weights(const NowPlaying& track, std::vector<Candidate>& out) const {
  out.clear();
  out.reserve(playlists_.size());
  for (const Playlist& p : playlists_) {
    Candidate c;
    c.playlistId = p.id;
    c.name = p.name;
    const String path = profilePath(p.id);
    File f;
    if (fileExists(path)) f = LittleFS.open(path, "r");
    if (f) {
      uint32_t count = 0;
      scanProfile(f, track.artistId, track.trackId, count, c.hasTrack);
      f.close();
      if (p.total > 0) c.weight = static_cast<float>(count) / p.total;
    }
    out.push_back(std::move(c));
  }
}

void Profiles::recordAdd(const String& playlistId, const NowPlaying& track,
                         const String& snapshot) {
  auto entry = std::find_if(playlists_.begin(), playlists_.end(),
                            [&](const Playlist& p) { return p.id == playlistId; });
  if (entry == playlists_.end()) return;

  Playlist p;
  Counts counts;
  if (!load(playlistId, p, counts)) return;  // no profile: the next sync rebuilds it

  if (!track.artistId.isEmpty()) {
    ArtistCount& a = counts[track.artistId];
    if (a.n++ == 0) a.name = cleanName(track.artistName);
    ++p.total;
  }
  p.name = entry->name;
  // Without a new snapshot, the old one stays and the next sync rebuilds the playlist
  if (!snapshot.isEmpty()) p.snapshot = snapshot;

  File old = LittleFS.open(profilePath(playlistId), "r");
  if (!old) return;
  // Closes the old profile before write() replaces it with the new one
  const bool saved = write(p, counts, [&](File& f) {
    copyTrackLines(old, HEADER_LINES, f);
    old.close();
    f.print("t ");
    f.println(track.trackId);
  });
  if (!saved) {
    Serial.printf("[profiles] failed to update '%s'\n", p.name.c_str());
    return;
  }
  entry->total = p.total;
  entry->snapshot = p.snapshot;
  Serial.printf("[profiles] '%s' updated: %u tracks\n", p.name.c_str(), p.total);
}

void Profiles::similarWeights(const std::vector<SimilarArtist>& similar,
                              std::vector<Candidate>& out) const {
  struct Hit {
    size_t playlist;
    size_t artist;
    uint16_t n;
  };
  std::vector<Hit> hits;
  std::vector<uint16_t> df(similar.size(), 0);  // how many playlists each artist appears in
  std::vector<uint16_t> counts;

  for (size_t i = 0; i < playlists_.size(); ++i) {
    const String path = profilePath(playlists_[i].id);
    if (!fileExists(path)) continue;
    File f = LittleFS.open(path, "r");
    if (!f) continue;
    scanSimilar(f, similar, counts);
    f.close();
    for (size_t j = 0; j < similar.size(); ++j) {
      if (counts[j] == 0) continue;
      ++df[j];
      hits.push_back({i, j, counts[j]});
    }
  }

  // hits come out in playlist order and, within each, from the most to the least similar artist
  const float total = playlists_.size();
  std::vector<float> scores(playlists_.size(), 0.0f);
  for (const Hit& h : hits) {
    const Playlist& p = playlists_[h.playlist];
    if (p.total == 0) continue;
    const float tf = static_cast<float>(h.n) / p.total;
    const float idf = logf(total / df[h.artist]);
    scores[h.playlist] += similar[h.artist].match * tf * idf;
  }

  for (size_t i = 0; i < playlists_.size(); ++i) {
    if (scores[i] <= 0.0f) continue;
    String via;
    uint8_t shown = 0;
    for (const Hit& h : hits) {
      if (h.playlist != i || shown == 3) continue;
      if (shown++ > 0) via += ", ";
      via += similar[h.artist].name + " (" + String(similar[h.artist].match, 2) + ")";
    }
    Serial.printf("[lastfm] '%s': %.2f%% via %s\n", playlists_[i].name.c_str(),
                  scores[i] * 100.0f, via.c_str());
  }

  for (Candidate& c : out) {
    auto p = std::find_if(playlists_.begin(), playlists_.end(),
                          [&](const Playlist& pl) { return pl.id == c.playlistId; });
    if (p == playlists_.end()) continue;
    c.weight = scores[p - playlists_.begin()];
    c.similar = true;
  }
}
