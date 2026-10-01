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

// Ranking
constexpr size_t MAX_SUGGESTIONS = 5;

// Display
constexpr uint32_t I2C_CLOCK_HZ = 400000;
constexpr uint8_t LIST_ROWS = 4;

}  // namespace cfg
