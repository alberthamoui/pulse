# PULSE — Arquitetura

PULSE monitora a música tocando no Spotify e decide automaticamente em qual das suas playlists adicioná-la, usando um sistema de scoring baseado em análise estatística do histórico de curadoria do usuário.

---

## Estrutura de Arquivos

```
pulse/
├── main.py                        # Orquestrador principal
├── config/
│   ├── constants.py               # Parâmetros do algoritmo (versionado)
│   ├── settings.py                # Credenciais Spotify + Last.fm (local, fora do git)
│   ├── config.json                # Configuração do sistema (local, fora do git)
│   └── *.example.*                # Modelos versionados de settings.py e config.json
├── src/
│   └── core/
│       ├── models.py              # Data classes
│       ├── client.py              # SpotifyManager (cliente API)
│       ├── playlist_analyzer.py   # Análise e perfilagem de playlists
│       ├── hybrid_matcher.py      # Algoritmo principal de matching
│       ├── artist_frequency_matcher.py  # Algoritmo alternativo simples
│       ├── matcher.py             # VibeMatcher (audio features, legado)
│       ├── matcher_base.py        # Interface abstrata dos matchers
│       ├── lastfm_client.py       # Cliente Last.fm para fallback
│       └── __init__.py
├── hardware/
│   ├── pi_zero/
│   │   └── handler.py             # Loop para Raspberry Pi Zero
│   └── pico/                      # Protótipo MicroPython (Pi Pico, simulado no Wokwi)
│       ├── main.py
│       ├── constants.py
│       └── diagram.json
└── docs/
    └── ARCHITECTURE.md
```

---

## Fluxo de Execução

```
python main.py [--auto | --dry-run | --refresh | --cache-refresh]
        │
        ├─ 1. Conecta ao Spotify (OAuth via spotipy)
        │
        ├─ 2. Obtém música tocando agora
        │       → se nada tocando: encerra
        │
        ├─ 3. Busca todas as playlists do usuário
        │
        ├─ 4. Sincroniza cache (veja seção Cache)
        │       → --refresh: reconstrói tudo
        │       → normal: atualiza só playlists com snapshot_id diferente
        │
        ├─ 5. Treina o HybridMatcher com os perfis
        │       → computa IDF de cada artista
        │       → constrói índice de co-ocorrência
        │       → constrói lookup nome → id para Last.fm
        │
        ├─ 6. Aviso de duplicata
        │       → verifica se a música já está em alguma playlist (via cache)
        │       → se sim: pergunta se quer continuar
        │         (--auto: não adiciona; --dry-run: só avisa)
        │
        ├─ 7. Scoring e seleção de playlist
        │       → tenta TF-IDF + co-ocorrência
        │       → se score=0 em tudo e Last.fm configurado: tenta fallback Last.fm
        │       → apresenta top 3 candidatas ao usuário
        │
        ├─ 8. Usuário confirma ou escolhe outra playlist
        │       → --auto: adiciona sem perguntar se score ≥ auto_add_min_score
        │       → --dry-run: mostra os candidatos e encerra sem adicionar
        │
        ├─ 9. Adiciona música à playlist escolhida
        │
        └─10. Atualiza cache localmente (sem chamada extra à API)
```

---

## Chamadas à API do Spotify

| Cenário | Chamadas |
|---|---|
| Run normal com cache válido | ~5 |
| Run com N playlists alteradas | ~5 + N × páginas |
| `--refresh` (46 playlists) | ~101 |

O contador `spotify.api_calls` é exibido ao final de cada execução. Toda chamada é interceptada via monkey-patch em `client.py:44`.

---

## Cache (`.pulse_cache.json`)

```json
{
  "algorithm": "hybrid",
  "cached_at": "2026-05-23T...",
  "snapshots": {
    "playlist_id": "snapshot_id_atual"
  },
  "artist_names": {
    "artist_id": "Nome do Artista"
  },
  "profiles": {
    "playlist_id": {
      "id": "...",
      "nome": "Nome da Playlist",
      "artista_weights": { "artist_id": 0.142 },
      "genre_weights": {},
      "total_tracks": 28,
      "track_ids": ["track_id_1", "track_id_2"]
    }
  }
}
```

**Invalidação inteligente:** a cada run, o `snapshot_id` de cada playlist é comparado com o do cache. Só playlists que mudaram são re-analisadas. Playlists removidas são descartadas do cache.

**Atualização pós-adição:** após adicionar uma música, o cache é atualizado localmente:
- `track_ids` da playlist recebe o novo track id
- `artista_weights` e `total_tracks` são recalculados sem chamada à API
- `snapshot_id` é atualizado com o valor retornado pelo endpoint de adição

---

## Algoritmo de Scoring (HybridMatcher)

### 1. Construção dos Perfis (build time)

Para cada playlist, `SpotifyPlaylistAnalyzer.build_artist_profile()` busca todas as faixas via paginação e calcula:

```
tf(artista, playlist) = (aparições + α) / (total_tracks + α × V)
```

Onde `α = 1` (Laplace smoothing) e `V` = número de artistas únicos na playlist.

O smoothing evita que playlists pequenas dominem com pesos inflados (ex: 1 artista em 3 músicas = 0.33 sem smoothing → 0.25 com smoothing se V=3).

### 2. Treinamento (train time)

O `HybridMatcher.train()` computa duas estruturas em memória:

**IDF por artista:**
```
idf(artista) = log(N / df)
```
Onde `N` = total de playlists e `df` = número de playlists que contêm o artista.
Artistas presentes em muitas playlists recebem IDF baixo (pouco discriminativos).

