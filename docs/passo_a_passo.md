# Passo a passo — Raspberry Pi Zero 2W

## 1. Instalar o sistema operacional

1. Baixar o **Raspberry Pi Imager**: https://www.raspberrypi.com/software/
2. Gravar **Raspberry Pi OS Lite (64-bit)** no cartão microSD
3. Antes de gravar, clicar em **"Edit Settings"** no Imager e configurar:
   - Hostname: `pulse`
   - Usuário e senha
   - WiFi (SSID + senha)
   - Enable SSH

---

## 2. Primeiro acesso

Conectar o cartão e ligar o Pi Zero. Após ~60s:

```bash
ssh pi@pulse.local
```

---

## 3. Habilitar I2C (para o display OLED)

```bash
sudo raspi-config
# Interface Options > I2C > Enable
sudo reboot
```

Verificar se o display está conectado após reiniciar:

```bash
i2cdetect -y 1
# deve aparecer o endereço 0x3C
```

---

## 4. Transferir o projeto

No seu PC (dentro da pasta `pulse/`):

```bash
rsync -av --exclude=venv --exclude=pulse --exclude=__pycache__ --exclude=.git . pi@pulse.local:~/pulse/
```

---

## 5. Instalar dependências

```bash
cd ~/pulse
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## 6. Copiar autenticação do Spotify

O arquivo `.cache` (gerado quando você fez login no Spotify no seu PC) precisa ir junto, senão o Pi Zero tentará abrir um browser e vai travar.

No seu PC:

```bash
scp .cache pi@pulse.local:~/pulse/.cache
```

---

## 7. Configurar o modo hardware

Em `config/config.json`, trocar:

```json
"mode": "hardware"
```

---

## 8. Testar

```bash
cd ~/pulse
source venv/bin/activate
python main.py
```

O display deve mostrar `PULSE / Pressione...` e o botão deve acionar o pulse.

---

## 9. Rodar automaticamente na inicialização

Criar o serviço systemd:

```bash
sudo nano /etc/systemd/system/pulse.service
```

Conteúdo:

```ini
[Unit]
Description=Pulse
After=network-online.target
Wants=network-online.target

[Service]
User=pi
WorkingDirectory=/home/pi/pulse
ExecStart=/home/pi/pulse/venv/bin/python main.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Ativar:

```bash
sudo systemctl enable pulse
sudo systemctl start pulse
```

Verificar se subiu:

```bash
sudo systemctl status pulse
```

---

## Conexões físicas (pinout BCM)

```
Pi Zero 2W          Componente
──────────────────────────────
GPIO 15  (Pin 22) → Botão → GND
GPIO 14  (Pin 8)  → Resistor 220Ω → LED → GND
GPIO 2   (Pin 3)  → OLED SDA
GPIO 3   (Pin 5)  → OLED SCL
3V3      (Pin 1)  → OLED VCC
GND      (Pin 6)  → OLED GND / Botão / LED
```
