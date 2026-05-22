"""
Handler de hardware para Raspberry Pi Zero 2W.

Conexoes:
  Botao : GPIO 15 (BCM) ──── GND  (pull-up interno)
  LED   : GPIO 14 (BCM) ──── resistor 220Ω ──── GND
  OLED  : SDA → GPIO 2 (BCM)
          SCL → GPIO 3 (BCM)
          VCC → 3V3(Pin 1)
          GND → GND

Setup no Pi Zero (uma vez):
  sudo raspi-config  # Interface Options > I2C > Enable
  pip install -r requirements.txt

Dependencias: gpiozero luma.oled Pillow
"""

import time
import threading
from gpiozero import Button, LED
from luma.core.interface.serial import i2c
from luma.oled.device import ssd1306
from luma.core.render import canvas

BTN_PIN = 15
LED_PIN = 14

button  = Button(BTN_PIN, pull_up=True, bounce_time=0.3)
led     = LED(LED_PIN)
_serial = i2c(port=1, address=0x3C)
display = ssd1306(_serial, width=128, height=64)

_lock = threading.Lock()  # impede chamadas simultâneas se botão for pressionado 2x


def _oled(lines: list):
    with canvas(display) as draw:
        for i, line in enumerate(lines):
            draw.text((0, i * 12), str(line)[:16], fill="white")


def _set_idle():
    led.off()
    _oled(["", "   PULSE", "", " Pressione..."])


def _set_processing():
    led.blink(on_time=0.15, off_time=0.15)
    _oled(["", " Buscando..."])


def _set_success(song: str, playlist: str):
    led.on()
    _oled(["OK!", song[:16], "->", playlist[:16]])
    time.sleep(4)
    _set_idle()


def _set_error(msg: str = "Tente novamente"):
    led.blink(on_time=0.1, off_time=0.1, n=3)
    led.off()
    _oled(["  ERRO", msg[:16]])
    time.sleep(3)
    _set_idle()


def run_hardware_loop(pulse_fn):
    """
    Loop principal do modo hardware.

    pulse_fn: callable que executa o pulse e retorna
              {'success': bool, 'track': str, 'playlist': str, 'error': str}
    """
    _set_idle()
    print("Hardware pronto. Aguardando botao (GPIO {})...".format(BTN_PIN))

    def on_press():
        if not _lock.acquire(blocking=False):
            return  # já processando, ignora press duplo
        try:
            _set_processing()
            result = pulse_fn()
            if result['success']:
                _set_success(result['track'], result['playlist'])
            else:
                _set_error(result.get('error', 'Erro'))
        finally:
            _lock.release()

    button.when_pressed = on_press

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        led.off()
        display.cleanup()
        print("\nEncerrado.")
