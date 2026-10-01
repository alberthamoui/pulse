#include <Arduino.h>

#include "buttons.h"
#include "display.h"
#include "fake_backend.h"
#include "state_machine.h"

namespace {

Display display;
Buttons buttons;
FakeBackend backend;
StateMachine machine(display, buttons, backend);

}  // namespace

void setup() {
  Serial.begin(115200);
  Serial.println();
  Serial.println("[pulse] boot (etapa 1: dados falsos)");

  display.begin();
  buttons.begin();
  machine.begin();
}

void loop() {
  machine.tick();
  delay(1);
}
