#pragma once

#include <Arduino.h>
#include <FS.h>

#include <functional>
#include <map>
#include <vector>

#include "backend.h"
#include "lastfm.h"

class SpotifyClient;

// Recebe todas as playlists do usuário, cada uma com o seu peso, e deixa em
// ranked só o que vai para a tela:
// - até maxCount playlists com peso > 0, do maior para o menor;
// - se nenhuma tiver peso, todas as playlists em ordem alfabética (escolha manual).
// Retorna true se houve match.
bool selectCandidates(std::vector<Candidate>& ranked, size_t maxCount);

// Perfis das playlists por frequência relativa de artistas, persistidos no
// LittleFS, um arquivo por playlist em /p/<id>.txt:
//   linha 1: PULSE3 (versão do formato; outra versão é reconstruída)
//   linha 2: snapshot_id
//   linha 3: nome
//   linha 4: total de faixas contadas
//   demais:  "a <artist_id> <n> <nome>", contando só o artista principal
//            (artists[0]), e "t <track_id>", para saber se a música já está
//            na playlist. O nome liga os artistas do Last.fm aos IDs.
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

  // Todas as playlists com o peso do artista da música (0 se ele não aparece)
  // e se a música já está nela.
  void weights(const NowPlaying& track, std::vector<Candidate>& out) const;

  // Troca o peso das playlists em out pelo score dos artistas parecidos, como
  // o lastfm_fallback do Python: soma de match * tf * idf de cada artista
  // parecido presente na playlist, com tf = n / total e idf = ln(N / df).
  // Os artistas são casados pelo nome, sem diferenciar maiúsculas.
  void similarWeights(const std::vector<SimilarArtist>& similar,
                      std::vector<Candidate>& out) const;

  // Atualiza o perfil depois de adicionar a música, com o snapshot_id novo, para
  // o próximo sync não reconstruir a playlist.
  void recordAdd(const String& playlistId, const NowPlaying& track, const String& snapshot);

  size_t size() const { return playlists_.size(); }

 private:
  struct Playlist {
    String id;
    String name;
    String snapshot;
    uint32_t total = 0;     // faixas contadas no perfil
    uint32_t apiTotal = 0;  // faixas segundo /me/playlists (para o progresso)
  };
  struct ArtistCount {
    uint16_t n = 0;
    String name;
  };
  using Counts = std::map<String, ArtistCount>;  // artist_id -> n e nome

  BackendError fetchPlaylists(std::vector<Playlist>& out);
  // Lê as faixas e grava o perfil. Soma em done as faixas lidas.
  BackendError build(Playlist& p, uint32_t& done, uint32_t toFetch, const ProgressFn& progress,
                     int& status);
  bool readHeader(const String& id, Playlist& p) const;
  // Lê o cabeçalho e as linhas "a" (as faixas ficam no arquivo).
  bool load(const String& id, Playlist& p, Counts& counts) const;
  // Grava o cabeçalho e as linhas "a"; writeTracks escreve as linhas "t".
  bool write(const Playlist& p, const Counts& counts,
             const std::function<void(File&)>& writeTracks) const;
  void removeStale() const;

  SpotifyClient& client_;
  String userId_;
  std::vector<Playlist> playlists_;
  bool useTrackField_ = false;  // fallback se a API recusar "item" no fields
};
