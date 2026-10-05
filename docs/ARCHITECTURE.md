# PULSE — Architecture

PULSE watches the song playing on Spotify and decides which of your playlists it should go to, using a scoring system based on a statistical analysis of how the user already curates their music.

---

## File Layout

```
pulse/
├── main.py                        # Main orchestrator
├── config/
│   ├── constants.py               # Algorithm parameters (versioned)
│   ├── settings.py                # Spotify + Last.fm credentials (local, kept out of git)
│   ├── config.json                # System configuration (local, kept out of git)
│   └── *.example.*                # Versioned templates for settings.py and config.json
├── src/
│   └── core/
│       ├── models.py              # Data classes
│       ├── client.py              # SpotifyManager (API client)
│       ├── playlist_analyzer.py   # Playlist analysis and profiling
│       ├── hybrid_matcher.py      # Main matching algorithm
│       ├── artist_frequency_matcher.py  # Simple alternative algorithm
│       ├── matcher_base.py        # Abstract matcher interface
│       ├── lastfm_client.py       # Last.fm client for the fallback
│       └── __init__.py
├── firmware/                      # Standalone ESP32 version (C++/PlatformIO), see firmware/README.md
├── tools/
│   └── get_refresh_token.py       # Generates the refresh token used by the firmware
├── tests/                         # Scoring and flow tests (pytest, no network)
└── docs/
    └── ARCHITECTURE.md
```

---

## Execution Flow

```
python main.py [--auto | --dry-run | --refresh | --cache-refresh]
        │
        ├─ 1. Connects to Spotify (OAuth through spotipy)
        │
        ├─ 2. Gets the current song (playing or paused)
        │       → if nothing is playing or it's a local file: stops
        │
        ├─ 3. Fetches the user's own playlists and the collaborative ones
        │
        ├─ 4. Syncs the cache (see the Cache section)
        │       → --refresh: rebuilds everything
        │       → normal: updates only playlists with a different snapshot_id
        │
        ├─ 5. Trains the HybridMatcher with the profiles
        │       → computes each artist's IDF
        │       → builds the co-occurrence index
        │       → builds the name → id lookup for Last.fm
        │
        ├─ 6. Duplicate warning
        │       → checks whether the song is already in some playlist (through the cache)
        │       → if so: asks whether to continue
        │         (--auto: doesn't add; --dry-run: only warns)
        │
        ├─ 7. Scoring and playlist selection
        │       → tries TF-IDF + co-occurrence
        │       → if everything scores 0 and Last.fm is set up: tries the Last.fm fallback
        │       → shows the top 3 candidates to the user
        │
        ├─ 8. The user confirms or picks another playlist (any algorithm)
        │       → --auto: adds without asking if score ≥ auto_add_min_score
        │       → --dry-run: shows the candidates and stops without adding
        │
        ├─ 9. Adds the song to the chosen playlist
        │
        └─10. Updates the cache locally (no extra API call)
```

---

## Spotify API Calls

| Scenario | Calls |
|---|---|
| Normal run with a valid cache | ~5 |
| Run with N changed playlists | ~5 + N × pages |
| `--refresh` (46 playlists) | ~101 |

The `spotify.api_calls` counter is shown at the end of each run. Every call is intercepted through a monkey-patch on `_internal_call` in `client.py`.

---

## Cache (`.pulse_cache.json`)

```json
{
  "version": 3,
  "algorithm": "hybrid",
  "cached_at": "2026-05-23T...",
  "snapshots": {
    "playlist_id": "current_snapshot_id"
  },
  "artist_names": {
    "artist_id": "Artist Name"
  },
  "profiles": {
    "playlist_id": {
      "id": "...",
      "name": "Playlist Name",
      "artist_weights": { "artist_id": 0.142 },
      "genre_weights": {},
      "total_tracks": 28,
      "track_ids": ["track_id_1", "track_id_2"],
      "artist_counts": { "artist_id": 4 }
    }
  }
}
```

**Smart invalidation:** on every run, each playlist's `snapshot_id` is compared with the cached one. Only the playlists that changed are analyzed again. Removed playlists are dropped from the cache. A cache with a different `version` (old format) is discarded and rebuilt.

**Update after adding:** after a song is added, `update_cache()` updates the cache locally:
- the playlist's `track_ids` gets the new track id and `total_tracks` goes up by 1
- `artist_counts` goes up by 1 for the artist, and `artist_weights` is recomputed from the raw counts (with the same Laplace smoothing as the build), with no API call
- `snapshot_id` is set to the value returned by the add endpoint

The file is written to a temp file and swapped in with `os.replace`, so an interruption halfway doesn't corrupt the cache.

---

## Scoring Algorithm (HybridMatcher)

### 1. Building the Profiles (build time)

For each playlist, `SpotifyPlaylistAnalyzer.build_artist_profile()` fetches every track with pagination and computes:

```
tf(artist, playlist) = (appearances + α) / (total_tracks + α × V)
```

Where `α = 1` (Laplace smoothing) and `V` = number of distinct artists in the playlist.

The smoothing keeps small playlists from dominating with inflated weights (e.g. 1 artist in 3 songs = 0.33 without smoothing → 0.25 with smoothing if V=3).

### 2. Training (train time)

`HybridMatcher.train()` computes two structures in memory:

