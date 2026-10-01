#include <Arduino.h>
#include <LittleFS.h>
#include <WiFi.h>

#include "buttons.h"
#include "config.h"
#include "display.h"
#include "fake_backend.h"
#include "spotify_client.h"
#include "state_machine.h"

#if !__has_include("secrets.h")
#error "Crie include/secrets.h a partir de include/secrets.example.h"
#endif
#include "secrets.h"

namespace {

Display display;
Buttons buttons;
SpotifyClient spotify;
FakeBackend backend;
StateMachine machine(display, buttons, backend);

// Mostra uma mensagem por durationMs, redesenhando para os textos longos rolarem.
void showMessage(const char* line1, const char* line2, uint32_t durationMs) {
  const uint32_t start = millis();
  while (millis() - start < durationMs) {
    display.message(line1, line2, millis() - start);
    delay(cfg::FRAME_MS);
  }
}

bool connectWifi() {
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(secrets::WIFI_SSID, secrets::WIFI_PASSWORD);
  Serial.printf("[wifi] conectando em %s\n", secrets::WIFI_SSID);

  const uint32_t start = millis();
  while (WiFi.status() != WL_CONNECTED) {
    const uint32_t elapsed = millis() - start;
    if (elapsed >= cfg::WIFI_TIMEOUT_MS) {
      Serial.printf("[wifi] falhou (status %d)\n", WiFi.status());
      return false;
    }
    display.progress("Conectando Wi-Fi", elapsed * 100 / cfg::WIFI_TIMEOUT_MS);
    delay(200);
  }
  Serial.printf("[wifi] conectado, IP %s, sinal %d dBm\n", WiFi.localIP().toString().c_str(),
                WiFi.RSSI());
  return true;
}

// Etapa 2: Wi-Fi, renovação do token e GET /me. O resto ainda usa dados falsos.
void bootOnline() {
  if (!connectWifi()) {
    showMessage(errorMessage(BackendError::NoWifi), "", cfg::ERROR_MS);
    return;
  }

  display.progress("Entrando no Spotify", 50);
  SpotifyUser me;
  const BackendError err = spotify.getMe(me);
  if (err != BackendError::None) {
    showMessage(errorMessage(err), "", cfg::ERROR_MS);
    return;
  }

  Serial.printf("[spotify] usuario: %s (id %s)\n", me.displayName.c_str(), me.id.c_str());
  showMessage("Olá,", me.displayName.c_str(), cfg::GREETING_MS);
}

}  // namespace

void setup() {
  Serial.begin(115200);
  Serial.println();
  Serial.println("[pulse] boot (etapa 2: Wi-Fi + token + /me)");

  display.begin();
  buttons.begin();
  if (!LittleFS.begin(true)) Serial.println("[fs] falha ao montar o LittleFS");
  spotify.begin();

  bootOnline();
  machine.begin();
}

void loop() {
  machine.tick();
  delay(1);
}
