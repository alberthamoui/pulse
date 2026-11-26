#pragma once

#include <Arduino.h>
#include <U8g2lib.h>

#include <vector>

#include "backend.h"
#include "config.h"

class Display {
 public:
  void begin();

  void idle();
  void progress(const char* label, uint8_t pct);

  // Choice screen. elapsedMs counts from the last selection change and drives
  // the scrolling of long names. Returns true if some text is scrolling, that
  // is, if the screen needs to be redrawn periodically.
  bool select(const NowPlaying& track, const std::vector<Candidate>& items, bool manual,
              size_t selected, size_t first, uint32_t elapsedMs);

  // Centered message in up to two lines (the second one scrolls if it doesn't fit).
  bool message(const char* line1, const char* line2, uint32_t elapsedMs);

 private:
  // Draws text in the band [x, x + w) with the baseline at y. If it doesn't fit,
  // clips to [top, bottom) and, with scroll = true, scrolls based on elapsedMs.
  bool drawClipped(int x, int y, int w, int top, int bottom, const char* text, bool scroll,
                   uint32_t elapsedMs);

  U8G2_SH1106_128X64_NONAME_F_HW_I2C u8g2_{U8G2_R0, U8X8_PIN_NONE, cfg::PIN_SCL, cfg::PIN_SDA};
};
