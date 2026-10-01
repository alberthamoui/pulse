// Teste da montagem, independente do resto do firmware (env hwtest).
// - Cada botão acende o LED azul da placa (GPIO2) enquanto estiver apertado e
//   aparece no Serial. O LED da placa não depende da montagem.
// - A cada 2 s, até achar o display, confere as linhas do I2C e procura
//   dispositivos. Dá para mexer nos fios e ver o resultado sem reiniciar.

#include <Arduino.h>
#include <Wire.h>

#include "config.h"

namespace {

constexpr uint8_t PIN_ONBOARD_LED = 2;
constexpr uint32_t PROBE_INTERVAL_MS = 2000;

// Lê a linha com o pull-up e depois com o pull-down interno. Devolve nullptr se
// ela está ok ou a descrição do problema.
// - baixo com pull-up: a linha está em curto com o GND.
// - baixo com pull-down: não há pull-up externo, ou seja, o display não está
//   alimentado ou não está ligado nessa linha (os módulos trazem os pull-ups).
const char* lineProblem(uint8_t pin) {
  pinMode(pin, INPUT_PULLUP);
  delay(5);
  const bool highWithPullUp = digitalRead(pin) == HIGH;
  pinMode(pin, INPUT_PULLDOWN);
  delay(5);
  const bool externalPullUp = digitalRead(pin) == HIGH;
  pinMode(pin, INPUT);

  if (!highWithPullUp) return "presa em baixo (curto com o GND?)";
  if (!externalPullUp) return "sem pull-up (display sem alimentacao ou fora dessa linha)";
  return nullptr;
}

// Devolve uma linha descrevendo o estado do display.
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
  String status = "[i2c] linhas ok, mas nenhum dispositivo respondeu";
  for (uint8_t addr = 1; addr < 127; ++addr) {
    Wire.beginTransmission(addr);
    const uint8_t err = Wire.endTransmission();
    if (err == 5) {
      status = "[i2c] timeout no barramento: confira as ligacoes do display";
      break;
    }
    if (err == 0) {
      status = String("[i2c] dispositivo em 0x") + String(addr, HEX) +
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
  Serial.printf("[botao] %s %s\n", name, pressed ? "apertado" : "solto");
}

}  // namespace

void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println();
  Serial.println("[teste] montagem do Pulse");

  pinMode(PIN_ONBOARD_LED, OUTPUT);
  pinMode(cfg::PIN_BTN_NAV, INPUT_PULLUP);
  pinMode(cfg::PIN_BTN_OK, INPUT_PULLUP);

  Serial.println("[teste] aperte os botoes: o LED azul da placa acende enquanto um deles estiver apertado");
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
  report("Navegar", nav, lastNav);
  report("Confirmar", ok, lastOk);

  if (!displayFound && (lastProbe == 0 || millis() - lastProbe >= PROBE_INTERVAL_MS)) {
    lastProbe = millis();
    const String status = probeI2C(displayFound);
    if (status != lastStatus) {
      Serial.println(status);
      lastStatus = status;
    }
  }

  delay(20);  // debounce simples, suficiente para o teste
}
