#pragma once

#include <Arduino.h>

#include <functional>
#include <vector>

// Música tocando no Spotify (só o artista principal, artists[0], entra no ranking).
struct NowPlaying {
  String trackId;
  String name;
  String artistId;
  String artistName;
};

// Playlist candidata a receber a música. weight = n / total do artista na playlist.
struct Candidate {
  String playlistId;
  String name;
  float weight = 0.0f;
};

enum class BackendError : uint8_t {
  None,
  NoWifi,
  NothingPlaying,
  NoPlaylists,
  RateLimited,
  Api,
};

// Recebe o progresso de 0 a 100 durante as operações de rede (bloqueantes).
using ProgressFn = std::function<void(uint8_t pct)>;

// Tudo que a máquina de estados precisa do Spotify. A etapa 1 usa FakeBackend.
class Backend {
 public:
  virtual ~Backend() = default;

  virtual BackendError fetchNowPlaying(NowPlaying& out, const ProgressFn& progress) = 0;

  // Preenche out com as playlists ordenadas pelo peso do artista (no máximo
  // cfg::MAX_SUGGESTIONS com peso > 0). Se o artista não estiver em nenhuma,
  // devolve todas as playlists para escolha manual e retorna false.
  virtual bool rank(const String& artistId, std::vector<Candidate>& out) = 0;

  virtual BackendError addTrack(const NowPlaying& track, const Candidate& playlist,
                                const ProgressFn& progress) = 0;

  // Reconstrói os perfis de todas as playlists, ignorando o snapshot_id.
  virtual BackendError resyncAll(const ProgressFn& progress) = 0;
};

const char* errorMessage(BackendError err);
