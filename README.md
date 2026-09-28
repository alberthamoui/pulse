# Pulse

Detecta a música tocando no Spotify e a adiciona automaticamente na playlist mais compatível. Sem match, cai na playlist de fallback (`FALLBACK_PULSE`).

## Estrutura

```
pulse/
├── main.py              # Entry point
├── config/
│   ├── settings.py      # Credenciais Spotify
│   └── config.json      # Configuração (algoritmo, fallback, cache)
├── src/
│   └── core/            # Lógica principal
│       ├── models.py
│       ├── client.py
│       ├── playlist_analyzer.py
│       ├── matcher_base.py
│       ├── artist_frequency_matcher.py
│       ├── hybrid_matcher.py
│       ├── lastfm_client.py
│       └── matcher.py
├── hardware/
│   ├── handler.py       # Botão GPIO genérico
│   ├── pi_zero/         # Loop para Raspberry Pi Zero (config "mode": "hardware")
│   └── pico/            # Protótipo MicroPython (Pi Pico / Wokwi)
├── tests/
│   └── validate_modules.py
└── docs/
    └── ARCHITECTURE.md
```

## Uso

```bash
python main.py                 # usa cache se disponível
python main.py --auto          # adiciona sem perguntar se o score passar do mínimo
python main.py --dry-run       # mostra os candidatos, não adiciona nada
python main.py --refresh       # força reanálise das playlists
python main.py --cache-refresh # só reconstrói o cache
```

## Configuração

**`config/settings.py`** — credenciais do Spotify:
```python
SPOTIFY_CLIENT_ID = "..."
SPOTIFY_CLIENT_SECRET = "..."
SPOTIFY_REDIRECT_URI = "http://localhost:8888/callback"
```

**`config/config.json`** — parâmetros do sistema:
```json
{
  "algorithm": "hybrid",
  "fallback_playlist_id": "...",
  "cache_file": ".pulse_cache.json",
  "auto_add_min_score": 0.5
}
```

Algoritmos disponíveis: `artist_frequency`, `hybrid`, `audio_features`.

## Instalação

```bash
pip install -r requirements.txt
```

`gpiozero` é opcional — só necessário em Raspberry Pi para o botão físico.
