#pragma once

#include <Arduino.h>

namespace cfg {

// Pins
constexpr uint8_t PIN_SDA = 21;
constexpr uint8_t PIN_SCL = 22;
constexpr uint8_t PIN_BTN_NAV = 18;  // Navigate
constexpr uint8_t PIN_BTN_OK = 19;   // Confirm

// Buttons (INPUT_PULLUP, button between the pin and GND)
constexpr uint32_t DEBOUNCE_MS = 30;
constexpr uint32_t HOLD_RESYNC_MS = 3000;  // hold Confirm on IDLE

// UI timings
constexpr uint32_t SELECT_TIMEOUT_MS = 30000;
constexpr uint32_t DONE_MS = 2000;
constexpr uint32_t ERROR_MS = 3000;
constexpr uint32_t FRAME_MS = 40;  // interval between frames while text is scrolling

// Horizontal scrolling of long names
constexpr uint32_t SCROLL_PAUSE_MS = 1000;
constexpr uint32_t SCROLL_PX_PER_S = 30;

// Ranking and profiles
constexpr size_t MAX_SUGGESTIONS = 5;
constexpr uint8_t PAGE_LIMIT = 50;  // API maximum for /me/playlists and /playlists/{id}/items

// Last.fm: with no direct match, scores the playlists through similar artists
constexpr uint8_t LASTFM_SIMILAR_LIMIT = 50;  // similar artists fetched
constexpr size_t LASTFM_SUGGESTIONS = 3;

// Display
constexpr uint32_t I2C_CLOCK_HZ = 400000;
constexpr uint8_t LIST_ROWS = 4;

// Network and Spotify
constexpr uint32_t WIFI_TIMEOUT_MS = 20000;
constexpr uint32_t HTTP_TIMEOUT_MS = 10000;
constexpr uint32_t TOKEN_MARGIN_MS = 60000;  // refreshes the access token before it expires
constexpr uint32_t MAX_RETRY_AFTER_S = 10;   // 429: waits up to this; above it, gives up
constexpr uint32_t SYNC_MAX_RETRY_AFTER_S = 60;  // the sync can wait longer
constexpr uint8_t MAX_ATTEMPTS = 3;          // per call, counting 401 and 429
constexpr uint32_t GREETING_MS = 2500;

}  // namespace cfg
