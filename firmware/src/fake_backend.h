#pragma once

#include "backend.h"

class Profiles;

// Backend da etapa 3: playlists, perfis e ranking reais; música tocando e
// "adicionar" ainda falsos (viram reais na etapa 4).
// Cada vez que o IDLE é disparado, avança para o próximo cenário:
//   1. Tame Impala (ID real do Spotify)
//   2. Radiohead (ID real do Spotify)
//   3. artista que não existe, com nomes longos (escolha manual entre todas)
//   4. nada tocando
//   5. sem Wi-Fi
class FakeBackend : public Backend {
 public:
  explicit FakeBackend(Profiles& profiles) : profiles_(profiles) {}

  BackendError fetchNowPlaying(NowPlaying& out, const ProgressFn& progress) override;
  bool rank(const String& artistId, std::vector<Candidate>& out) override;
  BackendError addTrack(const NowPlaying& track, const Candidate& playlist,
                        const ProgressFn& progress) override;
  BackendError resyncAll(const ProgressFn& progress) override;

 private:
  Profiles& profiles_;
  size_t scenario_ = 0;
};
