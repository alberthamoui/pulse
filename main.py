"""
PULSE - Pega a musica tocando no Spotify e adiciona na playlist mais compativel.
Se nao houver match, adiciona na playlist de fallback (FALLBACK_PULSE).

Uso:
    python main.py                 # usa cache se disponivel
    python main.py --auto          # modo automático (sem prompts)
    python main.py --dry-run       # executa o matching mas nao adiciona na playlist
    python main.py --refresh       # forca reanálise das playlists
    python main.py --cache-refresh # reconstrói o cache sem verificar música tocando

"""

import sys
from pathlib import Path
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT))
import json
import os
import tempfile
import time
from datetime import datetime, timezone
import spotipy
from core import SpotifyManager, SpotifyPlaylistAnalyzer, ArtistFrequencyMatcher, HybridMatcher
from core.models import PlaylistProfile
from core.playlist_analyzer import smoothed_weights
from config.settings import SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REDIRECT_URI, LASTFM_API_KEY

DEFAULT_AUTO_ADD_MIN_SCORE = 0.5  # usado se 'auto_add_min_score' nao estiver no config.json
DEFAULT_ALGORITHM = 'hybrid'
CACHE_VERSION = 2  # 2: perfis guardam as contagens brutas (artist_counts)


def load_config() -> dict:
    config_path = ROOT / 'config' / 'config.json'
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        raise RuntimeError(f"config.json nao encontrado em {config_path}")
    except json.JSONDecodeError:
        raise RuntimeError("config.json invalido")


def load_cache(cache_path: Path, algorithm: str) -> dict | None:
    """Retorna o cache completo se existir e o algoritmo bater."""
    if not cache_path.exists():
        return None
    try:
        with open(cache_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if data.get('algorithm') != algorithm:
            print("Cache invalido: algoritmo diferente do configurado.")
            return None
        if data.get('version') != CACHE_VERSION:
            print("Cache em formato antigo: reconstruindo os perfis.")
            return None
        return data
    except Exception as e:
        print(f"Erro ao ler cache: {e}")
        return None


def save_cache(cache_path: Path, algorithm: str, profiles_data: dict, snapshots: dict, artist_names: dict = None) -> None:
    """Salva os perfis, snapshot_ids e nomes de artistas no cache."""
    try:
        data = {
            'version': CACHE_VERSION,
            'algorithm': algorithm,
            'cached_at': datetime.now(timezone.utc).isoformat(),
            'snapshots': snapshots,
            'artist_names': artist_names or {},
            'profiles': profiles_data,
        }
        # Grava num temporário e troca: uma interrupção no meio não corrompe o cache
        fd, tmp = tempfile.mkstemp(dir=cache_path.parent, prefix=cache_path.name, suffix='.tmp')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, cache_path)
        except BaseException:
            os.unlink(tmp)
            raise
        print(f"Cache salvo em {cache_path}")
    except Exception as e:
        print(f"Aviso: nao foi possivel salvar cache: {e}")


def atualiza_cache(profiles_data: dict, snapshots: dict, playlist_id: str, new_snapshot: str, track) -> None:
    """Atualiza o cache localmente apos adicionar uma musica, sem chamadas extras a API."""
    profile = profiles_data[playlist_id]
    profile.setdefault('track_ids', []).append(track.id)
    profile['total_tracks'] = profile.get('total_tracks', 0) + 1
    snapshots[playlist_id] = new_snapshot

    if track.id_artista:
        counts = profile.setdefault('artist_counts', {})
        counts[track.id_artista] = counts.get(track.id_artista, 0) + 1
        profile['artista_weights'] = smoothed_weights(counts)


def build_profiles_for(spotify: SpotifyManager, playlists: list, matcher_type: str) -> tuple[dict, dict]:
    """
    Constroi perfis para a lista de playlists fornecida.
    Retorna (profiles_data, artist_names).
    """
    if not playlists:
        return {}, {}

    analyzer = SpotifyPlaylistAnalyzer(spotify)

    if matcher_type in ('artist_frequency', 'hybrid'):
        profiles, artist_names = analyzer.build_all_profiles(playlists)
        profiles_data = {
            pl_id: {
                'id': p.id,
                'nome': p.nome,
                'artista_weights': p.artista_weights,
                'genre_weights': p.genre_weights,
                'total_tracks': p.total_tracks,
                'track_ids': p.track_ids,
                'artist_counts': p.artist_counts,
            }
            for pl_id, p in profiles.items()
        }
        return profiles_data, artist_names

    raise RuntimeError(f"Algoritmo desconhecido: '{matcher_type}'")


