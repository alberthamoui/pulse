#include "display.h"

namespace {

const uint8_t* const FONT_BIG = u8g2_font_logisoso24_tr;
const uint8_t* const FONT_TEXT = u8g2_font_6x10_tf;  // _tf: inclui Latin-1 (acentos)
const uint8_t* const FONT_SMALL = u8g2_font_5x7_tf;

constexpr int WIDTH = 128;
constexpr int ROW_H = 10;
constexpr int LIST_TOP = 21;
constexpr int SCROLLBAR_W = 3;

// Deslocamento do scroll: pausa no início, rola até o fim, pausa e recomeça.
int marqueeOffset(int overflow, uint32_t elapsedMs) {
  const uint32_t scrollMs = overflow * 1000UL / cfg::SCROLL_PX_PER_S;
  const uint32_t cycle = cfg::SCROLL_PAUSE_MS + scrollMs + cfg::SCROLL_PAUSE_MS;
  uint32_t t = elapsedMs % cycle;
  if (t < cfg::SCROLL_PAUSE_MS) return 0;
  t -= cfg::SCROLL_PAUSE_MS;
  if (t < scrollMs) return t * cfg::SCROLL_PX_PER_S / 1000;
  return overflow;
}

}  // namespace

void Display::begin() {
  u8g2_.setBusClock(cfg::I2C_CLOCK_HZ);
  u8g2_.begin();
  u8g2_.enableUTF8Print();
  u8g2_.setFontMode(1);  // fundo transparente, para escrever sobre a linha invertida
}

bool Display::drawClipped(int x, int y, int w, int top, int bottom, const char* text,
                          bool scroll, uint32_t elapsedMs) {
  const int overflow = u8g2_.getUTF8Width(text) - w;
  if (overflow <= 0) {
    u8g2_.drawUTF8(x, y, text);
    return false;
  }
  const int offset = scroll ? marqueeOffset(overflow, elapsedMs) : 0;
  u8g2_.setClipWindow(x, top, x + w, bottom);
  u8g2_.drawUTF8(x - offset, y, text);
  u8g2_.setMaxClipWindow();
  return scroll;
}

void Display::idle() {
  u8g2_.clearBuffer();
  u8g2_.setFont(FONT_BIG);
  const char* title = "PULSE";
  const int x = (WIDTH - u8g2_.getStrWidth(title)) / 2;
  u8g2_.drawStr(x, 44, title);
  u8g2_.sendBuffer();
}

void Display::progress(const char* label, uint8_t pct) {
  if (pct > 100) pct = 100;
  u8g2_.clearBuffer();
  u8g2_.setFont(FONT_TEXT);
  u8g2_.drawUTF8((WIDTH - u8g2_.getUTF8Width(label)) / 2, 26, label);
  u8g2_.drawFrame(14, 34, 100, 10);
  u8g2_.drawBox(16, 36, 96 * pct / 100, 6);
  u8g2_.sendBuffer();
}

bool Display::select(const NowPlaying& track, const std::vector<Candidate>& items, bool manual,
                     size_t selected, size_t first, uint32_t elapsedMs) {
  bool animating = false;
  u8g2_.clearBuffer();

  // Cabeçalho: música e artista rolam juntos, no mesmo relógio da seleção
  u8g2_.setFont(FONT_TEXT);
  animating |= drawClipped(0, 8, WIDTH, 0, 10, track.name.c_str(), true, elapsedMs);
  u8g2_.setFont(FONT_SMALL);
  animating |= drawClipped(0, 17, WIDTH, 10, 18, track.artistName.c_str(), true, elapsedMs);
  u8g2_.drawHLine(0, 19, WIDTH);

  const bool hasScrollbar = items.size() > cfg::LIST_ROWS;
  const int rowW = hasScrollbar ? WIDTH - SCROLLBAR_W : WIDTH;

  u8g2_.setFont(FONT_TEXT);
  for (size_t i = 0; i < cfg::LIST_ROWS && first + i < items.size(); ++i) {
    const size_t idx = first + i;
    const Candidate& item = items[idx];
    const bool isSel = idx == selected;
    const int top = LIST_TOP + i * ROW_H;
    const int baseline = top + 8;

    if (isSel) {
      u8g2_.drawBox(0, top, rowW, ROW_H);
      u8g2_.setDrawColor(0);
    }

    // Coluna da direita: "já" se a música já está na playlist, senão o peso
    // (só nas sugestões; Fallback e Cancelar não têm peso)
    int nameW = rowW - 4;
    char tag[6] = "";
    if (item.hasTrack) {
      snprintf(tag, sizeof(tag), "já");
    } else if (!manual && item.kind == Candidate::Kind::Playlist) {
      const int p = static_cast<int>(item.weight * 100.0f + 0.5f);
      if (p < 1) {
        snprintf(tag, sizeof(tag), "<1%%");
      } else {
        snprintf(tag, sizeof(tag), "%d%%", p);
      }
    }
    if (tag[0] != '\0') {
      const int tagW = u8g2_.getUTF8Width(tag);
      u8g2_.drawUTF8(rowW - 2 - tagW, baseline, tag);
      nameW -= tagW + 4;
    }
    animating |= drawClipped(2, baseline, nameW, top, top + ROW_H, item.name.c_str(), isSel,
                             elapsedMs);
    u8g2_.setDrawColor(1);
  }

  if (hasScrollbar) {
    const int trackH = cfg::LIST_ROWS * ROW_H;
    const int thumbH = max(3, static_cast<int>(trackH * cfg::LIST_ROWS / items.size()));
    const int thumbY =
        LIST_TOP + (trackH - thumbH) * static_cast<int>(first) /
                       static_cast<int>(items.size() - cfg::LIST_ROWS);
    u8g2_.drawBox(WIDTH - 2, thumbY, 2, thumbH);
  }

  u8g2_.sendBuffer();
  return animating;
}

bool Display::message(const char* line1, const char* line2, uint32_t elapsedMs) {
  bool animating = false;
  u8g2_.clearBuffer();
  u8g2_.setFont(FONT_TEXT);

  auto centered = [&](const char* text, int y) {
    const int w = u8g2_.getUTF8Width(text);
    if (w <= WIDTH - 4) {
      u8g2_.drawUTF8((WIDTH - w) / 2, y, text);
    } else {
      animating |= drawClipped(2, y, WIDTH - 4, y - 9, y + 2, text, true, elapsedMs);
    }
  };

  const bool twoLines = line2 != nullptr && *line2 != '\0';
  centered(line1, twoLines ? 26 : 36);
  if (twoLines) centered(line2, 44);

  u8g2_.sendBuffer();
  return animating;
}
