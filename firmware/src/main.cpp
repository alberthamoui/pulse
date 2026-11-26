#include <Arduino.h>
#include <LittleFS.h>
#include <WiFi.h>

#include "buttons.h"
#include "config.h"
#include "display.h"
#include "profiles.h"
#include "spotify_backend.h"
#include "spotify_client.h"
#include "state_machine.h"

#if !__has_include("secrets.h")
#error "Create include/secrets.h from include/secrets.example.h"
#endif
#include "secrets.h"

namespace {

Display display;
Buttons buttons;
SpotifyClient spotify;
Profiles profiles(spotify);
SpotifyBackend backend(spotify, profiles);
StateMachine machine(display, buttons, backend);

// Shows a message for durationMs, redrawing so long texts scroll.
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
  Serial.printf("[wifi] connecting to %s\n", secrets::WIFI_SSID);

  const uint32_t start = millis();
  while (WiFi.status() != WL_CONNECTED) {
    const uint32_t elapsed = millis() - start;
    if (elapsed >= cfg::WIFI_TIMEOUT_MS) {
      Serial.printf("[wifi] failed (status %d)\n", WiFi.status());
      return false;
    }
    // The router sometimes refuses the first attempt: retries until the timeout
    const wl_status_t status = WiFi.status();
    if (status == WL_CONNECT_FAILED || status == WL_NO_SSID_AVAIL) {
      Serial.printf("[wifi] attempt refused (status %d), retrying\n", status);
      WiFi.disconnect();
      delay(500);
      WiFi.begin(secrets::WIFI_SSID, secrets::WIFI_PASSWORD);
    }
    display.progress("Connecting Wi-Fi", elapsed * 100 / cfg::WIFI_TIMEOUT_MS);
    delay(200);
  }
  Serial.printf("[wifi] connected, IP %s, signal %d dBm\n", WiFi.localIP().toString().c_str(),
                WiFi.RSSI());
  return true;
}

// Wi-Fi, token, GET /me and profile sync (only what changed since the last boot).
void bootOnline() {
  if (!connectWifi()) {
    showMessage(errorMessage(BackendError::NoWifi), "", cfg::ERROR_MS);
    return;
  }

  display.progress("Signing in to Spotify", 50);
  SpotifyUser me;
  const BackendError err = spotify.getMe(me);
  if (err != BackendError::None) {
    showMessage(errorMessage(err), errorDetail(err), cfg::ERROR_MS);
    return;
  }

  Serial.printf("[spotify] user: %s (id %s)\n", me.displayName.c_str(), me.id.c_str());
  showMessage("Hi,", me.displayName.c_str(), cfg::GREETING_MS);

  profiles.setUserId(me.id);
  const BackendError syncErr =
      profiles.sync(false, [](uint8_t pct) { display.progress("Syncing", pct); });
  if (syncErr != BackendError::None) {
    showMessage(errorMessage(syncErr), errorDetail(syncErr), cfg::ERROR_MS);
  }
}

}  // namespace

void setup() {
  Serial.begin(115200);
  Serial.println();
  Serial.println("[pulse] boot");

  display.begin();
  buttons.begin();
  if (!LittleFS.begin(true)) Serial.println("[fs] failed to mount LittleFS");
  spotify.begin();
  profiles.begin();

  bootOnline();
  machine.begin();
}

void loop() {
  machine.tick();
  delay(1);
}
