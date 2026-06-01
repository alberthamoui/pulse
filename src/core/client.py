"""
Cliente Spotify - Gerencia a comunicação com a API do Spotify.

Fornece métodos para autenticação, busca de músicas, features de áudio
e gerenciamento de playlists.
"""

import json
import spotipy
from pathlib import Path
from spotipy.oauth2 import SpotifyOAuth
from typing import List, Dict, Optional
from .models import Track, AudioFeatures

_GENRES_FLAG_FILE = Path(__file__).parent.parent.parent / '.pulse_genres_flag.json'


class SpotifyManager:
    """Gerenciador centralizado para todas as operações com a API Spotify."""
    
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        """
        Inicializa o cliente Spotify com credenciais OAuth.
        
        Args:
            client_id: ID do cliente Spotify
            client_secret: Secret do cliente Spotify
            redirect_uri: URI de redirecionamento após autenticação
        """
        scopes = (
            "user-read-currently-playing "
            "playlist-modify-private "
            "playlist-modify-public "
            "playlist-read-private "
            "user-library-read "
            "user-library-modify"
        )
        
        self.sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope=scopes
        ))
        self.api_calls = 0
        _orig = self.sp._internal_call
        def _counting_call(*args, **kwargs):
            self.api_calls += 1
            return _orig(*args, **kwargs)
        self.sp._internal_call = _counting_call

        self._genres_available = self._check_genres_available()

    def get_current_user(self) -> Optional[Dict]:
        """
        Obtém informações do usuário autenticado.
        
        Returns:
            Dict com 'display_name' e 'id', ou None se erro
        """
        try:
            user = self.sp.current_user()
            return {
                'display_name': user.get('display_name'),
                'id': user.get('id')
            }
        except Exception as e:
            print(f"Erro ao obter usuário: {e}")
            return None

    def get_current_track(self) -> Optional[Track]:
        """
        Obtém a música tocando no momento.
        
        Returns:
            Objeto Track ou None se nada estiver tocando
        """
        try:
            result = self.sp.current_user_playing_track()
            if result and result.get('is_playing') and result.get('item'):
                item = result['item']
                artists = item.get('artists', [])
                first_artist = artists[0] if artists else {}
                
                return Track(
                    id=item.get('id'),
                    nome=item.get('name'),
                    artista=first_artist.get('name', 'Desconhecido'),
                    id_artista=first_artist.get('id')
                )
            return None  # música não tocando
        except (spotipy.exceptions.SpotifyException, ConnectionError, TimeoutError) as e:
            raise  # relança erros graves para main.py tratar
        except Exception as e:
            print(f"Erro inesperado ao obter música atual: {e}")
            return None

    def get_audio_features(self, track_id: str) -> Optional[Dict]:
        """
        Obtém features de áudio de uma música.
        
        Args:
            track_id: ID da música no Spotify
            
        Returns:
            Dict com features (energy, danceability, etc) ou None
        """
        try:
            features = self.sp.audio_features([track_id])
            return features[0] if features else None
        except Exception as e:
            print(f"Erro ao obter features: {e}")
            return None

    def get_user_playlists(self) -> List[Dict]:
        """
        Obtém todas as playlists do usuário com paginação.

        Returns:
            Lista de dicts com 'id', 'name' e 'snapshot_id'
        """
        playlists = []
        try:
            user_id = self.sp.current_user()['id']
            result = self.sp.current_user_playlists(limit=50)
            while result:
                for p in result.get('items', []):
                    if p.get('owner', {}).get('id') == user_id:
                        playlists.append({
                            'id': p['id'],
                            'name': p['name'],
                            'snapshot_id': p.get('snapshot_id', ''),
                        })
                result = self.sp.next(result) if result.get('next') else None
        except Exception as e:
            print(f"Erro ao obter playlists: {e}")
        return playlists

    def _check_genres_available(self) -> bool:
        if _GENRES_FLAG_FILE.exists():
            try:
                data = json.loads(_GENRES_FLAG_FILE.read_text())
                available = data.get('available', False)
                if not available:
                    print("Aviso: endpoint de gêneros indisponível (403). Matching apenas por artista.")
                return available
            except Exception:
                pass

        import logging
        spotipy_logger = logging.getLogger('spotipy.client')
        prev_level = spotipy_logger.level
        spotipy_logger.setLevel(logging.CRITICAL)
        try:
            self.sp._get('artists', ids='0TnOYISbd1XYRBk9myaseg')
            available = True
        except Exception:
            print("Aviso: endpoint de gêneros indisponível (403). Matching apenas por artista.")
            available = False
        finally:
            spotipy_logger.setLevel(prev_level)

        try:
            _GENRES_FLAG_FILE.write_text(json.dumps({'available': available}))
        except Exception:
            pass
        return available

    def get_artists_genres(self, artist_ids: List[str]) -> Dict[str, List[str]]:
        """
        Fetches genres for a list of artist IDs, batching 50 at a time.
        Returns empty dicts silently if the endpoint is unavailable.
        """
        if not self._genres_available:
            return {aid: [] for aid in artist_ids}

        import logging
        spotipy_logger = logging.getLogger('spotipy.client')
        result: Dict[str, List[str]] = {}
        for i in range(0, len(artist_ids), 50):
            batch = artist_ids[i:i + 50]
            prev_level = spotipy_logger.level
            spotipy_logger.setLevel(logging.CRITICAL)
            try:
                response = self.sp._get('artists', ids=','.join(batch))
                for artist in response.get('artists') or []:
                    if artist:
                        result[artist['id']] = artist.get('genres', [])
            except Exception as e:
                # Erro inesperado - logar e relançar
                logging.error(f"Erro inesperado ao buscar gêneros: {e}")
                raise
            finally:
                spotipy_logger.setLevel(prev_level)
        return result



    def is_track_liked(self, track_id: str) -> bool:
        try:
            result = self.sp.current_user_saved_tracks_contains([track_id])
            return bool(result and result[0])
        except Exception:
            return False

    def get_playlist_track_ids(self, playlist_id: str) -> set:
        ids = set()
        try:
            offset = 0
            while True:
                result = self.sp.playlist_items(
                    playlist_id, fields="items(track(id)),next", limit=100, offset=offset
                )
                for item in result.get('items', []):
                    t = item.get('track')
                    if t and t.get('id'):
                        ids.add(t['id'])
                if not result.get('next'):
                    break
                offset += 100
        except Exception:
            pass
        return ids

    def add_track_to_playlist(self, playlist_id: str, track_id: str) -> Optional[str]:
        """
        Adiciona uma música a uma playlist ou às Músicas Curtidas (id="liked").

        Returns:
            Novo snapshot_id da playlist, "liked" para curtidas, None se erro.
        """
        try:
            if playlist_id == "liked":
                self.sp.current_user_saved_tracks_add([track_id])
                return "liked"
            result = self.sp.playlist_add_items(playlist_id, [track_id])
            return result.get('snapshot_id')
        except Exception as e:
            print(f"Erro ao adicionar música: {e}")
            return None

    # Métodos legados para compatibilidade
    def obter_musica_atual(self) -> Optional[Dict]:
        """[DEPRECATED] Use get_current_track() em vez disso."""
        track = self.get_current_track()
        if track:
            return {
                "id": track.id,
                "nome": track.nome,
                "artista": track.artista,
                "id_artista": track.id_artista
            }
        return None

    def obter_audio_features(self, track_id: str) -> Optional[Dict]:
        """[DEPRECATED] Use get_audio_features() em vez disso."""
        return self.get_audio_features(track_id)

    def obter_musicas_da_playlist(self, playlist_id: str) -> List[str]:
        """[DEPRECATED] Use SpotifyPlaylistAnalyzer.fetch_tracks() em vez disso."""
        try:
            resultados = self.sp.playlist_items(playlist_id, fields="items(track(id))")
            return [item['track']['id'] for item in resultados.get('items', []) if item.get('track')]
        except Exception:
            return []

    def adicionar_na_playlist(self, playlist_id: str, track_id: str) -> None:
        """[DEPRECATED] Use add_track_to_playlist() em vez disso."""
        self.add_track_to_playlist(playlist_id, track_id)