def sync_profiles(spotify: SpotifyManager, all_playlists: list, cached_data: dict | None,
                    matcher_type: str) -> tuple[dict, dict, dict]:
    """
    Atualiza apenas as playlists cujo snapshot_id mudou desde o ultimo cache.
    Retorna (profiles_data, snapshots_atual, artist_names).
    """
    playlists = [p for p in all_playlists if p['id']]
    current_snapshots = {p['id']: p['snapshot_id'] for p in playlists}

    if cached_data is None:
        print(f"Sem cache. Analisando {len(playlists)} playlists...")
        profiles, artist_names = build_profiles_for(spotify, playlists, matcher_type)
        return profiles, current_snapshots, artist_names

    cached_snapshots = cached_data.get('snapshots', {})
    cached_profiles  = cached_data.get('profiles', {})
    cached_names     = cached_data.get('artist_names', {})

    changed = [p for p in playlists if current_snapshots[p['id']] != cached_snapshots.get(p['id'])]
    removed = [pid for pid in cached_profiles if pid not in current_snapshots]

    if not changed and not removed:
        cached_at = datetime.fromisoformat(cached_data['cached_at'])
        age_hours = (datetime.now(timezone.utc) - cached_at).total_seconds() / 3600
        print(f"Cache valido ({age_hours:.1f}h atras). Nenhuma playlist alterada.")
        return cached_profiles, current_snapshots, cached_names

    print(f"{len(changed)} playlist(s) alterada(s), {len(removed)} removida(s). Atualizando...")
    for p in changed:
        print(f"  ~ {p['name']}")
    new_profiles, new_names = build_profiles_for(spotify, changed, matcher_type)

    merged = {pid: prof for pid, prof in cached_profiles.items() if pid not in removed}
    merged.update(new_profiles)
    merged_names = {**cached_names, **new_names}
    return merged, current_snapshots, merged_names


def train_matcher(matcher_type: str, profiles_data: dict, spotify=None, artist_names: dict = None):
    """Cria e treina o matcher com os dados de perfil."""
    if matcher_type == 'artist_frequency':
        profiles = {
            pl_id: PlaylistProfile(
                id=d['id'],
                nome=d['nome'],
                artista_weights=d['artista_weights'],
                total_tracks=d.get('total_tracks', 0),
            )
            for pl_id, d in profiles_data.items()
        }
        matcher = ArtistFrequencyMatcher()
        matcher.train(profiles)
        return matcher

    elif matcher_type == 'hybrid':
        profiles = {
            pl_id: PlaylistProfile(
                id=d['id'],
                nome=d['nome'],
                artista_weights=d['artista_weights'],
                genre_weights=d.get('genre_weights', {}),
                total_tracks=d.get('total_tracks', 0),
            )
            for pl_id, d in profiles_data.items()
        }
        matcher = HybridMatcher(spotify)
        matcher.train(profiles, artist_names=artist_names)
        return matcher

    raise RuntimeError(f"Algoritmo desconhecido: '{matcher_type}'")


def prompt_playlist_choice(
    candidates: list,
    fallback_id: str,
    profiles_data: dict,
    spotify,
    track,
) -> tuple[str, str] | None:
    """
    Exibe o menu de escolha de playlist e retorna (playlist_id, playlist_name).
    Retorna None se o usuário cancelar.
    """
    options = candidates
    track_in_liked    = spotify.is_track_liked(track.id)
    track_in_fallback = track.id in profiles_data.get(fallback_id, {}).get('track_ids', [])

    liked_label    = "Músicas Curtidas (já está)" if track_in_liked    else "Músicas Curtidas"
    fallback_label = "FALLBACK_PULSE (já está)"   if track_in_fallback else "FALLBACK_PULSE"

    print()
    if options:
        print("Onde adicionar?")
    else:
        print("Nenhuma playlist compatível encontrada. Escolha manualmente:")
    for i, r in enumerate(options, 1):
        reason = f" ({r.reason})" if r.reason else ""
        marker = " (recomendado)" if i == 1 else ""
        print(f"  [{i}] {r.playlist_name}: {r.score:.2%}{reason}{marker}")
    print(f"  [l] {liked_label}")
    print(f"  [f] {fallback_label}")
    print("  [n] Não adicionar")
    print()

    valid_range = '/'.join(str(i) for i in range(1, len(options) + 1)) + '/l/f/n'
    default = '1' if options else 'f'  # sem sugestão, Enter vai para a fallback
    while True:
        raw    = input(f"Escolha [{valid_range.lstrip('/')}] (Enter = {default}): ").strip()
        choice = raw if raw else default

        if choice == 'l':
            return "liked", "Músicas Curtidas"
        elif choice == 'f':
            return fallback_id, "FALLBACK_PULSE"
        elif choice == 'n':
            return None
        elif choice.isdigit() and 1 <= int(choice) <= len(options):
            r = options[int(choice) - 1]
            return r.playlist_id, r.playlist_name
        else:
            print("  Opção inválida, tente novamente.")


