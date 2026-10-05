#pragma once

#include <Arduino.h>

#include <vector>

#include "buttons.h"
#include "display.h"
#include "spotify_backend.h"

enum class State : uint8_t { Idle, Loading, Select, Done, Error };

class StateMachine {
 public:
  StateMachine(Display& display, Buttons& buttons, SpotifyBackend& backend)
      : display_(display), buttons_(buttons), backend_(backend) {}

  void begin();
  void tick();

 private:
  // Transitions. The network operations block and draw the progress bar.
  void enter(State next);
  void enterIdle();
  void enterError(BackendError err);
  void loadNowPlaying();
  void confirmSelection();
  void resync();

  void moveSelection();
  void render(uint32_t now);

  Display& display_;
  Buttons& buttons_;
  SpotifyBackend& backend_;

  State state_ = State::Idle;
  uint32_t stateSince_ = 0;
  uint32_t lastInput_ = 0;    // SELECT: timeout base
  uint32_t scrollStart_ = 0;  // horizontal scroll base

  NowPlaying track_;
  std::vector<Candidate> candidates_;
  bool manual_ = false;
  size_t selected_ = 0;
  size_t first_ = 0;  // first visible row of the list

  String line1_;  // DONE / ERROR texts
  String line2_;

  bool dirty_ = true;
  bool animating_ = false;
  uint32_t lastFrame_ = 0;
};
