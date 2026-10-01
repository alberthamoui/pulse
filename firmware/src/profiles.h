#pragma once

#include <Arduino.h>

#include <vector>

#include "backend.h"

class SpotifyClient;

// Recebe todas as playlists do usuário, cada uma com o peso (n / total) do
// artista da música tocando, e deixa em ranked só o que vai para a tela:
// - até cfg::MAX_SUGGESTIONS playlists com peso > 0, do maior para o menor;
// - se nenhuma tiver peso, todas as playlists em ordem alfabética (escolha manual).
// Retorna true se houve match.
bool selectCandidates(std::vector<Candidate>& ranked);

// Perfis das playlists por frequência relativa de artistas, persistidos no
// LittleFS, um arquivo por playlist em /p/<id>.txt:
//   linha 1: snapshot_id
//   linha 2: nome
//   linha 3: total de faixas contadas
//   demais:  "<artist_id> <n>", contando só o artista principal (artists[0])
// Só entram as playlists do usuário e as colaborativas.
class Profiles {
 public:
  explicit Profiles(SpotifyClient& client) : client_(client) {}

  // Monta o LittleFS antes. Carrega o índice salvo, para funcionar sem rede.
  void begin();

  void setUserId(const String& id) { userId_ = id; }

  // Lista as playlists e reconstrói os perfis cujo snapshot_id mudou
  // (ou todos, com force). Apaga os arquivos das playlists que sumiram.
  BackendError sync(bool force, const ProgressFn& progress);

  // Todas as playlists com o peso de artistId (0 se ele não aparece).
  void weights(const String& artistId, std::vector<Candidate>& out) const;

  size_t size() const { return playlists_.size(); }

 private:
  struct Playlist {
    String id;
    String name;
    String snapshot;
    uint32_t total = 0;      // faixas contadas no perfil
    uint32_t apiTotal = 0;   // faixas segundo /me/playlists (para o progresso)
  };

  BackendError fetchPlaylists(std::vector<Playlist>& out);
  // Lê as faixas e grava o perfil. Soma em done as faixas lidas.
  BackendError build(Playlist& p, uint32_t& done, uint32_t toFetch, const ProgressFn& progress,
                     int& status);
  bool readHeader(const String& id, Playlist& p) const;
  void removeStale() const;

  SpotifyClient& client_;
  String userId_;
  std::vector<Playlist> playlists_;
  bool useTrackField_ = false;  // fallback se a API recusar "item" no fields
};
