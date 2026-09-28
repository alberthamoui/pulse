"""
Data models para o projeto PULSE.

Define as estruturas de dados utilizadas em toda a aplicação.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List


@dataclass
class Track:
    """Representa uma faixa de música do Spotify."""
    id: str
    nome: str
    artista: str = ""
    id_artista: Optional[str] = None
    artistas: List[str] = field(default_factory=list)
    artistas_nomes: List[str] = field(default_factory=list)

    def __repr__(self) -> str:
        return f"Track(nome={self.nome!r}, artista={self.artista!r})"


@dataclass
class PlaylistProfile:
    """Perfil de uma playlist baseado em análise de conteúdo."""
    id: str
    nome: str
    artista_weights: Dict[str, float]  # { id_artista: peso_relativo }
    genre_weights: Dict[str, float] = field(default_factory=dict)  # { genre: peso_relativo }
    total_tracks: int = 0
    track_ids: list = field(default_factory=list)

    def __repr__(self) -> str:
        return f"PlaylistProfile(nome={self.nome!r}, artistas={len(self.artista_weights)}, genres={len(self.genre_weights)})"


@dataclass
class MatchResult:
    """Resultado de uma operação de matching entre música e playlist."""
    playlist_id: str
    playlist_name: str
    score: float  # 0.0 a 1.0
    match_type: str  # 'artist_frequency' ou 'audio_features'
    reason: str = ""

    def __repr__(self) -> str:
        return f"MatchResult({self.playlist_name!r}, score={self.score:.2%})"


@dataclass
class AudioFeatures:
    """Features de áudio extraídas do Spotify Audio Analysis API."""
    track_id: str
    energy: float
    danceability: float
    valence: float
    tempo: float
    acousticness: Optional[float] = None
    instrumentalness: Optional[float] = None
    liveness: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário (compatível com API do Spotify)."""
        return {
            'id': self.track_id,
            'energy': self.energy,
            'danceability': self.danceability,
            'valence': self.valence,
            'tempo': self.tempo,
            'acousticness': self.acousticness,
            'instrumentalness': self.instrumentalness,
            'liveness': self.liveness,
        }
