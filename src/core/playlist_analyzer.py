"""
Analisador de playlists do Spotify.

Responsável por extrair dados e construir perfis de playlists
baseados em frequência relativa de artistas.
"""

import time
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional
from .models import Track, PlaylistProfile, AudioFeatures
from .client import SpotifyManager


class SpotifyPlaylistAnalyzer:
    """Analisa playlists e constrói seus perfis de conteúdo."""
    
    def __init__(self, spotify_manager: SpotifyManager):
        """
        Inicializa o analisador com um cliente Spotify.
        
        Args:
            spotify_manager: Instância de SpotifyManager para acesso à API
        """
        self.spotify = spotify_manager
    
    def fetch_tracks(self, playlist_id: str) -> tuple[List[Track], int]:
        """
        Extrai todas as faixas de uma playlist com paginação.

        Returns:
            (lista de Track, total de faixas reportado pela API)
        """
        tracks = []
        total = 0
        offset = 0

        while True:
            response = self.spotify.sp.playlist_items(playlist_id, limit=100, offset=offset)
            if offset == 0:
                total = response.get('total', 0)

            for item in response.get('items', []):
                track = item.get('item')
                if track and track.get('id'):
                    artists = track.get('artists', [])
                    first_artist = artists[0] if artists else {}

                    track_obj = Track(
                        id=track['id'],
                        nome=track.get('name', 'Desconhecido'),
                        artista=first_artist.get('name', 'Desconhecido'),
                        id_artista=first_artist.get('id')
                    )
                    tracks.append(track_obj)

            if not response.get('next'):
                break
            offset += 100

        return tracks, total
    
    def build_artist_profile(self, playlist_id: str) -> tuple[Dict[str, float], int, list]:
        """
        Constrói o perfil de uma playlist baseado em frequência de artistas.

        Returns:
            ({ id_artista: peso_relativo }, total_tracks reportado pela API, lista de track IDs)
        """
        tracks, total_tracks = self.fetch_tracks(playlist_id)

        if not tracks:
            return {}, total_tracks, []

        track_ids = [t.id for t in tracks if t.id]
        artist_names = {t.id_artista: t.artista for t in tracks if t.id_artista and t.artista}
        artist_ids = [t.id_artista for t in tracks if t.id_artista]
        artist_counter = Counter(artist_ids)
        total = sum(artist_counter.values())
        V = len(artist_counter)

        ALPHA = 1  # Laplace smoothing
        smoothed = {
            artist_id: (count + ALPHA) / (total + ALPHA * V)
            for artist_id, count in artist_counter.items()
        }

        return smoothed, total_tracks, track_ids, artist_names
    
    def build_genre_profile(self, artist_weights: Dict[str, float]) -> Dict[str, float]:
        """
        Derives a genre weight dict from an existing artist_weights dict.
        Each genre inherits the weight of its artist; shared genres accumulate.
        Result is normalized to sum=1.0.
        """
        if not artist_weights:
            return {}
        artist_genres = self.spotify.get_artists_genres(list(artist_weights.keys()))
        raw: Dict[str, float] = {}
        for artist_id, weight in artist_weights.items():
            for genre in artist_genres.get(artist_id, []):
                raw[genre] = raw.get(genre, 0.0) + weight
        total = sum(raw.values())
        return {g: w / total for g, w in raw.items()} if total > 0 else {}

    def build_all_profiles(self, playlists: List[Dict[str, str]]) -> tuple[Dict[str, PlaylistProfile], Dict[str, str]]:
        """
        Constrói perfis para múltiplas playlists.

        Returns:
            (playlist_id → PlaylistProfile, artist_id → artist_name)
        """
        profiles = {}
        artist_names: Dict[str, str] = {}
        total = len(playlists)
        t_start = time.time()
        lock = threading.Lock()
        done = [0]

        def process(playlist: Dict) -> Optional[tuple]:
            playlist_id = playlist.get('id')
            playlist_name = playlist.get('name')
            if not playlist_id or not playlist_name:
                return None

            try:
                artist_weights, total_tracks, track_ids, names = self.build_artist_profile(playlist_id)
                genre_weights = self.build_genre_profile(artist_weights)
            except Exception:
                with lock:
                    done[0] += 1
                    print(f"  [{done[0]}/{total}] {playlist_name}... pulando (sem acesso)")
                return None

            with lock:
                done[0] += 1
                print(f"  [{done[0]}/{total}] {playlist_name}... ok")

            return playlist_id, PlaylistProfile(
                id=playlist_id,
                nome=playlist_name,
                artista_weights=artist_weights,
                genre_weights=genre_weights,
                total_tracks=total_tracks,
                track_ids=track_ids,
            ), names

        with ThreadPoolExecutor(max_workers=5) as executor:
            for result in as_completed([executor.submit(process, p) for p in playlists]):
                data = result.result()
                if data:
                    pl_id, profile, names = data
                    profiles[pl_id] = profile
                    artist_names.update(names)

        elapsed = time.time() - t_start
        print(f"Análise concluída em {elapsed:.1f}s ({len(profiles)}/{total} playlists).")
        return profiles, artist_names
    
    def fetch_playlist_tracks_with_features(
        self, playlist_id: str
    ) -> tuple[List[Track], List[Optional[AudioFeatures]]]:
        """
        Extrai faixas de uma playlist junto com suas features de áudio.
        
        Args:
            playlist_id: ID da playlist
            
        Returns:
            Tupla (lista de Track, lista de AudioFeatures)
        """
        tracks, _ = self.fetch_tracks(playlist_id)
        features_list = []

        for i in range(0, len(tracks), 100):
            batch = tracks[i:i+100]
            track_ids = [t.id for t in batch]
            
            try:
                features_response = self.spotify.sp.audio_features(track_ids)
                features_list.extend(features_response)
            except Exception as e:
                print(f"  Erro ao buscar features: {e}")
                features_list.extend([None] * len(batch))
        
        return tracks, features_list
