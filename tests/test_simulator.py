"""The browser simulator mirrors the firmware: these fail when one changes without the other."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_H = ROOT / "firmware/include/config.h"
DISPLAY_CPP = ROOT / "firmware/src/display.cpp"
SIM_CONFIG = ROOT / "simulator/js/config.js"
SIM_FONTS = ROOT / "simulator/js/fonts.js"


def firmware_constants():
    text = CONFIG_H.read_text(encoding="utf-8")
    return {name: int(value) for name, value in re.findall(r"constexpr \w+ (\w+) = (\d+);", text)}


def simulator_constants():
    text = SIM_CONFIG.read_text(encoding="utf-8")
    return {name: int(value) for name, value in re.findall(r"^\s*(\w+): (\d+),", text, re.MULTILINE)}


def test_simulator_timings_and_limits_match_config_h():
    firmware = firmware_constants()
    simulator = simulator_constants()

    assert simulator, "no constants found in simulator/js/config.js"
    for name, value in simulator.items():
        assert name in firmware, f"{name} is in the simulator but not in config.h"
        assert value == firmware[name], f"{name}: config.h has {firmware[name]}, the simulator {value}"


def test_simulator_has_the_ui_constants_of_config_h():
    # Pins and network details don't apply in the browser; everything the screens use does
    not_simulated = {"PIN_SDA", "PIN_SCL", "PIN_BTN_NAV", "PIN_BTN_OK", "I2C_CLOCK_HZ", "HTTP_TIMEOUT_MS",
                     "TOKEN_MARGIN_MS", "MAX_RETRY_AFTER_S", "SYNC_MAX_RETRY_AFTER_S", "MAX_ATTEMPTS"}
    missing = firmware_constants().keys() - simulator_constants().keys() - not_simulated
    assert not missing, f"add to simulator/js/config.js: {sorted(missing)}"


def test_simulator_has_every_font_the_display_uses():
    used = set(re.findall(r"u8g2_font_\w+", DISPLAY_CPP.read_text(encoding="utf-8")))
    bundled = set(re.findall(r"^\s*(u8g2_font_\w+):", SIM_FONTS.read_text(encoding="utf-8"), re.MULTILINE))
    assert used <= bundled, f"run tools/extract_u8g2_fonts.py for {sorted(used - bundled)}"
