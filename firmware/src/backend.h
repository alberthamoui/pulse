#pragma once

// Types shared by the state machine, the display and the Spotify backend.

#include <Arduino.h>

#include <functional>
#include <vector>

// Song playing on Spotify (only the main artist, artists[0], is ranked).
struct NowPlaying {
  String trackId;
  String name;
  String artistId;
  String artistName;
};

// Option on the choice screen: a candidate playlist, the fallback playlist or
// cancel. A playlist's weight is n / total of the artist in the playlist or, if
// similar, the score of the similar artists according to Last.fm.
struct Candidate {
  enum class Kind : uint8_t { Playlist, Fallback, Cancel };

  String playlistId;
  String name;
  float weight = 0.0f;
  bool hasTrack = false;  // the song is already in this playlist
  bool similar = false;   // weight came from Last.fm, not from the artist itself
  Kind kind = Kind::Playlist;
};

enum class BackendError : uint8_t {
  None,
  NoWifi,
  NothingPlaying,
  LocalFile,     // local file: no catalog ID, the API can't add it
  NoPlaylists,
  RateLimited,
  AuthExpired,   // refresh token revoked or expired
  Api,
};

// Gets the progress from 0 to 100 during the (blocking) network operations.
using ProgressFn = std::function<void(uint8_t pct)>;

// Error message for the display: main line and detail (may be empty).
const char* errorMessage(BackendError err);
const char* errorDetail(BackendError err);
