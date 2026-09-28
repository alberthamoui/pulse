# Pulse

Detecta a música tocando no Spotify e a adiciona automaticamente na playlist mais compatível. Sem match, cai na playlist de fallback (`FALLBACK_PULSE`).

## Estrutura

```
pulse/
├── main.py              # Entry point
├── config/
│   ├── constants.py            # Parâmetros do algoritmo (versionado)
│   ├── settings.example.py     # Modelo de credenciais → copiar para settings.py
│   └── config.example.json     # Modelo de configuração → copiar para config.json
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

Copie os arquivos de exemplo e preencha com seus dados (os arquivos copiados ficam fora do git):

```bash
cp config/settings.example.py config/settings.py
cp config/config.example.json config/config.json
```

**`config/settings.py`** — credenciais do Spotify e Last.fm (opcional):
```python
SPOTIFY_CLIENT_ID     = "..."
SPOTIFY_CLIENT_SECRET = "..."
SPOTIFY_REDIRECT_URI  = "http://127.0.0.1:8080"
LASTFM_API_KEY        = ""
```

**`config/config.json`** — parâmetros do sistema:
```json
{
  "algorithm": "hybrid",
  "fallback_playlist_id": "...",
  "cache_file": ".pulse_cache.json",
  "auto_add_min_score": 0.5,
  "mode": "code"
}
```

**`config/constants.py`** — parâmetros do algoritmo (pesos, Last.fm, threads). É versionado, sem dados sensíveis.

Algoritmos disponíveis: `artist_frequency`, `hybrid`, `audio_features`.

## Instalação

```bash
pip install -r requirements.txt
```

`gpiozero` é opcional — só necessário em Raspberry Pi para o botão físico.
