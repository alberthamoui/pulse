"""Tuning knobs for the ranking, Last.fm and the Spotify sync."""

# -=-=-=-=-=-=-=-= Ranking -=-=-=-=-=-=-=-=
CO_OCCURRENCE_WEIGHT = 0.5  # weight of the indirect (co-occurrence) signal next to the direct one
LAPLACE_ALPHA = 1           # Laplace smoothing in each artist's tf

# -=-=-=-=-=-=-=-= Last.fm -=-=-=-=-=-=-=-=
LASTFM_SIMILAR_LIMIT = 50  # similar artists fetched per call
LASTFM_TIMEOUT       = 5   # HTTP timeout in seconds

# -=-=-=-=-=-=-=-= Spotify API -=-=-=-=-=-=-=-=
PLAYLIST_WORKERS = 5  # parallel threads when reading playlists