**IDF per artist:**
```
idf(artist) = log(N / df)
```
Where `N` = total number of playlists and `df` = number of playlists that contain the artist.
Artists that show up in many playlists get a low IDF (they don't discriminate much).

**Co-occurrence index:**
```
artist_to_playlists = { artist_id: {pl_id_1, pl_id_2, ...} }
```
Used to compute the Jaccard between artists at match time.

### 3. Scoring per Playlist (match time)

For the song playing, with artist X:

**Direct score:**
```
tfidf(X, playlist) = tf(X, playlist) × idf(X)
```

**Indirect score through co-occurrence:**
```
indirect = Σ Jaccard(X, Y) × tf(Y, playlist) × idf(Y)
           for every artist Y in the playlist
```

Where `Jaccard(X, Y) = |playlists_with_X ∩ playlists_with_Y| / |playlists_with_X ∪ playlists_with_Y|`

The Jaccard is computed once per match and cached locally; there are no API calls.

**Final score:**
```
artist_score = tfidf + β × indirect     (β = 0.5)
final_score  = α × artist_score + (1-α) × genre_overlap    (α = 0.8)
```

`genre_overlap` is always 0 right now because the Spotify API genres endpoint returns 403.

### 4. Last.fm Fallback

Only kicks in when `final_score = 0` for every playlist (a completely unknown artist).

1. Calls `artist.getSimilar` on the Last.fm API: 1 external HTTP request
2. Looks up each similar artist returned in the `name → id` lookup built in `train()`
3. Playlists that contain similar artists get a score:
```
score_lastfm(playlist) = Σ match_lastfm(Y) × tf(Y, playlist) × idf(Y)
```

If Last.fm doesn't solve it either: the song goes to FALLBACK_PULSE.

---

## Components

### `models.py`
```python
Track            — id, name, artist, artist_id, artist_ids, artist_names
PlaylistProfile  — id, name, artist_weights, genre_weights, total_tracks, track_ids, artist_counts
MatchResult      — playlist_id, playlist_name, score, match_type, reason
```

### `client.py` — SpotifyManager
- `get_current_track()` → current Track
- `get_user_playlists()` → paginated list (the user's own playlists and the collaborative ones, as in the firmware)
- `get_artists_genres()` → batches of 50, silently returns `{}` if the endpoint is unavailable
- `add_track_to_playlist()` → returns the new `snapshot_id` (from the endpoint's response)
- `api_calls` counter through a monkey-patch on `_internal_call`

### `playlist_analyzer.py` — SpotifyPlaylistAnalyzer
- `fetch_tracks()` → `(List[Track], total)`, 100 tracks per request
- `build_artist_profile()` → `(artist_weights, total_tracks, track_ids, artist_names, artist_counts)`
- `smoothed_weights(counts)` → weights with Laplace smoothing; used in the build and in the update after adding
- `build_all_profiles()` → parallel with `ThreadPoolExecutor(max_workers=5)`, returns `(profiles, artist_names)`

### `hybrid_matcher.py` — HybridMatcher
Main algorithm. Implements TF-IDF + Laplace + co-occurrence + the Last.fm fallback.
- `train(profiles, artist_names)` → computes the IDF, the co-occurrence index and the name→id lookup
- `top_matches(track, n=3)` → top N with score > 0
- `lastfm_fallback(track, api_key)` → only used when top_matches comes back empty

### `lastfm_client.py`
- `get_similar_artists(artist_name, api_key)` → list of `{name, match}` through the stdlib `urllib`
- 5 s timeout, returns `[]` on any error

### `artist_frequency_matcher.py` — ArtistFrequencyMatcher
Simple alternative algorithm: score = relative frequency of the artist in the playlist.
Available through `config.json: "algorithm": "artist_frequency"`.

---

## Configuration

### `config/settings.py`
```python
SPOTIFY_CLIENT_ID     = "..."
SPOTIFY_CLIENT_SECRET = "..."
SPOTIFY_REDIRECT_URI  = "http://127.0.0.1:8080"
LASTFM_API_KEY        = "..."   # https://www.last.fm/api/account/create
```

### `config/config.json`
```json
{
  "algorithm": "hybrid",
  "fallback_playlist_id": "fallback_playlist_id",
  "cache_file": ".pulse_cache.json",
  "auto_add_min_score": 0.5
}
```

`auto_add_min_score` is the minimum score for `--auto` to add without asking (0.5 by default).

---

## Run Modes

```bash
python main.py                 # uses the cache, updates only what changed
python main.py --auto          # adds without asking if the score passes the minimum
python main.py --dry-run       # shows the candidates, adds nothing
python main.py --refresh       # forces every playlist to be analyzed again
python main.py --cache-refresh # only rebuilds the cache, without looking at the current song
```

In normal mode, it shows the top 3 candidate playlists with score and reason and asks for confirmation before adding (`[1-3]` playlists, `l` Liked Songs, `f` FALLBACK_PULSE, `n` cancel).

---

## Known Limitations

- **Genres unavailable:** the `GET /v1/artists` endpoint returns 403 for apps not approved by Spotify. `genre_weights` is always empty.
- **New artists without Last.fm:** if the artist isn't in any playlist AND Last.fm has no data or none of the similar artists are in the playlists, the menu has no suggestions and Enter picks FALLBACK_PULSE (with `--auto`, nothing is added).
- **Co-occurrence depends on your own history:** Jaccard only works for artists that already appear in at least one of the user's playlists.
