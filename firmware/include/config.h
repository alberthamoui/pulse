#pragma once

#include <Arduino.h>

namespace cfg {

// Pinos
constexpr uint8_t PIN_SDA = 21;
constexpr uint8_t PIN_SCL = 22;
constexpr uint8_t PIN_BTN_NAV = 18;  // Navegar
constexpr uint8_t PIN_BTN_OK = 19;   // Confirmar

// Botões (INPUT_PULLUP, botão entre o pino e o GND)
constexpr uint32_t DEBOUNCE_MS = 30;
constexpr uint32_t HOLD_RESYNC_MS = 3000;  // segurar Confirmar no IDLE

// Tempos da interface
constexpr uint32_t SELECT_TIMEOUT_MS = 30000;
constexpr uint32_t DONE_MS = 2000;
constexpr uint32_t ERROR_MS = 3000;
constexpr uint32_t FRAME_MS = 40;  // intervalo entre quadros quando há texto rolando

// Scroll horizontal de nomes longos
constexpr uint32_t SCROLL_PAUSE_MS = 1000;
constexpr uint32_t SCROLL_PX_PER_S = 30;

// Ranking e perfis
constexpr size_t MAX_SUGGESTIONS = 5;
constexpr uint8_t PAGE_LIMIT = 50;  // máximo da API em /me/playlists e /playlists/{id}/items

// Last.fm: sem match direto, pontua as playlists pelos artistas parecidos
constexpr uint8_t LASTFM_SIMILAR_LIMIT = 50;  // artistas parecidos buscados
constexpr size_t LASTFM_SUGGESTIONS = 3;

// Display
constexpr uint32_t I2C_CLOCK_HZ = 400000;
constexpr uint8_t LIST_ROWS = 4;

// Rede e Spotify
constexpr uint32_t WIFI_TIMEOUT_MS = 20000;
constexpr uint32_t HTTP_TIMEOUT_MS = 10000;
constexpr uint32_t TOKEN_MARGIN_MS = 60000;  // renova o access token antes de expirar
constexpr uint32_t MAX_RETRY_AFTER_S = 10;   // 429: espera até isso; acima, desiste
constexpr uint32_t SYNC_MAX_RETRY_AFTER_S = 60;  // no sync dá para esperar mais
constexpr uint8_t MAX_ATTEMPTS = 3;          // por chamada, contando 401 e 429
constexpr uint32_t GREETING_MS = 2500;

}  // namespace cfg
