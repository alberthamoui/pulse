#pragma once

#include <Arduino.h>
#include <FS.h>

#include <functional>
#include <map>
#include <vector>

#include "backend.h"
#include "lastfm.h"

class SpotifyClient;

// Takes every playlist of the user, each with its weight, and leaves in ranked
// only what goes on the screen:
// - up to maxCount playlists with weight > 0, from highest to lowest;
// - if none has a weight, every playlist in alphabetical order (manual choice).
// Returns true if there was a match.
bool selectCandidates(std::vector<Candidate>& ranked, size_t maxCount);

// Playlist profiles by relative artist frequency, stored on LittleFS, one file
// per playlist at /p/<id>.txt:
//   line 1: PULSE3 (format version; any other version is rebuilt)
//   line 2: snapshot_id
//   line 3: name
//   line 4: total tracks counted
//   rest:   "a <artist_id> <n> <name>", counting only the main artist
//           (artists[0]), and "t <track_id>", to know whether the song is
//           already in the playlist. The name links Last.fm artists to the IDs.
// Only the user's own playlists and the collaborative ones are included.
class Profiles {
 public:
  explicit Profiles(SpotifyClient& client) : client_(client) {}

  // Mount LittleFS first. Loads the saved index, so it works without network.
  void begin();

  void setUserId(const String& id) { userId_ = id; }

  // Lists the playlists and rebuilds the profiles whose snapshot_id changed
  // (or all of them, with force). Deletes the files of playlists that are gone.
  BackendError sync(bool force, const ProgressFn& progress);

  // Every playlist with the weight of the song's artist (0 if it doesn't
  // appear) and whether the song is already in it.
  void weights(const NowPlaying& track, std::vector<Candidate>& out) const;

  // Replaces the weight of the playlists in out with the score of the similar
  // artists: sum of match * tf * idf of each similar artist in the playlist,
  // with idf = ln(N / df). Same formula as the Python lastfm_fallback, but with
  // tf = n / total, without Laplace smoothing, so the values differ a little.
  // Artists are matched by name, case-insensitive.
  void similarWeights(const std::vector<SimilarArtist>& similar,
                      std::vector<Candidate>& out) const;

  // Updates the profile after adding the song, with the new snapshot_id, so the
  // next sync doesn't rebuild the playlist.
  void recordAdd(const String& playlistId, const NowPlaying& track, const String& snapshot);

 private:
  struct Playlist {
    String id;
    String name;
    String snapshot;
    uint32_t total = 0;     // tracks counted in the profile
    uint32_t apiTotal = 0;  // tracks according to /me/playlists (for the progress)
  };
  struct ArtistCount {
    uint16_t n = 0;
    String name;
  };
  using Counts = std::map<String, ArtistCount>;  // artist_id -> n and name

  BackendError fetchPlaylists(std::vector<Playlist>& out);
  // Reads the tracks and writes the profile. Adds the tracks read to done.
  BackendError build(Playlist& p, uint32_t& done, uint32_t toFetch, const ProgressFn& progress,
                     int& status);
  bool readHeader(const String& id, Playlist& p) const;
  // Reads the header and the "a" lines (the tracks stay in the file).
  bool load(const String& id, Playlist& p, Counts& counts) const;
  // Writes the header and the "a" lines; writeTracks writes the "t" lines.
  bool write(const Playlist& p, const Counts& counts,
             const std::function<void(File&)>& writeTracks) const;
  void removeStale() const;

  SpotifyClient& client_;
  String userId_;
  std::vector<Playlist> playlists_;
  bool useTrackField_ = false;  // fallback if the API rejects "item" in fields
};