**Índice de co-ocorrência:**
```
artist_to_playlists = { artist_id: {pl_id_1, pl_id_2, ...} }
```
Usado para calcular Jaccard entre artistas na hora do match.

### 3. Scoring por Playlist (match time)

Para a música tocando, com artista X:

**Score direto:**
```
tfidf(X, playlist) = tf(X, playlist) × idf(X)
```

**Score indireto via co-ocorrência:**
```
indirect = Σ Jaccard(X, Y) × tf(Y, playlist) × idf(Y)
           para todo artista Y na playlist
```

Onde `Jaccard(X, Y) = |playlists_com_X ∩ playlists_com_Y| / |playlists_com_X ∪ playlists_com_Y|`

O Jaccard é calculado uma vez por match e cacheado localmente — não são chamadas à API.

**Score final:**
```
artist_score = tfidf + β × indirect     (β = 0.5)
score_final  = α × artist_score + (1-α) × genre_overlap    (α = 0.8)
```

`genre_overlap` é sempre 0 atualmente porque o endpoint de gêneros da Spotify API retorna 403.

### 4. Fallback Last.fm

Ativado apenas quando `score_final = 0` para todas as playlists (artista completamente desconhecido).

1. Chama `artist.getSimilar` na Last.fm API — 1 request HTTP externo
2. Para cada artista similar retornado, busca no lookup `nome → id` construído no `train()`
3. Playlists que contêm artistas similares recebem score:
```
score_lastfm(playlist) = Σ match_lastfm(Y) × tf(Y, playlist) × idf(Y)
```

Se Last.fm também não resolver: vai para FALLBACK_PULSE.

---

## Componentes

### `models.py`
```python
Track            — id, nome, artista, id_artista, artistas, artistas_nomes
PlaylistProfile  — id, nome, artista_weights, genre_weights, total_tracks, track_ids
MatchResult      — playlist_id, playlist_name, score, match_type, reason
AudioFeatures    — energy, danceability, valence, tempo, ...
```

### `client.py` — SpotifyManager
- `get_current_track()` → Track atual
- `get_user_playlists()` → lista paginada (filtra só playlists do próprio usuário)
- `get_artists_genres()` → batch de 50, retorna `{}` silenciosamente se endpoint indisponível
- `add_track_to_playlist()` → retorna novo `snapshot_id` (vem da resposta do endpoint)
- Contador `api_calls` via monkey-patch em `_internal_call`

### `playlist_analyzer.py` — SpotifyPlaylistAnalyzer
- `fetch_tracks()` → `(List[Track], total)` — paginação de 100 por request
- `build_artist_profile()` → `(artista_weights, total_tracks, track_ids, artist_names)`
- `build_all_profiles()` → paralelo com `ThreadPoolExecutor(max_workers=5)`, retorna `(profiles, artist_names)`

### `hybrid_matcher.py` — HybridMatcher
Algoritmo principal. Implementa TF-IDF + Laplace + co-ocorrência + fallback Last.fm.
- `train(profiles, artist_names)` → computa IDF, índice co-ocorrência, lookup nome→id
- `top_matches(track, n=3)` → top N com score > 0
- `lastfm_fallback(track, api_key)` → ativado só quando top_matches retorna vazio

### `lastfm_client.py`
- `get_similar_artists(artist_name, api_key)` → lista de `{name, match}` via stdlib `urllib`
- Timeout de 5s, retorna `[]` em qualquer erro

### `artist_frequency_matcher.py` — ArtistFrequencyMatcher
Algoritmo alternativo simples: score = frequência relativa do artista na playlist.
Disponível via `config.json: "algorithm": "artist_frequency"`.

---

## Configuração

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
  "fallback_playlist_id": "id_da_playlist_fallback",
  "cache_file": ".pulse_cache.json",
  "auto_add_min_score": 0.5,
  "mode": "code"
}
```

`auto_add_min_score` é o score mínimo para o `--auto` adicionar sem perguntar (padrão 0.5).

`mode: "hardware"` ativa o loop para Raspberry Pi Zero via `hardware/pi_zero/handler.py`.

---

## Modos de Execução

```bash
python main.py                 # usa cache, atualiza só o que mudou
python main.py --auto          # adiciona sem perguntar se o score passar do mínimo
python main.py --dry-run       # mostra os candidatos, não adiciona nada
python main.py --refresh       # força reanálise de todas as playlists
python main.py --cache-refresh # só reconstrói o cache, sem olhar a música tocando
```

No modo normal, exibe as top 3 playlists candidatas com score e motivo e pede confirmação antes de adicionar (`[1-3]` playlists, `l` Músicas Curtidas, `f` FALLBACK_PULSE, `n` cancelar).

---

## Limitações Conhecidas

- **Gêneros indisponíveis:** endpoint `GET /v1/artists` retorna 403 para apps não aprovados pelo Spotify. `genre_weights` fica sempre vazio.
- **Artistas novos sem Last.fm:** se o artista não está em nenhuma playlist E Last.fm não tem dados ou não há artistas similares nas playlists, vai para FALLBACK_PULSE.
- **`total_tracks` necessário para recálculo local:** cache antigo (anterior a maio/2026) tem `total_tracks=0`, o que desativa o recálculo de pesos após adição. Resolver com `--refresh`.
- **Co-ocorrência depende do histórico próprio:** Jaccard só funciona para artistas que já aparecem em pelo menos uma playlist do usuário.
