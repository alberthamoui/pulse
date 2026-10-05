#pragma once

#include <Arduino.h>

#include <vector>

// Similar artist according to Last.fm, with the similarity from 0 to 1.
struct SimilarArtist {
  String name;
  float match = 0.0f;
};

// true if secrets.h has a LASTFM_API_KEY.
bool lastFmEnabled();

// artist.getSimilar: up to cfg::LASTFM_SIMILAR_LIMIT artists similar to
// artist, from most to least similar. Any failure (no network, invalid key,
// unknown artist) just leaves out empty: Last.fm is an extra.
bool fetchSimilarArtists(const String& artist, std::vector<SimilarArtist>& out);
