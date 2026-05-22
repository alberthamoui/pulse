# Pulse

Detecta a música tocando no Spotify e a adiciona automaticamente na playlist mais compatível. Sem match, cai na playlist de fallback (`FALLBACK_PULSE`).

## Estrutura

```
pulse/
├── main.py              # Entry point
├── config/
│   ├── settings.py      # Credenciais Spotify (não commitar)
│   └── config.json      # Configuração (algoritmo, fallback, cache)
├── src/
│   ├── core/            # Lógica principal
│   │   ├── models.py
│   │   ├── client.py
│   │   ├── playlist_analyzer.py
│   │   ├── matcher_base.py
│   │   ├── artist_frequency_matcher.py
│   │   ├── hybrid_matcher.py
│   │   └── matcher.py
│   └── hardware/
│       └── handler.py   # Botão GPIO (opcional, Raspberry Pi)
├── hardware/
│   └── handler.py
├── tests/
│   └── validate_modules.py
└── docs/
    └── ARCHITECTURE.md
```

## Uso

```bash
python main.py            # usa cache se disponível
python main.py --refresh  # força reanálise das playlists
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
  "cache_file": ".pulse_cache.json"
}
```

Algoritmos disponíveis: `artist_frequency`, `hybrid`, `audio_features`.

## Instalação

```bash
pip install -r requirements.txt
```

`gpiozero` é opcional — só necessário em Raspberry Pi para o botão físico.
