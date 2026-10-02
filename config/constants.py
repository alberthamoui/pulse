# -=-=-=-=-=-=-=-= Algoritmo de scoring -=-=-=-=-=-=-=-=  
ALGO_ALPHA   = 0.8  # peso do sinal de artista vs gênero (0-1)
ALGO_BETA    = 0.5  # peso do sinal indireto de co-ocorrência (0-1)
LAPLACE_ALPHA = 1   # Laplace smoothing no cálculo de TF

# -=-=-=-=-=-=-=-= Last.fm -=-=-=-=-=-=-=-=  
LASTFM_SIMILAR_LIMIT = 50  # artistas similares buscados por chamada
LASTFM_TIMEOUT       = 5   # segundos de timeout HTTP

# -=-=-=-=-=-=-=-= Spotify API -=-=-=-=-=-=-=-=
PLAYLIST_WORKERS = 5  # threads paralelas na análise de playlists
