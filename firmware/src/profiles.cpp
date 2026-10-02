#include "profiles.h"

#include <ArduinoJson.h>
#include <LittleFS.h>
#include <sys/stat.h>

#include <algorithm>

#include "config.h"
#include "spotify_client.h"

namespace {

constexpr char PROFILE_DIR[] = "/p";
constexpr char FORMAT_TAG[] = "PULSE2";
constexpr int HEADER_LINES = 4;  // formato, snapshot, nome e total

String profilePath(const String& id) { return String(PROFILE_DIR) + "/" + id + ".txt"; }

// LittleFS.exists() loga um erro quando o arquivo não existe; stat() não
bool fileExists(const String& path) {
  struct stat st;
  return stat((String("/littlefs") + path).c_str(), &st) == 0;
}

String readLine(File& f) {
  String line = f.readStringUntil('\n');
  line.trim();  // println grava "\r\n"
  return line;
}

bool idEquals(const char* s, size_t len, const String& id) {
  return len == id.length() && strncmp(s, id.c_str(), len) == 0;
}

// Percorre o perfil depois do cabeçalho: quantas faixas são de artistId e se
// trackId já está na playlist. Lê em blocos, bem mais rápido que readStringUntil.
void scanProfile(File& f, const String& artistId, const String& trackId, uint32_t& count,
                 bool& hasTrack) {
  count = 0;
  hasTrack = false;
  char buf[256];
  char line[64];
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
      if (++lineNo <= HEADER_LINES || lineLen < 3 || line[1] != ' ') continue;

      const char* id = line + 2;
      if (line[0] == 'a' && count == 0) {
        const char* sep = strchr(id, ' ');
        if (sep != nullptr && idEquals(id, sep - id, artistId)) {
          count = strtoul(sep + 1, nullptr, 10);
        }
      } else if (line[0] == 't' && idEquals(id, lineLen - 2, trackId)) {
        hasTrack = true;
        return;  // as linhas "t" vêm depois das "a": nada mais a procurar
      }
    }
  }
}

}  // namespace