def run_cache_refresh() -> dict:
    """Reconstrói o cache de playlists sem verificar a música tocando."""
    t_start = time.time()

    try:
        config = load_config()
    except RuntimeError as e:
        return {'success': False, 'error': str(e)}

    matcher_type = config.get('algorithm', DEFAULT_ALGORITHM)
    cache_file   = config.get('cache_file', '.pulse_cache.json')
    cache_path   = ROOT / cache_file

    print("Conectando ao Spotify...")
    spotify = SpotifyManager(
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET,
        redirect_uri=SPOTIFY_REDIRECT_URI
    )

    print("Buscando playlists...")
    all_playlists = spotify.get_user_playlists()

    profiles_data, snapshots, artist_names = sync_profiles(
        spotify, all_playlists, None, matcher_type  # None força rebuild completo
    )

    if profiles_data:
        save_cache(cache_path, matcher_type, profiles_data, snapshots, artist_names)
        elapsed = round(time.time() - t_start, 1)
        print(f"Cache atualizado: {len(profiles_data)} playlists [{elapsed}s | {spotify.api_calls} chamadas API]")
        return {'success': True, 'playlists': len(profiles_data), 'elapsed': elapsed}

    return {'success': False, 'error': 'Nenhum perfil gerado'}


def run_pulse(mode: str = 'normal') -> dict:
    """
    Executa o ciclo completo do Pulse.

    Retorna:
        {'success': True,  'track': '...', 'playlist': '...', 'elapsed': 1.2}
        {'success': False, 'error': 'mensagem'}
    """
    t_start = time.time()

    try:
        config = load_config()
    except RuntimeError as e:
        return {'success': False, 'error': str(e)}

    matcher_type = config.get('algorithm', DEFAULT_ALGORITHM)
    fallback_id  = config.get('fallback_playlist_id')
    cache_file   = config.get('cache_file', '.pulse_cache.json')
    cache_path   = ROOT / cache_file

    if not fallback_id:
        return {'success': False, 'error': "'fallback_playlist_id' nao configurado"}

    print("Conectando ao Spotify...")
    spotify = SpotifyManager(
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET,
        redirect_uri=SPOTIFY_REDIRECT_URI
    )

    try:
        track = spotify.get_current_track()
    except (spotipy.exceptions.SpotifyException, ConnectionError, TimeoutError) as e:
        return {'success': False, 'error': f'Erro Spotify/conexão: {e}'}

    if not track:
        print("Nenhuma musica tocando no momento.")
        elapsed = round(time.time() - t_start, 1)
        print(f"[{elapsed}s | {spotify.api_calls} chamadas API]")
        return {'success': False, 'error': 'Nenhuma música tocando'}

    print(f"Tocando: {track.nome} - {track.artista}")

    if not track.id:
        return {'success': False, 'error': 'Arquivo local: fora do catálogo do Spotify, não dá para adicionar'}

    print("Verificando playlists...")
    all_playlists = spotify.get_user_playlists()

    cached_data   = None if (mode == 'refresh') else load_cache(cache_path, matcher_type)
    profiles_data, snapshots, artist_names = sync_profiles(
        spotify, all_playlists, cached_data, matcher_type
    )

    if profiles_data:
        save_cache(cache_path, matcher_type, profiles_data, snapshots, artist_names)

    playlist_id   = None
    playlist_name = None
    candidates    = []
    result        = None

    if profiles_data:
        matcher = train_matcher(matcher_type, profiles_data, spotify, artist_names=artist_names)

        if matcher_type == 'hybrid':
            candidates = matcher.top_matches(track, n=3)
            if not candidates and LASTFM_API_KEY:
                print("Nenhum match direto. Tentando Last.fm...")
                candidates = matcher.lastfm_fallback(track, LASTFM_API_KEY)
                if candidates:
                    print("Match via Last.fm encontrado.")
        else:
            best = matcher.match(track)
            candidates = [best] if best else []

        result = candidates[0] if candidates else None

        if result:
            playlist_id   = result.playlist_id
            playlist_name = result.playlist_name

    # Aviso de duplicata
    track_to_playlists: dict = {}
    for pd in profiles_data.values():
        for tid in pd.get('track_ids', []):
            track_to_playlists.setdefault(tid, []).append(pd['nome'])

    already_in = track_to_playlists.get(track.id, [])
    if already_in:
        print(f"\nAviso: esta música já está em: {', '.join(already_in)}")
        if mode == 'auto':
            elapsed = round(time.time() - t_start, 1)
            print(f"Modo automático: não adicionando duplicata. [{elapsed}s | {spotify.api_calls} chamadas API]")
            return {'success': False, 'error': 'Musica ja esta em uma playlist'}
    if already_in and mode != 'dry-run':
        raw = input("Continuar mesmo assim? [s/n] (Enter = n): ").strip().lower()
        if raw != 's':
            elapsed = round(time.time() - t_start, 1)
            print(f"Cancelado. [{elapsed}s | {spotify.api_calls} chamadas API]")
            return {'success': False, 'error': 'Cancelado - musica ja na playlist'}
        print()

    if mode == 'auto':
        # Confirmação automática: só adiciona se o melhor match passar do score mínimo
        min_score = config.get('auto_add_min_score', DEFAULT_AUTO_ADD_MIN_SCORE)
        elapsed   = round(time.time() - t_start, 1)
        if not result:
            print(f"Sem candidatos para auto-add. [{elapsed}s | {spotify.api_calls} chamadas API]")
            return {'success': False, 'error': 'Sem candidatos para auto-add'}
        if result.score < min_score:
            print(f"Score baixo ({result.score:.2%} < {min_score:.2%}). Não adicionando automaticamente. "
                  f"[{elapsed}s | {spotify.api_calls} chamadas API]")
            return {'success': False, 'error': 'Score abaixo do minimo para auto-add'}

    if mode == 'dry-run':
        # Nao vai adicionar nada, só mostra os candidatos e sai
        if candidates:
            for r in candidates:
                print(f"  {r.playlist_name}: {r.score:.2%} ({r.reason})")
        elif not result:
            print("Nenhum candidato encontrado.")

        elapsed = round(time.time() - t_start, 1)
        print(f"\nIria ser adicionado em: {playlist_name or 'FALLBACK_PULSE'} [{elapsed}s | {spotify.api_calls} chamadas API]\n")
        return {
            'success':  True,
            'track':    f"{track.nome} - {track.artista}",
            'playlist': playlist_name or 'FALLBACK_PULSE',
            'elapsed':  elapsed,
        }

    # Confirmação interativa: só o --auto adiciona sem perguntar
    if mode != 'auto':
        choice = prompt_playlist_choice(candidates, fallback_id, profiles_data, spotify, track)
        if choice is None:
            elapsed = round(time.time() - t_start, 1)
            print(f"Cancelado. [{elapsed}s | {spotify.api_calls} chamadas API]")
            return {'success': False, 'error': 'Cancelado pelo usuario'}
        playlist_id, playlist_name = choice
        print()

    if not playlist_id:
        playlist_id   = fallback_id
        playlist_name = "FALLBACK_PULSE"
        print("Sem match. Usando FALLBACK_PULSE.")

    new_snapshot = spotify.add_track_to_playlist(playlist_id, track.id)
    if new_snapshot is None:
        return {'success': False, 'error': 'Falha ao adicionar na playlist'}

    if playlist_id in profiles_data and new_snapshot:
        atualiza_cache(profiles_data, snapshots, playlist_id, new_snapshot, track)
        save_cache(cache_path, matcher_type, profiles_data, snapshots, artist_names)

    elapsed = round(time.time() - t_start, 1)
    print(f"Adicionado em: {playlist_name}")
    print(f"[{elapsed}s | {spotify.api_calls} chamadas API]")

    return {
        'success':  True,
        'track':    f"{track.nome} - {track.artista}",
        'playlist': playlist_name,
        'elapsed':  elapsed,
    }


def main():
    if '--auto' in sys.argv:
        mode = 'auto'
    elif '--dry-run' in sys.argv:
        mode = 'dry-run'
    elif '--refresh' in sys.argv:
        mode = 'refresh'
    elif '--cache-refresh' in sys.argv:
        mode = 'cache-refresh'
    else:
        mode = 'normal'

    if mode == 'cache-refresh':
        result = run_cache_refresh()
        if not result['success']:
            print(f"Erro: {result.get('error')}")
            sys.exit(1)
        return

    result = run_pulse(mode)
    if not result['success']:
        print(f"Erro: {result.get('error')}")
        sys.exit(1)


if __name__ == '__main__':
    main()
