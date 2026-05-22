"""
Matcher abstrato - Interface para algoritmos de matching de músicas com playlists.
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional
from .models import Track, MatchResult


class Matcher(ABC):
    """
    Classe abstrata para algoritmos que fazem matching de músicas com playlists.
    
    Um matcher recebe uma música e retorna a melhor playlist para ela
    baseado em alguma estratégia (frequência de artistas, features de áudio, etc).
    """
    
    @abstractmethod
    def train(self, data: Dict) -> None:
        """
        Treina o matcher com dados das playlists.
        
        Args:
            data: Dados específicos do algoritmo (perfis, features, etc)
        """
        pass
    
    @abstractmethod
    def match(self, track: Track, **kwargs) -> Optional[MatchResult]:
        """
        Encontra a melhor playlist para uma faixa.
        
        Args:
            track: Objeto Track a ser matchado
            **kwargs: Argumentos adicionais específicos do algoritmo
            
        Returns:
            MatchResult com a melhor playlist encontrada, ou None se não houver match
        """
        pass
    
    @abstractmethod
    def get_name(self) -> str:
        """Retorna o nome descritivo do algoritmo."""
        pass
