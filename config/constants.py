# -=-=-=-=-=-=-=-= Algoritmo de scoring -=-=-=-=-=-=-=-=  
ALGO_ALPHA   = 0.8  # peso do sinal de artista vs gênero (0-1)
ALGO_BETA    = 0.5  # peso do sinal indireto de co-ocorrência (0-1)
LAPLACE_ALPHA = 1   # Laplace smoothing no cálculo de TF

# -=-=-=-=-=-=-=-= Last.fm -=-=-=-=-=-=-=-=  
LASTFM_SIMILAR_LIMIT = 50  # artistas similares buscados por chamada
LASTFM_TIMEOUT       = 5   # segundos de timeout HTTP

# -=-=-=-=-=-=-=-= Correções do usuário -=-=-=-=-=-=-=-=
CORRECTION_BOOST     = 0.15  # boost por correção registrada
CORRECTION_BOOST_MAX = 0.45  # teto do boost (equivale a 3 correções)

# -=-=-=-=-=-=-=-= Spotify API -=-=-=-=-=-=-=-=
PLAYLIST_WORKERS = 5  # threads paralelas na análise de playlists

# -=-=-=-=-=-=-=-= Hardware Pi Zero -=-=-=-=-=-=-=-=
HW_BTN_TRIGGER_PIN = 15  # dispara análise
HW_BTN_CYCLE_PIN   = 16  # alterna entre candidatas
HW_BTN_CONFIRM_PIN = 18  # confirma seleção
HW_LED_PIN         = 14
HW_BTN_BOUNCE_TIME = 0.3   # segundos de debounce
HW_I2C_PORT        = 1
HW_I2C_ADDRESS     = 0x3C
HW_OLED_WIDTH      = 128
HW_OLED_HEIGHT     = 64
