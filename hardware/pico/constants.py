# Constantes do hardware MicroPython (Raspberry Pi Pico / Zero).
# Altere aqui; main.py importa deste arquivo.

# Pinos GPIO
PIN_TRIGGER = 15  # dispara análise
PIN_CYCLE   = 16  # alterna entre candidatas
PIN_CONFIRM = 18  # confirma seleção
PIN_LED     = 14
PIN_SDA     = 2
PIN_SCL     = 3

# Display OLED
OLED_WIDTH  = 128
OLED_HEIGHT = 64
I2C_FREQ    = 400_000
I2C_ID      = 1

# Timings (segundos)
DEBOUNCE_DELAY   = 0.05
NAV_DELAY        = 0.25
BLINK_DELAY      = 0.15
SUCCESS_HOLD     = 2.5
PROCESSING_DELAY = 1.2
SAVE_DELAY       = 1.0
CANCEL_DELAY     = 0.3
CONFIRM_DELAY    = 0.4
