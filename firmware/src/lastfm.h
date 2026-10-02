#pragma once

#include <Arduino.h>

#include <vector>

// Artista parecido segundo o Last.fm, com a similaridade de 0 a 1.
struct SimilarArtist {
  String name;
  float match = 0.0f;
};

// true se há LASTFM_API_KEY no secrets.h.
bool lastFmEnabled();

// artist.getSimilar: até cfg::LASTFM_SIMILAR_LIMIT artistas parecidos com
// artist, do mais para o menos parecido. Qualquer falha (sem rede, chave
// inválida, artista desconhecido) só deixa out vazio: o Last.fm é um extra.
bool fetchSimilarArtists(const String& artist, std::vector<SimilarArtist>& out);
