#pragma once

#include "backend.h"

class Profiles;
class SpotifyClient;

// Everything the state machine needs from Spotify: the current song, the
// ranking from the profiles and adding to a playlist.
class SpotifyBackend {
 public:
  SpotifyBackend(SpotifyClient& client, Profiles& profiles)
      : client_(client), profiles_(profiles) {}

  BackendError fetchNowPlaying(NowPlaying& out, const ProgressFn& progress);

  // Fills out with the playlists sorted by the weight of the song's artist (at
  // most cfg::MAX_SUGGESTIONS with weight > 0). If the artist isn't in any of
  // them, tries the similar artists from Last.fm (at most
  // cfg::LASTFM_SUGGESTIONS); if there's still no match, returns every
  // playlist for a manual choice and returns false. Also adds the fallback
  // and cancel options.
  bool rank(const NowPlaying& track, std::vector<Candidate>& out, const ProgressFn& progress);

  BackendError addTrack(const NowPlaying& track, const Candidate& playlist,
                        const ProgressFn& progress);

  // Rebuilds the profiles of every playlist, ignoring the snapshot_id.
  BackendError resyncAll(const ProgressFn& progress);

 private:
  SpotifyClient& client_;
  Profiles& profiles_;
};
