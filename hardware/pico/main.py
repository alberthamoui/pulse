from machine import Pin, I2C
import ssd1306
import time
from constants import (
    PIN_TRIGGER, PIN_CYCLE, PIN_CONFIRM, PIN_LED,
    PIN_SDA, PIN_SCL, I2C_ID, I2C_FREQ, OLED_WIDTH, OLED_HEIGHT,
    DEBOUNCE_DELAY, NAV_DELAY, BLINK_DELAY, SUCCESS_HOLD,
    PROCESSING_DELAY, SAVE_DELAY, CANCEL_DELAY, CONFIRM_DELAY,
)

btn_trigger = Pin(PIN_TRIGGER, Pin.IN, Pin.PULL_UP)
btn_cycle   = Pin(PIN_CYCLE,   Pin.IN, Pin.PULL_UP)
btn_confirm = Pin(PIN_CONFIRM, Pin.IN, Pin.PULL_UP)
led         = Pin(PIN_LED, Pin.OUT)
i2c         = I2C(I2C_ID, sda=Pin(PIN_SDA), scl=Pin(PIN_SCL), freq=I2C_FREQ)
oled        = ssd1306.SSD1306_I2C(OLED_WIDTH, OLED_HEIGHT, i2c)

PLAYLISTS = ["afternoon", "workout", "late night", "chill", "focus"]

state      = "idle"   # idle | selecting | processing
sel_index  = 0
musica     = ""

def show(l1="", l2="", l3="", l4=""):
    oled.fill(0)
    oled.text(l1, 0,  0)
    oled.text(l2, 0, 16)
    oled.text(l3, 0, 32)
    oled.text(l4, 0, 48)
    oled.show()

def blink(n, delay=BLINK_DELAY):
    for _ in range(n):
        led.on();  time.sleep(delay)
        led.off(); time.sleep(delay)

def pressed(pin):
    return pin.value() == 0

show("PULSE", "", "aperte trigger")

while True:
    # --- IDLE: aguarda trigger ---
    if state == "idle":
        if pressed(btn_trigger):
            state = "processing"
            show("detectando...", "", "", "")
            blink(3, 0.1)

            # simulacao da deteccao
            time.sleep(PROCESSING_DELAY)
            musica = "Tame Impala"

            sel_index = 0
            state = "selecting"
            time.sleep(CANCEL_DELAY)

    # --- SELECTING: navega playlists ---
    elif state == "selecting":
        pl = PLAYLISTS[sel_index]
        show(musica[:16], "", "-> " + pl, "ok=conf  >=trocar")

        if pressed(btn_cycle):
            sel_index = (sel_index + 1) % len(PLAYLISTS)
            time.sleep(NAV_DELAY)

        elif pressed(btn_confirm):
            state = "processing"
            show("salvando...", musica[:16], PLAYLISTS[sel_index], "")
            blink(2, 0.1)

            # simulacao do save na API
            time.sleep(SAVE_DELAY)

            led.on()
            show("salvo!", musica[:16], PLAYLISTS[sel_index], "")
            time.sleep(SUCCESS_HOLD)
            led.off()

            state = "idle"
            show("PULSE", "", "aperte trigger")
            time.sleep(CONFIRM_DELAY)

        elif pressed(btn_trigger):
            # cancela
            state = "idle"
            show("PULSE", "", "aperte trigger")
            time.sleep(CANCEL_DELAY)

    time.sleep(DEBOUNCE_DELAY)