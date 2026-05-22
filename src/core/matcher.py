"""
Matcher baseado em Características de Áudio (Audio Features).

Utiliza features como energia, danceability, valence e tempo
para encontrar a melhor playlist usando distância euclidiana.
"""

import numpy as np
from typing import Dict, Optional
from .models import Track, MatchResult, AudioFeatures
from .matcher_base import Matcher


class VibeMatcher(Matcher):
    """
    Matcher que utiliza características de áudio para matching.
    
    Calcula o perfil médio de cada playlist usando features de áudio
    (energy, danceability, valence, tempo) e encontra a playlist
    mais próxima usando distância euclidiana.
    """
    
    def __init__(self):
        """Inicializa o matcher."""
        # Vai guardar o perfil médio de cada playlist
        # Formato: { "id_da_playlist": [media_energia, media_danceability, media_valence, media_tempo_norm] }
        self.playlist_profiles: Dict[str, np.ndarray] = {}
        self.playlist_names: Dict[str, str] = {}

    def _extract_feature_vector(self, features_dict: Dict) -> np.ndarray:
        """
        Transforma o dicionário do Spotify em um array numérico para cálculo.
        
        Args:
            features_dict: Dict com features do Spotify
            
        Returns:
            Array numpy com features normalizadas
        """
        return np.array([
            features_dict.get('energy', 0.0),
            features_dict.get('danceability', 0.0),
            features_dict.get('valence', 0.0),
            features_dict.get('tempo', 0.0) / 200.0  # Normalizando BPM para escala 0-1
        ])

    def train(self, playlist_features_data: Dict[str, list]) -> None:
        """
        Treina o matcher com dados de features de múltiplas playlists.
        
        Args:
            playlist_features_data: Dict { playlist_id: [feature_dicts] }
                Cada feature_dict tem: energy, danceability, valence, tempo, etc.
        """
        for playlist_id, features_list in playlist_features_data.items():
            if not features_list:
                continue
            
            # Extrai vetores de todas as músicas da playlist
            vectors = [
                self._extract_feature_vector(f) 
                for f in features_list 
                if f
            ]
            
            if vectors:
                # Calcula a média de cada atributo (perfil da playlist)
                self.playlist_profiles[playlist_id] = np.mean(vectors, axis=0)

    def match(self, track: Track, audio_features: Optional[dict] = None, **kwargs) -> Optional[MatchResult]:
        """
        Encontra a melhor playlist usando distância euclidiana.
        
        Args:
            track: Track object
            audio_features: Dict com features de áudio da track (obrigatório)
            **kwargs: Argumentos adicionais (não utilizados)
            
        Returns:
            MatchResult com a melhor playlist encontrada
        """
        if not audio_features:
            return None
        
        current_vector = self._extract_feature_vector(audio_features)
        
        best_playlist_id = None
        best_playlist_name = None
        min_distance = float('inf')

        for playlist_id, profile_vector in self.playlist_profiles.items():
            # Distância euclidiana entre o vetor da música e o vetor médio da playlist
            distance = np.linalg.norm(current_vector - profile_vector)
            
            if distance < min_distance:
                min_distance = distance
                best_playlist_id = playlist_id
                best_playlist_name = self.playlist_names.get(playlist_id, "Unknown")

        # Converte distância para score (quanto menor a distância, melhor)
        # Score vai de 0 a 1, onde 1 é perfeito match (distância 0)
        if best_playlist_id and min_distance < float('inf'):
            # Usa uma função de decaimento: score = e^(-distância)
            score = np.exp(-min_distance)
            
            return MatchResult(
                playlist_id=best_playlist_id,
                playlist_name=best_playlist_name,
                score=score,
                match_type='audio_features'
            )
        
        return None
    
    def train_with_names(self, playlist_data: Dict[str, dict]) -> None:
        """
        Treina o matcher com dados de playlists incluindo nomes.
        
        Args:
            playlist_data: { playlist_id: {'name': str, 'features': [feature_dicts]} }
        """
        features_data = {}
        
        for playlist_id, data in playlist_data.items():
            if 'name' in data:
                self.playlist_names[playlist_id] = data['name']
            
            if 'features' in data:
                features_data[playlist_id] = data['features']
        
        if features_data:
            self.train(features_data)
    
    def get_name(self) -> str:
        """Retorna nome do algoritmo."""
        return "Audio Features Matcher (Vibe Matcher)"