"""
Pulse core: everything except the command line (main.py).

    user_config        config/settings.py and config/config.json
    client             Spotify API calls
    playlist_analyzer  reads the playlists and builds their profiles
    cache              keeps the profiles between runs
    matcher            ranks the playlists for a song (+ Last.fm fallback)
    lastfm_client      similar artists from Last.fm
    models             Track, PlaylistProfile, MatchResult
    constants          tuning knobs
"""
