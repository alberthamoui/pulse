"""
PULSE - Pega a musica tocando no Spotify e adiciona na playlist mais compativel.
Se nao houver match, adiciona na playlist de fallback (FALLBACK_PULSE).

Uso:
    python main.py            # usa cache se disponivel
    python main.py --refresh  # forca reanálise das playlists
"""

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
import spotipy

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT))

from core import SpotifyManager, SpotifyPlaylistAnalyzer, ArtistFrequencyMatcher, VibeMatcher, HybridMatcher
from core.models import PlaylistProfile
from config.settings import SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REDIRECT_URI, LASTFM_API_KEY


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
        return data
    except Exception as e:
        print(f"Erro ao ler cache: {e}")
        return None


def save_cache(cache_path: Path, algorithm: str, profiles_data: dict, snapshots: dict, artist_names: dict = None) -> None:
    """Salva os perfis, snapshot_ids e nomes de artistas no cache."""
    try:
        data = {
            'algorithm': algorithm,
            'cached_at': datetime.now(timezone.utc).isoformat(),
            'snapshots': snapshots,
            'artist_names': artist_names or {},
            'profiles': profiles_data,
        }
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"Cache salvo em {cache_path}")
    except Exception as e:
        print(f"Aviso: nao foi possivel salvar cache: {e}")


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
            }
            for pl_id, p in profiles.items()
        }
        return profiles_data, artist_names

    elif matcher_type == 'audio_features':
        playlist_data = {}
        for pl in playlists:
            print(f"  Analisando: {pl['name']}...")
            try:
                tracks, features_list = analyzer.fetch_playlist_tracks_with_features(pl['id'])
                playlist_data[pl['id']] = {
                    'name': pl['name'],
                    'features': [f for f in features_list if f],
                }
            except Exception as e:
                print(f"  Erro ao analisar {pl['name']}: {e}")
        return playlist_data, {}

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

    elif matcher_type == 'audio_features':
        matcher = VibeMatcher()
        matcher.train_with_names(profiles_data)
        return matcher


def run_pulse(force_refresh: bool = False) -> dict:
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

    matcher_type = config.get('algorithm', 'artist_frequency')
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
    except TimeoutError:
        return {'success': False, 'error': 'Timeout ao conectar ao Spotify'}

    if not track:
        print("Nenhuma musica tocando no momento.")
        return {'success': False, 'error': 'Nenhuma música tocando'}

    print(f"Tocando: {track.nome} - {track.artista}")

    print("Verificando playlists...")
    all_playlists = spotify.get_user_playlists()

    cached_data   = None if force_refresh else load_cache(cache_path, matcher_type)
    profiles_data, snapshots, artist_names = sync_profiles(
        spotify, all_playlists, cached_data, matcher_type
    )

    if profiles_data:
        save_cache(cache_path, matcher_type, profiles_data, snapshots, artist_names)

    playlist_id   = None
    playlist_name = None
    candidates    = []

    if profiles_data:
        matcher = train_matcher(matcher_type, profiles_data, spotify, artist_names=artist_names)

        if matcher_type == 'hybrid' and hasattr(matcher, 'top_matches'):
            candidates = matcher.top_matches(track, n=3)

            if not candidates and LASTFM_API_KEY:
                print("Nenhum match direto. Tentando Last.fm...")
                candidates = matcher.lastfm_fallback(track, LASTFM_API_KEY)
                if candidates:
                    print("Match via Last.fm encontrado.")

            result = candidates[0] if candidates else None
        elif matcher_type == 'artist_frequency':
            result = matcher.match(track)
        else:
            features = spotify.get_audio_features(track.id)
            result   = matcher.match(track, audio_features=features) if features else None

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
        raw = input("Continuar mesmo assim? [s/n] (Enter = n): ").strip().lower()
        if raw != 's':
            elapsed = round(time.time() - t_start, 1)
            print(f"Cancelado. [{elapsed}s | {spotify.api_calls} chamadas API]")
            return {'success': False, 'error': 'Cancelado - musica ja na playlist'}
        print()

    # Confirmação interativa
    if matcher_type == 'hybrid':
        options = candidates
        liked_num    = len(options) + 1
        fallback_num = len(options) + 2
        skip_num     = len(options) + 3

        track_in_liked    = spotify.is_track_liked(track.id)
        track_in_fallback = track.id in profiles_data.get(fallback_id, {}).get('track_ids', [])  

        liked_label    = "Músicas Curtidas (já está)" if track_in_liked    else "Músicas Curtidas"
        fallback_label = "FALLBACK_PULSE (já está)"   if track_in_fallback else "FALLBACK_PULSE"

        print()
        print("Onde adicionar?")
        for i, r in enumerate(options, 1):
            marker = "(recomendado)" if i == 1 else ""
            print(f"  [{i}] {r.playlist_name}: {r.score:.2%} ({r.reason}) {marker}")
        print(f"  [{liked_num}] {liked_label}")
        print(f"  [{fallback_num}] {fallback_label}")
        print(f"  [{skip_num}] Não adicionar")
        print()

        valid_range = '/'.join(str(i) for i in range(1, skip_num + 1))
        while True:
            raw    = input(f"Escolha [{valid_range}] (Enter = 1): ").strip()
            choice = raw if raw else '1'

            if not choice.isdigit():
                print("  Opção inválida, tente novamente.")
                continue

            n = int(choice)
            if 1 <= n <= len(options):
                playlist_id   = options[n - 1].playlist_id
                playlist_name = options[n - 1].playlist_name
                break
            elif n == liked_num:
                playlist_id   = "liked"
                playlist_name = "Músicas Curtidas"
                break
            elif n == fallback_num:
                playlist_id   = fallback_id
                playlist_name = "FALLBACK_PULSE"
                break
            elif n == skip_num:
                elapsed = round(time.time() - t_start, 1)
                print(f"Cancelado. [{elapsed}s | {spotify.api_calls} chamadas API]")
                return {'success': False, 'error': 'Cancelado pelo usuario'}
            else:
                print("  Opção inválida, tente novamente.")
        print()

    if not playlist_id:
        playlist_id   = fallback_id
        playlist_name = "FALLBACK_PULSE"
        print("Sem match. Usando FALLBACK_PULSE.")

    new_snapshot = spotify.add_track_to_playlist(playlist_id, track.id)
    if new_snapshot is None:
        return {'success': False, 'error': 'Falha ao adicionar na playlist'}

    # Atualiza cache localmente sem chamadas extras
    if playlist_id in profiles_data and new_snapshot:
        profile = profiles_data[playlist_id]
        profile.setdefault('track_ids', []).append(track.id)
        snapshots[playlist_id] = new_snapshot

        total = profile.get('total_tracks', 0)
        if total > 0 and track.id_artista:
            new_total = total + 1
            old_weight = profile['artista_weights'].get(track.id_artista, 0.0)
            old_count  = round(old_weight * total)
            new_weights = {a: w * total / new_total for a, w in profile['artista_weights'].items()}
            new_weights[track.id_artista] = (old_count + 1) / new_total
            profile['artista_weights'] = new_weights
            profile['total_tracks']    = new_total

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
    force_refresh = '--refresh' in sys.argv

    try:
        config = load_config()
    except RuntimeError as e:
        print(f"Erro: {e}")
        sys.exit(1)

    mode = config.get('mode', 'code')

    if mode == 'hardware':
        from hardware.pi_zero.handler import run_hardware_loop
        run_hardware_loop(run_pulse)
        return

    result = run_pulse(force_refresh)
    if not result['success']:
        print(f"Erro: {result.get('error')}")
        sys.exit(1)


if __name__ == '__main__':
    main()
