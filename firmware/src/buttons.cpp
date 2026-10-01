#include "buttons.h"

void Buttons::begin() {
  pinMode(nav_.pin, INPUT_PULLUP);
  pinMode(ok_.pin, INPUT_PULLUP);
  suppressUntilRelease();
}

int8_t Buttons::update(Button& b, uint32_t now) {
  const bool raw = digitalRead(b.pin) == LOW;
  if (raw != b.raw) {
    b.raw = raw;
    b.rawSince = now;
  }
  if (now - b.rawSince < cfg::DEBOUNCE_MS) return 0;

  if (b.raw == b.stable) {
    // Solto e estável: libera uma supressão que ficou pendurada por ruído.
    if (!b.stable) b.suppressed = false;
    return 0;
  }

  b.stable = b.raw;
  if (b.stable) {
    b.pressedAt = now;
    b.holdFired = false;
    return 1;
  }
  return -1;
}

ButtonEvent Buttons::poll() {
  if (pending_ != ButtonEvent::None) {
    const ButtonEvent ev = pending_;
    pending_ = ButtonEvent::None;
    return ev;
  }

  const uint32_t now = millis();
  ButtonEvent navEv = ButtonEvent::None;
  ButtonEvent okEv = ButtonEvent::None;

  int8_t edge = update(nav_, now);
  if (edge > 0 && !nav_.suppressed) navEv = ButtonEvent::NavPress;
  if (edge < 0) nav_.suppressed = false;

  edge = update(ok_, now);
  if (edge < 0) {
    if (!ok_.suppressed && !ok_.holdFired) okEv = ButtonEvent::OkClick;
    ok_.suppressed = false;
  } else if (ok_.stable && !ok_.suppressed && !ok_.holdFired &&
             now - ok_.pressedAt >= cfg::HOLD_RESYNC_MS) {
    ok_.holdFired = true;
    okEv = ButtonEvent::OkHold;
  }

  if (navEv != ButtonEvent::None) {
    pending_ = okEv;
    return navEv;
  }
  return okEv;
}

void Buttons::suppressUntilRelease() {
  for (Button* b : {&nav_, &ok_}) {
    b->suppressed = b->stable || digitalRead(b->pin) == LOW;
  }
  pending_ = ButtonEvent::None;
}
