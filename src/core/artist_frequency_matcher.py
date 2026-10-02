"""
Matcher baseado em Frequência Relativa de Artistas.

Algoritmo base, mais simples que o HybridMatcher:
- Cada playlist tem um perfil { id_artista: peso_relativo }
- Uma música é alocada na playlist onde seu artista tem maior peso
"""

from typing import Dict, Optional
from .models import Track, PlaylistProfile, MatchResult
from .matcher_base import Matcher


class ArtistFrequencyMatcher(Matcher):
    """
    Matcher que utiliza a frequência relativa de artistas em cada playlist.
    
    O algoritmo é simples e rápido: busca em qual playlist o artista
    da música tocando tem o maior peso (frequência relativa).
    """
    
    def __init__(self):
        """Inicializa o matcher."""
        self.profiles: Dict[str, PlaylistProfile] = {}
    
    def train(self, profiles: Dict[str, PlaylistProfile]) -> None:
        """
        Treina o matcher com os perfis de playlists.
        
        Args:
            profiles: Dict mapeando playlist_id → PlaylistProfile
        """
        self.profiles = profiles
    
    def match(self, track: Track, **kwargs) -> Optional[MatchResult]:
        """
        Encontra a melhor playlist baseado na frequência do artista.
        
        Args:
            track: Track com id_artista preenchido
            **kwargs: Argumentos adicionais (não utilizados neste matcher)
            
        Returns:
            MatchResult com a melhor playlist, ou None se artista não encontrado
        """
        if not track.id_artista:
            return None
        
        best_playlist_id = None
        best_playlist_name = None
        best_score = 0.0
        
        # Procura em qual playlist este artista tem maior peso
        for playlist_id, profile in self.profiles.items():
            artist_weight = profile.artista_weights.get(track.id_artista, 0.0)
            
            if artist_weight > best_score:
                best_score = artist_weight
                best_playlist_id = playlist_id
                best_playlist_name = profile.nome
        
        if best_playlist_id and best_score > 0:
            return MatchResult(
                playlist_id=best_playlist_id,
                playlist_name=best_playlist_name,
                score=best_score,
                match_type='artist_frequency'
            )
        
        return None
    
    def get_name(self) -> str:
        """Retorna nome do algoritmo."""
        return "Artist Frequency Matcher"
    
    def get_artist_stats(self, playlist_id: str) -> Dict[str, float]:
        """
        Retorna estatísticas de artistas de uma playlist.
        
        Args:
            playlist_id: ID da playlist
            
        Returns:
            Dict com artistas ordenados por peso decrescente
        """
        if playlist_id not in self.profiles:
            return {}
        
        profile = self.profiles[playlist_id]
        # Ordena artistas por peso (maior primeiro)
        return dict(sorted(
            profile.artista_weights.items(),
            key=lambda x: x[1],
            reverse=True
        ))
