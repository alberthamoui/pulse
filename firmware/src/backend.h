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

// Opção da tela de escolha: uma playlist candidata (weight = n / total do
// artista na playlist), a playlist de fallback ou cancelar.
struct Candidate {
  enum class Kind : uint8_t { Playlist, Fallback, Cancel };

  String playlistId;
  String name;
  float weight = 0.0f;
  bool hasTrack = false;  // a música já está nessa playlist
  Kind kind = Kind::Playlist;
};

enum class BackendError : uint8_t {
  None,
  NoWifi,
  NothingPlaying,
  LocalFile,     // arquivo local: sem ID no catálogo, a API não adiciona
  NoPlaylists,
  RateLimited,
  AuthExpired,   // refresh token revogado ou expirado (vale 180 dias)
  Api,
};

// Recebe o progresso de 0 a 100 durante as operações de rede (bloqueantes).
using ProgressFn = std::function<void(uint8_t pct)>;

// Tudo que a máquina de estados precisa do Spotify.
class Backend {
 public:
  virtual ~Backend() = default;

  virtual BackendError fetchNowPlaying(NowPlaying& out, const ProgressFn& progress) = 0;

  // Preenche out com as playlists ordenadas pelo peso do artista da música (no
  // máximo cfg::MAX_SUGGESTIONS com peso > 0). Se o artista não estiver em
  // nenhuma, devolve todas as playlists para escolha manual e retorna false.
  // Inclui também as opções de fallback e de cancelar.
  virtual bool rank(const NowPlaying& track, std::vector<Candidate>& out) = 0;

  virtual BackendError addTrack(const NowPlaying& track, const Candidate& playlist,
                                const ProgressFn& progress) = 0;

  // Reconstrói os perfis de todas as playlists, ignorando o snapshot_id.
  virtual BackendError resyncAll(const ProgressFn& progress) = 0;
};

// Mensagem de erro para o display: linha principal e detalhe (pode ser vazio).
const char* errorMessage(BackendError err);
const char* errorDetail(BackendError err);
