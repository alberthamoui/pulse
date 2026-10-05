# PULSE — Architecture

PULSE watches the song playing on Spotify and decides which of your playlists it should go to, using a scoring system based on a statistical analysis of how the user already curates their music.

This document covers the Python version in depth. The file layout is in the [README](../README.md#project-structure), and the ESP32 device is in [firmware/README.md](../firmware/README.md).

---

## Execution Flow

```
python main.py [--auto | --dry-run | --refresh | --cache-refresh]
        │
        ├─ 1. Loads the user's config (user_config)
        │       → missing or placeholder values: stops with a message saying what to fix
        │
        ├─ 2. Connects to Spotify (OAuth through spotipy) and gets the current song
        │       → no song, or a local file: stops
        │
        ├─ 3. Fetches the user's own playlists and the collaborative ones
        │
        ├─ 4. Syncs the cache (see the Cache section)
        │       → --refresh: rebuilds everything
        │       → normal: re-reads only playlists with a different snapshot_id
        │
        ├─ 5. Builds the PlaylistMatcher from the profiles
        │       → computes each artist's IDF and the co-occurrence index
        │       → builds the name → id lookup for Last.fm
        │
        ├─ 6. Ranks the playlists: TF-IDF + co-occurrence
        │       → if nothing scores and Last.fm is set up: tries the Last.fm fallback
        │
        ├─ 7. Duplicate warning
        │       → checks whether the song is already in some playlist (through the cache)
        │       → if so: asks whether to continue
        │         (--auto: doesn't add; --dry-run: only warns)
        │
        ├─ 8. The user picks a playlist from the top 3 (or Liked Songs, the fallback, or cancel)
        │       → --auto: adds the best one without asking if score ≥ auto_add_min_score
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

The `spotify.api_calls` counter is shown at the end of each run. Every call is intercepted through a monkey-patch on spotipy's `_internal_call` in `client.py`.

---

## Cache (`.pulse_cache.json`)

```json
{
  "version": 4,
  "cached_at": "2026-10-05T...",
  "snapshots": {
    "playlist_id": "snapshot_id the profile was built from"
  },
  "artist_names": {
    "artist_id": "Artist Name"
  },
  "profiles": {
    "playlist_id": {
      "id": "...",
      "name": "Playlist Name",
      "artist_counts": { "artist_id": 4 },
      "track_ids": ["track_id_1", "track_id_2"]
    }
  }
}
```

Only the raw `artist_counts` are stored: `PlaylistProfile` derives the smoothed `artist_weights` from them when it's loaded.

**Smart invalidation:** on every run, each playlist's `snapshot_id` is compared with the cached one. Only the playlists that changed are read again. Removed playlists are dropped from the cache. A cache with a different `version` (old format) is discarded and rebuilt.

**Failed reads are retried:** only a playlist that was actually read gets its new `snapshot_id`. One that failed (rate limit, network) keeps its old profile and old snapshot, so the next run reads it again.

**Update after adding:** after a song is added, `Cache.record_add()` updates the cache locally:
- the playlist's `track_ids` gets the new track id
- `artist_counts` goes up by 1 for the artist, and the weights are recomputed from the counts
- `snapshot_id` is set to the value returned by the add endpoint

The file is written to a temp file and swapped in with `os.replace`, so an interruption halfway doesn't corrupt the cache.

---

## Ranking (PlaylistMatcher)

### 1. Building the Profiles

For each playlist, `SpotifyPlaylistAnalyzer.build_profile()` fetches every track with pagination and counts the main artist of each one. `PlaylistProfile` turns the counts into a smoothed frequency:

```
tf(artist, playlist) = (appearances + α) / (tracks + α × V)
```

Where `α = 1` (Laplace smoothing) and `V` = number of distinct artists in the playlist.

The smoothing keeps small playlists from dominating with inflated weights (e.g. 1 artist in 3 songs = 0.33 without smoothing → 0.25 with smoothing if V=3).

### 2. Indexes

The `PlaylistMatcher` constructor computes two structures in memory:

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

### 3. Scoring per Playlist

For the song playing, with artist X:

**Direct score:**
```
direct(X, playlist) = tf(X, playlist) × idf(X)
```

**Indirect score through co-occurrence:**
```
indirect = Σ Jaccard(X, Y) × tf(Y, playlist) × idf(Y)
           for every other artist Y in the playlist
```

Where `Jaccard(X, Y) = |playlists_with_X ∩ playlists_with_Y| / |playlists_with_X ∪ playlists_with_Y|`

The Jaccard is computed once per artist per match and reused across playlists; there are no API calls.

**Final score:**
```
score = direct + β × indirect     (β = CO_OCCURRENCE_WEIGHT = 0.5)
```

The score isn't normalized: it's only meaningful relative to the other playlists.

### 4. Last.fm Fallback

Only kicks in when no playlist scores above 0 (an artist that isn't in any playlist).

1. Calls `artist.getSimilar` on the Last.fm API: 1 external HTTP request
2. Looks up each similar artist returned in the `name → id` lookup
3. Playlists that contain similar artists get a score:
```
score_lastfm(playlist) = Σ match_lastfm(Y) × tf(Y, playlist) × idf(Y)
```

If Last.fm doesn't solve it either: the menu has no suggestions and Enter picks FALLBACK_PULSE.

---

## Modules

### `user_config.py`
- `load_settings()` → `Settings` from `config/settings.py`; raises `SetupError` if the file is missing or the credentials are placeholders
- `load_config()` → `Config` from `config/config.json`
- `parse_playlist_id()` → accepts a playlist ID, link or URI

### `client.py` — SpotifyManager
- `get_current_track()` → current Track, playing or paused; `None` for no session, podcasts and ads
- `get_user_playlists()` → paginated list (the user's own playlists and the collaborative ones, as in the firmware)
- `is_track_liked()` and `add_track_to_playlist()` → the latter returns the new `snapshot_id`
- `api_calls` counter

### `playlist_analyzer.py` — SpotifyPlaylistAnalyzer
- `fetch_tracks()` → every song in a playlist, 100 per request; episodes and local files are skipped
- `build_profile()` → `(PlaylistProfile, artist_names)`
- `build_all_profiles()` → parallel with `ThreadPoolExecutor(max_workers=5)`; a playlist that fails is left out

### `cache.py`
- `Cache` → profiles, snapshots, artist names, and `record_add()`
- `load_cache()` / `save_cache()` → the JSON file above
- `sync_profiles()` → re-reads only the changed playlists, as described in the Cache section

### `matcher.py` — PlaylistMatcher
- `top_matches(track, n=3)` → top N with score > 0
- `lastfm_fallback(track, api_key)` → used only when top_matches comes back empty

### `lastfm_client.py`
- `get_similar_artists(artist_name, api_key)` → list of `{name, match}` through the stdlib `urllib`
- 5 s timeout, returns `[]` on any error and prints the reason

### `models.py`
```python
Track            — id, name, artist, artist_id
PlaylistProfile  — id, name, artist_counts, track_ids, artist_weights (derived)
MatchResult      — playlist_id, playlist_name, score, reason
```

---

## Configuration

### `config/settings.py`
```python
SPOTIFY_CLIENT_ID     = "..."
SPOTIFY_CLIENT_SECRET = "..."
SPOTIFY_REDIRECT_URI  = "http://127.0.0.1:8080"
LASTFM_API_KEY        = "..."   # optional: https://www.last.fm/api/account/create
```

### `config/config.json`
```json
{
  "fallback_playlist_id": "https://open.spotify.com/playlist/...",
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
python main.py --refresh       # forces every playlist to be read again
python main.py --cache-refresh # only rebuilds the cache, without looking at the current song
```

In normal mode, it shows the top 3 candidate playlists with score and reason and asks for confirmation before adding (`[1-3]` playlists, `l` Liked Songs, `f` FALLBACK_PULSE, `n` cancel).

---

## Known Limitations

- **New artists without Last.fm:** if the artist isn't in any playlist AND Last.fm has no data or none of the similar artists are in the playlists, the menu has no suggestions and Enter picks FALLBACK_PULSE (with `--auto`, nothing is added).
- **Co-occurrence depends on your own history:** Jaccard only works for artists that already appear in at least one of the user's playlists.
- **Main artist only:** featured artists are ignored.
