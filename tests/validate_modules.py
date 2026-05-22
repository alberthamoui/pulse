"""
Script de validação da modularização do PULSE.

Testa se todos os módulos foram criados corretamente.
"""

import sys
from pathlib import Path

# Adiciona src ao path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

def test_imports():
    """Testa se todos os módulos podem ser importados."""
    print("🧪 Testando importações...")
    print("-" * 60)
    
    tests = [
        ("core.models", ["Track", "PlaylistProfile", "MatchResult", "AudioFeatures"]),
        ("core.client", ["SpotifyManager"]),
        ("core.playlist_analyzer", ["SpotifyPlaylistAnalyzer"]),
        ("core.matcher_base", ["Matcher"]),
        ("core.artist_frequency_matcher", ["ArtistFrequencyMatcher"]),
        ("core.matcher", ["VibeMatcher"]),
        ("hardware.handler", ["ButtonListener"]),
    ]
    
    success_count = 0
    fail_count = 0
    
    for module_name, classes in tests:
        try:
            module = __import__(module_name, fromlist=classes)
            for class_name in classes:
                if hasattr(module, class_name):
                    print(f"✅ {module_name}.{class_name}")
                    success_count += 1
                else:
                    print(f"❌ {module_name}.{class_name} - NÃO ENCONTRADO")
                    fail_count += 1
        except Exception as e:
            print(f"❌ {module_name} - ERRO: {e}")
            fail_count += len(classes)
    
    print("-" * 60)
    print(f"✅ Sucesso: {success_count}")
    print(f"❌ Falhas: {fail_count}")
    
    return fail_count == 0


def test_data_models():
    """Testa se as data classes funcionam."""
    print("\n🧪 Testando data models...")
    print("-" * 60)
    
    from core.models import Track, PlaylistProfile, MatchResult
    
    # Testa Track
    track = Track(
        id="track_123",
        nome="Song Name",
        artista="Artist Name",
        id_artista="artist_456"
    )
    print(f"✅ Track criado: {track}")
    
    # Testa PlaylistProfile
    profile = PlaylistProfile(
        id="pl_789",
        nome="My Playlist",
        artista_weights={"artist_456": 0.8, "artist_789": 0.2},
        total_tracks=100
    )
    print(f"✅ PlaylistProfile criado: {profile}")
    
    # Testa MatchResult
    result = MatchResult(
        playlist_id="pl_789",
        playlist_name="My Playlist",
        score=0.85,
        match_type="artist_frequency"
    )
    print(f"✅ MatchResult criado: {result}")
    
    print("-" * 60)
    return True


def test_matcher_interface():
    """Testa se os matchers implementam a interface."""
    print("\n🧪 Testando interface Matcher...")
    print("-" * 60)
    
    from core.matcher_base import Matcher
    from core.artist_frequency_matcher import ArtistFrequencyMatcher
    from core.matcher import VibeMatcher
    
    # Verifica ArtistFrequencyMatcher
    matcher1 = ArtistFrequencyMatcher()
    assert isinstance(matcher1, Matcher), "ArtistFrequencyMatcher não herda de Matcher"
    assert hasattr(matcher1, 'train'), "ArtistFrequencyMatcher sem método train"
    assert hasattr(matcher1, 'match'), "ArtistFrequencyMatcher sem método match"
    assert hasattr(matcher1, 'get_name'), "ArtistFrequencyMatcher sem método get_name"
    print(f"✅ ArtistFrequencyMatcher implementa interface: {matcher1.get_name()}")
    
    # Verifica VibeMatcher
    matcher2 = VibeMatcher()
    assert isinstance(matcher2, Matcher), "VibeMatcher não herda de Matcher"
    assert hasattr(matcher2, 'train'), "VibeMatcher sem método train"
    assert hasattr(matcher2, 'match'), "VibeMatcher sem método match"
    assert hasattr(matcher2, 'get_name'), "VibeMatcher sem método get_name"
    print(f"✅ VibeMatcher implementa interface: {matcher2.get_name()}")
    
    print("-" * 60)
    return True


def main():
    """Executa todos os testes."""
    print("=" * 60)
    print("🎵 PULSE - Validação da Modularização")
    print("=" * 60)
    
    all_pass = True
    
    try:
        all_pass &= test_imports()
        all_pass &= test_data_models()
        all_pass &= test_matcher_interface()
    except Exception as e:
        print(f"\n❌ ERRO durante testes: {e}")
        import traceback
        traceback.print_exc()
        all_pass = False
    
    print("\n" + "=" * 60)
    if all_pass:
        print("✅ TODOS OS TESTES PASSARAM!")
        print("=" * 60)
        return 0
    else:
        print("❌ ALGUNS TESTES FALHARAM")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
