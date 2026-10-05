# -=-=-=-=-=-=-=-= Scoring algorithm -=-=-=-=-=-=-=-=  
ALGO_ALPHA   = 0.8  # weight of the artist signal vs genre (0-1)
ALGO_BETA    = 0.5  # weight of the indirect co-occurrence signal (0-1)
LAPLACE_ALPHA = 1   # Laplace smoothing in the TF computation

# -=-=-=-=-=-=-=-= Last.fm -=-=-=-=-=-=-=-=  
LASTFM_SIMILAR_LIMIT = 50  # similar artists fetched per call
LASTFM_TIMEOUT       = 5   # HTTP timeout in seconds

# -=-=-=-=-=-=-=-= Spotify API -=-=-=-=-=-=-=-=
PLAYLIST_WORKERS = 5  # parallel threads when analyzing playlists
