#include "profiles.h"

#include <ArduinoJson.h>
#include <LittleFS.h>
#include <sys/stat.h>

#include <algorithm>
#include <map>

#include "config.h"
#include "spotify_client.h"

namespace {

constexpr char PROFILE_DIR[] = "/p";

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

// Procura a linha "<artistId> <n>" depois do cabeçalho e devolve n (0 se não
// achar). Lê em blocos: bem mais rápido que readStringUntil por linha.
uint32_t countFor(File& f, const String& artistId) {
  char buf[256];
  char line[64];
  size_t len = 0;
  int lineNo = 0;
  int n;
  while ((n = f.read(reinterpret_cast<uint8_t*>(buf), sizeof(buf))) > 0) {
    for (int i = 0; i < n; ++i) {
      if (buf[i] != '\n') {
        if (len < sizeof(line) - 1) line[len++] = buf[i];
        continue;
      }
      line[len] = '\0';
      len = 0;
      if (++lineNo <= 3) continue;  // snapshot, nome e total
      const char* sep = strchr(line, ' ');
      if (sep != nullptr && static_cast<size_t>(sep - line) == artistId.length() &&
          strncmp(line, artistId.c_str(), sep - line) == 0) {
        return strtoul(sep + 1, nullptr, 10);
      }
    }
  }
  return 0;
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
  p.id = id;
  p.snapshot = readLine(f);
  p.name = readLine(f);
  p.total = readLine(f).toInt();
  f.close();
  return !p.snapshot.isEmpty();
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

  std::map<String, uint16_t> counts;
  uint32_t total = 0;
  JsonDocument filter;
  JsonDocument doc;
  uint32_t offset = 0;

  while (true) {
    // fev/2026: a faixa vem em "item"; "track" fica de fallback
    const char* field = useTrackField_ ? "track" : "item";
    filter.clear();
    filter["next"] = true;
    filter["items"][0][field]["artists"][0]["id"] = true;
    const String url = "/playlists/" + p.id + "/items?limit=" + String(cfg::PAGE_LIMIT) +
                       "&offset=" + String(offset) + "&fields=next,items(" + field +
                       "(artists(id)))";

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
      if (!it[field].isNull()) ++withField;
      const char* artist = it[field]["artists"][0]["id"];
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

  // Grava num temporário e renomeia: uma queda de energia não deixa perfil pela metade
  const String path = profilePath(p.id);
  const String tmp = String(PROFILE_DIR) + "/" + p.id + ".tmp";
  File f = LittleFS.open(tmp, "w");
  if (!f) {
    Serial.printf("[perfis] falha ao gravar '%s'\n", p.name.c_str());
    return BackendError::Api;
  }
  f.println(p.snapshot);
  f.println(p.name);
  f.println(total);
  for (const auto& [artist, n] : counts) {
    f.print(artist);
    f.print(' ');
    f.println(n);
  }
  f.close();
  if (fileExists(path)) LittleFS.remove(path);
  if (!LittleFS.rename(tmp, path)) {
    Serial.printf("[perfis] falha ao salvar '%s'\n", p.name.c_str());
    return BackendError::Api;
  }

  p.total = total;
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
    } else if (buildErr == BackendError::RateLimited || buildErr == BackendError::NoWifi) {
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

void Profiles::weights(const String& artistId, std::vector<Candidate>& out) const {
  out.clear();
  out.reserve(playlists_.size());
  for (const Playlist& p : playlists_) {
    Candidate c;
    c.playlistId = p.id;
    c.name = p.name;
    if (p.total > 0) {
      File f = LittleFS.open(profilePath(p.id), "r");
      if (f) {
        c.weight = static_cast<float>(countFor(f, artistId)) / p.total;
        f.close();
      }
    }
    out.push_back(std::move(c));
  }
}
