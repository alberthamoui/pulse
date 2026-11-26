# Pulse simulator

Try the Pulse device without the hardware. The firmware runs in the browser, with a simulated Spotify behind it: you pick the song that's "playing", press the buttons and watch the same screens, rankings and Serial log the ESP32 would produce.

Two models, same firmware:

- **Prototype**: the breadboard from [docs/device.jpeg](../docs/device.jpeg), with the green Navigate and white Confirm buttons.
- **Final product**: a concept for a 3D-printed case. It's a wedge that tilts the screen towards you, with two caps under it and USB-C at the back. Drag it to turn it, double-click to reset the view, and pick the filament color. The render isn't to scale: the screen is enlarged so it's readable.

## Running it

Open `simulator/index.html` in a browser. There's no build step and nothing to install. If your browser blocks pages opened from disk, serve the folder instead:

```bash
python -m http.server 8000 --directory simulator
# then open http://127.0.0.1:8000
```

| Control | What it does |
|---|---|
| Green button, <kbd>N</kbd> or <kbd>↓</kbd> | Navigate: on `PULSE` looks up the song, on the list moves to the next option |
| White button, <kbd>O</kbd> or <kbd>Enter</kbd> | Confirm: on `PULSE` looks up the song, on the list adds to the selected playlist |
| Hold Confirm 3 s on `PULSE` | Re-syncs every playlist |

The panel on the right is the outside world. You can:

- Change the song playing. Each one hits a different path: ranking, the `in` mark, Last.fm `~` suggestions, the manual list, a local file, a podcast.
- Turn Wi-Fi off, make the Spotify API rate-limit or revoke the token.
- Turn the Last.fm key or the fallback playlist off.
- "Edit one from your phone", then restart the device and watch only that playlist get re-read.

Your library and the device's flash are kept in `localStorage`, so a reload works like a reboot. **Factory reset** clears both.

## How faithful it is

The `js/firmware.js` file is a line-by-line port of `firmware/src`:

| Firmware | Simulator |
|---|---|
| `buttons.cpp` | `Buttons`: 30 ms debounce, click on release, hold for 3 s, presses ignored until release after a blocking call |
| `display.cpp` | `Display`: the same layout, scrolling and integer math |
| `state_machine.cpp` | `StateMachine`: IDLE → LOADING → SELECT → DONE / ERROR, 30 s timeout |
| `profiles.cpp` | `Profiles`: snapshot-based sync, direct weight `n / total`, Last.fm `sum(match * tf * idf)` in 32-bit float |
| `spotify_backend.cpp` | `SpotifyBackend`: Fallback and Cancel placement, manual alphabetical list |
| `main.cpp` | `Device`: Wi-Fi, sign-in, greeting and sync at boot |

The text on the screen is drawn with U8g2's own font data. `tools/extract_u8g2_fonts.py` copies the bytes of the three fonts `display.cpp` uses into `js/fonts.js`, and `js/u8g2.js` decodes them with the same algorithm as `u8g2_font.c`, so every glyph lands on the same pixels as on the OLED.

`tests/test_simulator.py` fails if the timings and limits in `js/config.js` drift from `firmware/include/config.h`, or if `display.cpp` starts using a font the simulator doesn't have.

What's simulated rather than ported: Wi-Fi, HTTPS and the Spotify and Last.fm APIs (`js/cloud.js`, with made-up playlists in `js/library.js`), and the 429 handling, which gives up immediately instead of waiting.

## Files

```
index.html          the page: both models, the panel and the Serial monitor
css/style.css       the look, including the CSS 3D case
js/fonts.js         U8g2 font data (generated, don't edit)
js/u8g2.js          the slice of U8g2 that display.cpp uses
js/config.js        mirror of firmware/include/config.h
js/library.js       example playlists, songs and similar artists
js/cloud.js         simulated Wi-Fi, Spotify and Last.fm
js/firmware.js      the firmware port
js/app.js           wires the device to the page
```
