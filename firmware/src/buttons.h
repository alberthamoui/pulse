#pragma once

#include <Arduino.h>

#include "config.h"

enum class ButtonEvent : uint8_t {
  None,
  NavPress,  // Navigate: fires on press
  OkClick,   // Confirm: fires on release, unless it became an OkHold
  OkHold,    // Confirm held for cfg::HOLD_RESYNC_MS
};

class Buttons {
 public:
  void begin();

  // Call on every loop. Returns at most one event per call.
  ButtonEvent poll();

  // Ignores the buttons that are pressed right now until they're released. Used
  // after the blocking operations so an old press doesn't become a new event.
  void suppressUntilRelease();

 private:
  struct Button {
    explicit Button(uint8_t p) : pin(p) {}

    uint8_t pin;
    bool raw = false;     // instant reading (true = pressed)
    bool stable = false;  // state after the debounce
    uint32_t rawSince = 0;
    uint32_t pressedAt = 0;
    bool holdFired = false;
    bool suppressed = false;
  };

  // Updates the debounce. Returns +1 on press, -1 on release and 0 with no change.
  static int8_t update(Button& b, uint32_t now);

  Button nav_{cfg::PIN_BTN_NAV};
  Button ok_{cfg::PIN_BTN_OK};
  ButtonEvent pending_ = ButtonEvent::None;
};
