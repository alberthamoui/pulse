#pragma once

#include <map>
#include <vector>

#include "backend.h"

// Backend com dados falsos para testar a interface sem Wi-Fi (etapa 1).
// Cada vez que o IDLE é disparado, avança para o próximo cenário:
//   1. artista em 3 playlists
//   2. artista em 9 playlists (mostra só as 5 melhores)
//   3. artista desconhecido, com nomes longos (escolha manual entre todas)
//   4. nada tocando
//   5. sem Wi-Fi
// O ranking usa a mesma regra do firmware real (peso = n / total).
class FakeBackend : public Backend {
 public:
  FakeBackend();

  BackendError fetchNowPlaying(NowPlaying& out, const ProgressFn& progress) override;
  bool rank(const String& artistId, std::vector<Candidate>& out) override;
  BackendError addTrack(const NowPlaying& track, const Candidate& playlist,
                        const ProgressFn& progress) override;
  BackendError resyncAll(const ProgressFn& progress) override;

 private:
  struct Profile {
    String id;
    String name;
    uint16_t total = 0;
    std::map<String, uint16_t> counts;  // artist_id -> n
  };

  std::vector<Profile> profiles_;
  size_t scenario_ = 0;
};
