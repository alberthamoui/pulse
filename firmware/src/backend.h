#pragma once

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

// Everything the state machine needs from Spotify.
class Backend {
 public:
  virtual ~Backend() = default;

  virtual BackendError fetchNowPlaying(NowPlaying& out, const ProgressFn& progress) = 0;

  // Fills out with the playlists sorted by the weight of the song's artist (at
  // most cfg::MAX_SUGGESTIONS with weight > 0). If the artist isn't in any of
  // them, tries the similar artists from Last.fm (at most
  // cfg::LASTFM_SUGGESTIONS); if there's still no match, returns every
  // playlist for a manual choice and returns false. Also adds the fallback
  // and cancel options.
  virtual bool rank(const NowPlaying& track, std::vector<Candidate>& out,
                    const ProgressFn& progress) = 0;

  virtual BackendError addTrack(const NowPlaying& track, const Candidate& playlist,
                                const ProgressFn& progress) = 0;

  // Rebuilds the profiles of every playlist, ignoring the snapshot_id.
  virtual BackendError resyncAll(const ProgressFn& progress) = 0;
};

// Error message for the display: main line and detail (may be empty).
const char* errorMessage(BackendError err);
const char* errorDetail(BackendError err);
