#pragma once

#include <Arduino.h>

#include "config.h"

enum class ButtonEvent : uint8_t {
  None,
  NavPress,  // Navegar: dispara ao apertar
  OkClick,   // Confirmar: dispara ao soltar, se não chegou a ser um OkHold
  OkHold,    // Confirmar segurado por cfg::HOLD_RESYNC_MS
};

class Buttons {
 public:
  void begin();

  // Chamar a cada loop. Devolve no máximo um evento por chamada.
  ButtonEvent poll();

  // Ignora os botões que estão apertados agora até serem soltos. Usado depois
  // das operações bloqueantes para um aperto antigo não virar um evento novo.
  void suppressUntilRelease();

 private:
  struct Button {
    explicit Button(uint8_t p) : pin(p) {}

    uint8_t pin;
    bool raw = false;     // leitura instantânea (true = apertado)
    bool stable = false;  // estado depois do debounce
    uint32_t rawSince = 0;
    uint32_t pressedAt = 0;
    bool holdFired = false;
    bool suppressed = false;
  };

  // Atualiza o debounce. Devolve +1 ao apertar, -1 ao soltar e 0 sem mudança.
  static int8_t update(Button& b, uint32_t now);

  Button nav_{cfg::PIN_BTN_NAV};
  Button ok_{cfg::PIN_BTN_OK};
  ButtonEvent pending_ = ButtonEvent::None;
};
