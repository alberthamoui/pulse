// The part of U8g2 that display.cpp uses: a 128x64 frame buffer, the font decoder and
// the drawing calls. The fonts are U8g2's own bytes (js/fonts.js), decoded with the same
// algorithm as u8g2_font.c, so the text lands on the same pixels as on the OLED.
(function () {
  'use strict';

  const WIDTH = 128;
  const HEIGHT = 64;
  const FONT_HEADER_SIZE = 23; // U8G2_FONT_DATA_STRUCT_SIZE

  function base64Bytes(text) {
    const raw = atob(text);
    const out = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
    return out;
  }

  // u8g2_font_decode_get_unsigned_bits / _signed_bits: LSB first, across byte borders
  class BitReader {
    constructor(data, pos) {
      this.data = data;
      this.pos = pos;
      this.bit = 0;
    }

    unsigned(cnt) {
      let val = this.data[this.pos] >> this.bit;
      let end = this.bit + cnt;
      if (end >= 8) {
        this.pos++;
        val |= this.data[this.pos] << (8 - this.bit);
        end -= 8;
      }
      this.bit = end;
      return val & ((1 << cnt) - 1);
    }

    signed(cnt) {
      return this.unsigned(cnt) - (1 << (cnt - 1));
    }
  }

  class Font {
    constructor(bytes) {
      const d = bytes;
      this.bitsPer0 = d[2];
      this.bitsPer1 = d[3];
      this.bitsW = d[4];
      this.bitsH = d[5];
      this.bitsX = d[6];
      this.bitsY = d[7];
      this.bitsDx = d[8];
      this.data = d;

      // Glyphs up to 255: [encoding][size of this entry][bit stream], until a size of 0
      this.offsets = new Map();
      for (let p = FONT_HEADER_SIZE; p + 1 < d.length && d[p + 1] !== 0; p += d[p + 1]) {
        this.offsets.set(d[p], p + 2);
      }
      this.cache = new Map();
    }

    // { w, h, x, y, dx, px } or null when the font has no glyph for the code point
    glyph(code) {
      if (this.cache.has(code)) return this.cache.get(code);
      const offset = code <= 255 ? this.offsets.get(code) : undefined;
      const glyph = offset === undefined ? null : this.decode(offset);
      this.cache.set(code, glyph);
      return glyph;
    }

    // u8g2_font_decode_glyph: run-length encoded rows of 0s and 1s
    decode(offset) {
      const r = new BitReader(this.data, offset);
      const w = r.unsigned(this.bitsW);
      const h = r.unsigned(this.bitsH);
      const x = r.signed(this.bitsX);
      const y = r.signed(this.bitsY);
      const dx = r.signed(this.bitsDx);
      const px = new Uint8Array(w * h);

      if (w > 0) {
        let lx = 0;
        let ly = 0;
        // u8g2_font_decode_len
        const run = (len, on) => {
          let cnt = len;
          for (;;) {
            const rem = w - lx;
            const current = cnt < rem ? cnt : rem;
            if (on) for (let i = 0; i < current; i++) if (ly < h) px[ly * w + lx + i] = 1;
            if (cnt < rem) break;
            cnt -= rem;
            lx = 0;
            ly++;
          }
          lx += cnt;
        };
        for (;;) {
          const zeros = r.unsigned(this.bitsPer0);
          const ones = r.unsigned(this.bitsPer1);
          do {
            run(zeros, false);
            run(ones, true);
          } while (r.unsigned(1) !== 0);
          if (ly >= h) break;
        }
      }
      return { w, h, x, y, dx, px };
    }
  }

  const fonts = {};
  for (const [name, data] of Object.entries(window.U8G2_FONT_DATA)) {
    fonts[name] = new Font(base64Bytes(data));
  }

  class U8G2 {
    constructor() {
      this.buffer = new Uint8Array(WIDTH * HEIGHT);
      this.font = null;
      this.drawColor = 1;
      this.fontMode = 0;
      this.setMaxClipWindow();
      this.onSendBuffer = null;
    }

    clearBuffer() { this.buffer.fill(0); }

    sendBuffer() { if (this.onSendBuffer) this.onSendBuffer(this.buffer); }

    setFont(name) { this.font = fonts[name]; }

    setDrawColor(color) { this.drawColor = color; }

    setFontMode(mode) { this.fontMode = mode; }

    setClipWindow(x0, y0, x1, y1) { this.clip = { x0, y0, x1, y1 }; }

    setMaxClipWindow() { this.clip = { x0: 0, y0: 0, x1: WIDTH, y1: HEIGHT }; }

    pixel(x, y, color) {
      const c = this.clip;
      if (x < c.x0 || x >= c.x1 || y < c.y0 || y >= c.y1) return;
      if (x < 0 || x >= WIDTH || y < 0 || y >= HEIGHT) return;
      const i = y * WIDTH + x;
      this.buffer[i] = color === 2 ? this.buffer[i] ^ 1 : color;
    }

    drawBox(x, y, w, h) {
      for (let j = 0; j < h; j++) for (let i = 0; i < w; i++) this.pixel(x + i, y + j, this.drawColor);
    }

    drawHLine(x, y, w) { this.drawBox(x, y, w, 1); }

    drawVLine(x, y, h) { this.drawBox(x, y, 1, h); }

    drawFrame(x, y, w, h) {
      this.drawHLine(x, y, w);
      this.drawHLine(x, y + h - 1, w);
      this.drawVLine(x, y, h);
      this.drawVLine(x + w - 1, y, h);
    }

    // y is the baseline. Returns the advance (0 for a glyph the font doesn't have).
    drawGlyph(x, y, code) {
      const g = this.font.glyph(code);
      if (!g) return 0;
      if (g.w > 0) {
        const top = y - (g.h + g.y);
        const left = x + g.x;
        const bg = this.drawColor === 0 ? 1 : 0;
        for (let j = 0; j < g.h; j++) {
          for (let i = 0; i < g.w; i++) {
            if (g.px[j * g.w + i]) this.pixel(left + i, top + j, this.drawColor);
            else if (this.fontMode === 0) this.pixel(left + i, top + j, bg);
          }
        }
      }
      return g.dx;
    }

    drawUTF8(x, y, text) {
      let width = 0;
      for (const ch of text) {
        const dx = this.drawGlyph(x, y, ch.codePointAt(0));
        x += dx;
        width += dx;
      }
      return width;
    }

    drawStr(x, y, text) { return this.drawUTF8(x, y, text); }

    // u8g2_string_width with U8G2_BALANCED_STR_WIDTH_CALCULATION (the default in 2.35)
    getUTF8Width(text) {
      let w = 0;
      let dx = 0;
      let glyphWidth = 0;
      let xOffset = 0;
      let initialXOffset = -64;
      for (const ch of text) {
        const g = this.font.glyph(ch.codePointAt(0));
        if (!g) {
          dx = 0;
          continue;
        }
        dx = g.dx;
        glyphWidth = g.w;
        xOffset = g.x;
        if (initialXOffset === -64) initialXOffset = xOffset;
        w += dx;
      }
      if (glyphWidth !== 0) {
        w = w - dx + glyphWidth + xOffset;
        if (initialXOffset > 0) w += initialXOffset;
      }
      return w;
    }

    getStrWidth(text) { return this.getUTF8Width(text); }
  }

  window.U8G2 = U8G2;
  window.OLED_WIDTH = WIDTH;
  window.OLED_HEIGHT = HEIGHT;
})();
