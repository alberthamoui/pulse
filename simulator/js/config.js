// Mirror of firmware/include/config.h. tests/test_simulator.py fails if they drift apart.
window.cfg = Object.freeze({
  // Buttons
  DEBOUNCE_MS: 30,
  HOLD_RESYNC_MS: 3000,

  // UI timings
  SELECT_TIMEOUT_MS: 30000,
  DONE_MS: 2000,
  ERROR_MS: 3000,
  FRAME_MS: 40,

  // Horizontal scrolling of long names
  SCROLL_PAUSE_MS: 1000,
  SCROLL_PX_PER_S: 30,

  // Ranking and profiles
  MAX_SUGGESTIONS: 5,
  PAGE_LIMIT: 50,

  // Last.fm
  LASTFM_SIMILAR_LIMIT: 50,
  LASTFM_SUGGESTIONS: 3,

  // Display
  LIST_ROWS: 4,

  // Network and Spotify
  WIFI_TIMEOUT_MS: 20000,
  GREETING_MS: 2500,
});
