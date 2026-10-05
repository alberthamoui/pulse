#pragma once

#include "backend.h"

class Profiles;
class SpotifyClient;

// Real backend: current song, ranking from the profiles and adding to a playlist.
class SpotifyBackend : public Backend {
 public:
  SpotifyBackend(SpotifyClient& client, Profiles& profiles)
      : client_(client), profiles_(profiles) {}

  BackendError fetchNowPlaying(NowPlaying& out, const ProgressFn& progress) override;
  bool rank(const NowPlaying& track, std::vector<Candidate>& out,
            const ProgressFn& progress) override;
  BackendError addTrack(const NowPlaying& track, const Candidate& playlist,
                        const ProgressFn& progress) override;
  BackendError resyncAll(const ProgressFn& progress) override;

 private:
  SpotifyClient& client_;
  Profiles& profiles_;
};
