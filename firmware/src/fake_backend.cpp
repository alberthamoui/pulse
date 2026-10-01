#include "fake_backend.h"

#include "profiles.h"

namespace {

// Simula uma chamada de rede de durationMs, avançando a barra de fromPct a toPct.
void simulate(const ProgressFn& progress, uint32_t durationMs, uint8_t fromPct, uint8_t toPct) {
  constexpr int STEPS = 10;
  for (int i = 1; i <= STEPS; ++i) {
    delay(durationMs / STEPS);
    progress(fromPct + (toPct - fromPct) * i / STEPS);
  }
}

}  // namespace

FakeBackend::FakeBackend() {
  auto add = [this](const char* id, const char* name, uint16_t total,
                    std::map<String, uint16_t> counts) {
    Profile p;
    p.id = id;
    p.name = name;
    p.total = total;
    p.counts = std::move(counts);
    profiles_.push_back(std::move(p));
  };

  add("fake01", "Indie da tarde", 40, {{"tame", 6}, {"arctic", 4}, {"radiohead", 2}});
  add("fake02", "Psicodelia", 25, {{"tame", 8}, {"radiohead", 1}});
  add("fake03", "Rock alternativo", 60, {{"arctic", 10}, {"radiohead", 5}});
  add("fake04", "Músicas pra dirigir à noite na estrada vazia", 30,
      {{"tame", 2}, {"radiohead", 3}});
  add("fake05", "Foco", 50, {{"radiohead", 4}});
  add("fake06", "Chuva", 20, {{"radiohead", 6}});
  add("fake07", "Anos 2000", 80, {{"radiohead", 2}, {"arctic", 7}});
  add("fake08", "Treino", 45, {});
  add("fake09", "Domingo de manhã", 15, {{"radiohead", 1}});
  add("fake10", "Clássicos que meu pai ouvia no carro", 70, {{"radiohead", 3}});
}

BackendError FakeBackend::fetchNowPlaying(NowPlaying& out, const ProgressFn& progress) {
  const size_t scenario = scenario_;
  scenario_ = (scenario_ + 1) % 5;

  if (scenario == 4) {
    simulate(progress, 300, 0, 20);
    return BackendError::NoWifi;
  }

  simulate(progress, 900, 0, 80);
  switch (scenario) {
    case 0:
      out = {"t1", "The Less I Know The Better", "tame", "Tame Impala"};
      break;
    case 1:
      out = {"t2", "Weird Fishes/Arpeggi", "radiohead", "Radiohead"};
      break;
    case 2:
      out = {"t3", "Uma música com um nome bem comprido para testar o scroll", "novo",
             "Artista Que Ninguém Conhece Ainda"};
      break;
    default:
      return BackendError::NothingPlaying;
  }
  return BackendError::None;
}

bool FakeBackend::rank(const String& artistId, std::vector<Candidate>& out) {
  out.clear();
  for (const Profile& p : profiles_) {
    Candidate c;
    c.playlistId = p.id;
    c.name = p.name;
    const auto it = p.counts.find(artistId);
    if (it != p.counts.end() && p.total > 0) {
      c.weight = static_cast<float>(it->second) / p.total;
    }
    out.push_back(c);
  }
  return selectCandidates(out);
}

BackendError FakeBackend::addTrack(const NowPlaying& track, const Candidate& playlist,
                                   const ProgressFn& progress) {
  Serial.printf("[fake] POST /playlists/%s/items spotify:track:%s\n", playlist.playlistId.c_str(),
                track.trackId.c_str());
  simulate(progress, 700, 0, 100);
  return BackendError::None;
}

BackendError FakeBackend::resyncAll(const ProgressFn& progress) {
  for (size_t i = 0; i < profiles_.size(); ++i) {
    Serial.printf("[fake] sync %u/%u %s\n", static_cast<unsigned>(i + 1),
                  static_cast<unsigned>(profiles_.size()), profiles_[i].name.c_str());
    delay(250);
    progress((i + 1) * 100 / profiles_.size());
  }
  return BackendError::None;
}