bool selectCandidates(std::vector<Candidate>& ranked) {
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
  if (matches.size() > cfg::MAX_SUGGESTIONS) matches.resize(cfg::MAX_SUGGESTIONS);
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
  Serial.printf("[perfis] %u playlists no cache\n", static_cast<unsigned>(playlists_.size()));
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

bool Profiles::load(const String& id, Playlist& p, Counts& counts,
                    std::vector<String>& tracks) const {
  if (!readHeader(id, p)) return false;
  File f = LittleFS.open(profilePath(id), "r");
  if (!f) return false;
  for (int i = 0; i < HEADER_LINES; ++i) readLine(f);
  while (f.available()) {
    const String line = readLine(f);
    if (line.startsWith("a ")) {
      const int sep = line.indexOf(' ', 2);
      if (sep > 2) counts[line.substring(2, sep)] = line.substring(sep + 1).toInt();
    } else if (line.startsWith("t ")) {
      tracks.push_back(line.substring(2));
    }
  }
  f.close();
  return true;
}

bool Profiles::write(const Playlist& p, const Counts& counts,
                     const std::vector<String>& tracks) const {
  // Grava num temporário e renomeia: uma queda de energia não deixa perfil pela metade
  const String path = profilePath(p.id);
  const String tmp = String(PROFILE_DIR) + "/" + p.id + ".tmp";
  File f = LittleFS.open(tmp, "w");
  if (!f) return false;
  f.println(FORMAT_TAG);
  f.println(p.snapshot);
  f.println(p.name);
  f.println(p.total);
  for (const auto& [artist, n] : counts) {
    f.print("a ");
    f.print(artist);
    f.print(' ');
    f.println(n);
  }
  for (const String& track : tracks) {
    f.print("t ");
    f.println(track);
  }
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
  item["items"]["total"] = true;   // fev/2026: "tracks" virou "items"
  item["tracks"]["total"] = true;  // nome antigo, de fallback

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
      pl.name = p["name"] | "";
      pl.name.replace('\n', ' ');
      pl.snapshot = p["snapshot_id"] | "";
      pl.apiTotal = p["items"]["total"] | (p["tracks"]["total"] | 0);
      // A API às vezes repete uma playlist na listagem
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
  Serial.printf("[perfis] lendo '%s' (%u faixas)\n", p.name.c_str(), p.apiTotal);

  Counts counts;
  std::vector<String> tracks;
  uint32_t total = 0;
  JsonDocument filter;
  JsonDocument doc;
  uint32_t offset = 0;

  while (true) {
    // fev/2026: a faixa vem em "item"; "track" fica de fallback
    const char* field = useTrackField_ ? "track" : "item";
    filter.clear();
    filter["next"] = true;
    filter["items"][0][field]["id"] = true;
    filter["items"][0][field]["artists"][0]["id"] = true;
    const String url = "/playlists/" + p.id + "/items?limit=" + String(cfg::PAGE_LIMIT) +
                       "&offset=" + String(offset) + "&fields=next,items(" + field +
                       "(id,artists(id)))";

    const BackendError err = client_.call("GET", url, "", filter, doc, status);
    if (err == BackendError::Api && status == 400 && !useTrackField_) {
      Serial.println("[perfis] a API recusou fields com 'item'; usando 'track'");
      useTrackField_ = true;
      continue;
    }
    if (err != BackendError::None) return err;

    JsonArrayConst items = doc["items"];
    size_t withField = 0;
    for (JsonObjectConst it : items) {
      JsonObjectConst track = it[field];
      if (track.isNull()) continue;
      ++withField;
      const char* trackId = track["id"];
      if (trackId != nullptr && *trackId != '\0') tracks.push_back(trackId);
      const char* artist = track["artists"][0]["id"];
      if (artist == nullptr || *artist == '\0') continue;  // faixa local, episódio ou indisponível
      ++counts[artist];
      ++total;
    }

    // Se a API ignorar o campo pedido, as faixas voltam vazias: tenta o outro nome
    if (offset == 0 && items.size() > 0 && withField == 0 && !useTrackField_) {
      Serial.println("[perfis] faixas sem 'item' na resposta; usando 'track'");
      useTrackField_ = true;
      continue;
    }

    done += items.size();
    if (toFetch > 0) progress(std::min<uint32_t>(99, done * 100 / toFetch));
    if (doc["next"].isNull()) break;
    offset += cfg::PAGE_LIMIT;
  }

  p.total = total;
  if (!write(p, counts, tracks)) {
    Serial.printf("[perfis] falha ao salvar '%s'\n", p.name.c_str());
    return BackendError::Api;
  }
  Serial.printf("[perfis] '%s': %u faixas, %u artistas\n", p.name.c_str(), total,
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
    Serial.printf("[perfis] removido %s\n", path.c_str());
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

  // Só reconstrói o que mudou: o snapshot_id muda a cada alteração na playlist
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
  Serial.printf("[perfis] %u playlists, %u para reconstruir (%u faixas)\n",
                static_cast<unsigned>(fresh.size()), static_cast<unsigned>(toRebuild), toFetch);

  // Mantém o perfil antigo (se houver) de uma playlist que falhou; como o
  // snapshot salvo continua o antigo, ela é reconstruída no próximo sync
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
    if (err != BackendError::None) {  // sync interrompido: só aproveita o que já existe
      keepOld(fresh[i]);
      continue;
    }

    int status = 0;
    const BackendError buildErr = build(fresh[i], done, toFetch, progress, status);
    if (buildErr == BackendError::None) {
      kept.push_back(fresh[i]);
      ++rebuilt;
    } else if (status == 403) {
      Serial.printf("[perfis] sem acesso a '%s', ignorada\n", fresh[i].name.c_str());
    } else if (buildErr == BackendError::RateLimited || buildErr == BackendError::NoWifi ||
               buildErr == BackendError::AuthExpired) {
      Serial.println("[perfis] sync interrompido");
      err = buildErr;
      keepOld(fresh[i]);
    } else {
      Serial.printf("[perfis] falha em '%s', mantendo o perfil anterior\n",
                    fresh[i].name.c_str());
      keepOld(fresh[i]);
    }
  }
  client_.setMaxRetryAfter(cfg::MAX_RETRY_AFTER_S);

  playlists_ = std::move(kept);
  removeStale();
  progress(100);
  Serial.printf("[perfis] %u playlists prontas, %u reconstruidas, em %.1fs\n",
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
  std::vector<String> tracks;
  if (!load(playlistId, p, counts, tracks)) return;  // sem perfil: o próximo sync reconstrói

  if (!track.artistId.isEmpty()) {
    ++counts[track.artistId];
    ++p.total;
  }
  tracks.push_back(track.trackId);
  p.name = entry->name;
  // Sem snapshot novo, fica o antigo e o próximo sync reconstrói a playlist
  if (!snapshot.isEmpty()) p.snapshot = snapshot;

  if (!write(p, counts, tracks)) {
    Serial.printf("[perfis] falha ao atualizar '%s'\n", p.name.c_str());
    return;
  }
  entry->total = p.total;
  entry->snapshot = p.snapshot;
  Serial.printf("[perfis] '%s' atualizada: %u faixas\n", p.name.c_str(), p.total);
}
