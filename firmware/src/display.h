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

  // Tela de escolha. elapsedMs conta desde a última mudança de seleção e
  // controla o scroll dos nomes longos. Devolve true se algum texto está
  // rolando, ou seja, se a tela precisa ser redesenhada periodicamente.
  bool select(const NowPlaying& track, const std::vector<Candidate>& items, bool manual,
              size_t selected, size_t first, uint32_t elapsedMs);

  // Mensagem centralizada em até duas linhas (a segunda rola se não couber).
  bool message(const char* line1, const char* line2, uint32_t elapsedMs);

 private:
  // Desenha text na faixa [x, x + w) com a baseline em y. Se não couber, corta
  // na faixa [top, bottom) e, com scroll = true, rola de acordo com elapsedMs.
  bool drawClipped(int x, int y, int w, int top, int bottom, const char* text, bool scroll,
                   uint32_t elapsedMs);

  U8G2_SH1106_128X64_NONAME_F_HW_I2C u8g2_{U8G2_R0, U8X8_PIN_NONE, cfg::PIN_SCL, cfg::PIN_SDA};
};
