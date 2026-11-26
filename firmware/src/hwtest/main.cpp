// Wiring test, independent from the rest of the firmware (env hwtest).
// - Each button lights the board's blue LED (GPIO2) while it's pressed and
//   shows up on Serial. The board LED doesn't depend on the wiring.
// - Every 2 s, until the display is found, checks the I2C lines and scans for
//   devices. You can move the wires around and see the result without rebooting.

#include <Arduino.h>
#include <Wire.h>

#include "config.h"

namespace {

constexpr uint8_t PIN_ONBOARD_LED = 2;
constexpr uint32_t PROBE_INTERVAL_MS = 2000;

// Reads the line with the internal pull-up and then with the pull-down. Returns
// nullptr if it's fine, or a description of the problem.
// - low with pull-up: the line is shorted to GND.
// - low with pull-down: there's no external pull-up, so the display isn't
//   powered or isn't connected to this line (the modules carry the pull-ups).
const char* lineProblem(uint8_t pin) {
  pinMode(pin, INPUT_PULLUP);
  delay(5);
  const bool highWithPullUp = digitalRead(pin) == HIGH;
  pinMode(pin, INPUT_PULLDOWN);
  delay(5);
  const bool externalPullUp = digitalRead(pin) == HIGH;
  pinMode(pin, INPUT);

  if (!highWithPullUp) return "stuck low (shorted to GND?)";
  if (!externalPullUp) return "no pull-up (display not powered or not on this line)";
  return nullptr;
}

// Returns a line describing the display's state.
String probeI2C(bool& found) {
  found = false;
  const char* sda = lineProblem(cfg::PIN_SDA);
  const char* scl = lineProblem(cfg::PIN_SCL);
  if (sda != nullptr || scl != nullptr) {
    String status = "[i2c]";
    if (sda != nullptr) status += String(" SDA (D21) ") + sda + ";";
    if (scl != nullptr) status += String(" SCL (D22) ") + scl;
    return status;
  }

  Wire.begin(cfg::PIN_SDA, cfg::PIN_SCL, 100000);
  String status = "[i2c] lines ok, but no device answered";
  for (uint8_t addr = 1; addr < 127; ++addr) {
    Wire.beginTransmission(addr);
    const uint8_t err = Wire.endTransmission();
    if (err == 5) {
      status = "[i2c] bus timeout: check the display wiring";
      break;
    }
    if (err == 0) {
      status = String("[i2c] device at 0x") + String(addr, HEX) +
               (addr == 0x3C || addr == 0x3D ? " (display ok)" : "");
      found = true;
      break;
    }
  }
  Wire.end();
  return status;
}

void report(const char* name, bool pressed, bool& last) {
  if (pressed == last) return;
  last = pressed;
  Serial.printf("[button] %s %s\n", name, pressed ? "pressed" : "released");
}

}  // namespace

void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println();
  Serial.println("[test] Pulse wiring");

  pinMode(PIN_ONBOARD_LED, OUTPUT);
  pinMode(cfg::PIN_BTN_NAV, INPUT_PULLUP);
  pinMode(cfg::PIN_BTN_OK, INPUT_PULLUP);

  Serial.println("[test] press the buttons: the board's blue LED lights up while one of them is pressed");
}

void loop() {
  static bool lastNav = false;
  static bool lastOk = false;
  static bool displayFound = false;
  static uint32_t lastProbe = 0;
  static String lastStatus;

  const bool nav = digitalRead(cfg::PIN_BTN_NAV) == LOW;
  const bool ok = digitalRead(cfg::PIN_BTN_OK) == LOW;

  digitalWrite(PIN_ONBOARD_LED, nav || ok ? HIGH : LOW);
  report("Navigate", nav, lastNav);
  report("Confirm", ok, lastOk);

  if (!displayFound && (lastProbe == 0 || millis() - lastProbe >= PROBE_INTERVAL_MS)) {
    lastProbe = millis();
    const String status = probeI2C(displayFound);
    if (status != lastStatus) {
      Serial.println(status);
      lastStatus = status;
    }
  }

  delay(20);  // simple debounce, enough for the test
}
