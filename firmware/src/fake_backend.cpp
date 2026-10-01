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

BackendError FakeBackend::fetchNowPlaying(NowPlaying& out, const ProgressFn& progress) {
  const size_t scenario = scenario_;
  scenario_ = (scenario_ + 1) % 5;

  if (scenario == 4) {
    simulate(progress, 300, 0, 20);
    return BackendError::NoWifi;
  }

  simulate(progress, 600, 0, 80);
  switch (scenario) {
    case 0:
      out = {"t1", "The Less I Know The Better", "5INjqkS1o8h1imAzPqGZBb", "Tame Impala"};
      break;
    case 1:
      out = {"t2", "Weird Fishes/Arpeggi", "4Z8W4fKeB5YxbusRsdQVPb", "Radiohead"};
      break;
    case 2:
      out = {"t3", "Uma música com um nome bem comprido para testar o scroll",
             "0000000000000000000000", "Artista Que Ninguém Conhece Ainda"};
      break;
    default:
      return BackendError::NothingPlaying;
  }
  return BackendError::None;
}

bool FakeBackend::rank(const String& artistId, std::vector<Candidate>& out) {
  profiles_.weights(artistId, out);
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
  return profiles_.sync(true, progress);
}
