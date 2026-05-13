#!/usr/bin/env bash
set -euo pipefail

echo "📦 Waveshare 2.9inch E-Paper Display Installation (Offline)"
echo "============================================================"
echo ""

# Prüfe ob als Root ausgeführt
if [ "$EUID" -ne 0 ]; then 
    echo "⚠️  Dieses Skript muss als root ausgeführt werden"
    echo "Bitte mit 'sudo ./install_epaper.sh' ausführen"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ACTUAL_USER="${SUDO_USER:-$USER}"

echo "📁 Arbeitsverzeichnis: $SCRIPT_DIR"
echo "👤 Benutzer: $ACTUAL_USER"
echo ""

# 1. SPI aktivieren
echo "🔧 Aktiviere SPI Interface..."
if ! grep -q "^dtparam=spi=on" /boot/config.txt; then
    echo "dtparam=spi=on" >> /boot/config.txt
    echo "✅ SPI in /boot/config.txt aktiviert"
    SPI_CHANGED=1
else
    echo "✅ SPI bereits aktiviert"
    SPI_CHANGED=0
fi

# 2. SPI-Modul aktivieren (sofort, ohne Neustart)
echo "🔧 Lade SPI-Kernel-Module..."
if ! lsmod | grep -q spi_bcm2835; then
    modprobe spi_bcm2835 || echo "⚠️  Konnte SPI-Module nicht laden (Neustart erforderlich)"
fi

# 3. Berechtigungen setzen
echo "🔐 Setze Berechtigungen..."
usermod -a -G spi,gpio $ACTUAL_USER || true

# 4. Erstelle lib-Verzeichnis
echo "📁 Erstelle Library-Verzeichnis..."
LIB_DIR="$SCRIPT_DIR/lib/waveshare_epd"
mkdir -p "$LIB_DIR"

# 5. Erstelle minimale waveshare_epd Library (nur 2.9inch V2)
echo "📝 Erstelle Waveshare EPD Library..."

# epdconfig.py
cat > "$LIB_DIR/epdconfig.py" << 'EOF'
import os
import sys
import time
import logging

try:
    import spidev
    import RPi.GPIO as GPIO
except ImportError:
    sys.exit("This library requires the spidev & RPi.GPIO libraries\nInstall with: sudo apt install python3-spidev python3-rpi.gpio")

# Pin definition
RST_PIN         = 17
DC_PIN          = 25
CS_PIN          = 8
BUSY_PIN        = 24

# SPI device, bus = 0, device = 0
SPI = spidev.SpiDev(0, 0)

def digital_write(pin, value):
    GPIO.output(pin, value)

def digital_read(pin):
    return GPIO.input(pin)

def delay_ms(delaytime):
    time.sleep(delaytime / 1000.0)

def spi_writebyte(data):
    SPI.writebytes(data)

def module_init():
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    GPIO.setup(RST_PIN, GPIO.OUT)
    GPIO.setup(DC_PIN, GPIO.OUT)
    GPIO.setup(CS_PIN, GPIO.OUT)
    GPIO.setup(BUSY_PIN, GPIO.IN)
    SPI.max_speed_hz = 4000000
    SPI.mode = 0b00
    return 0

def module_exit():
    logging.debug("spi end")
    SPI.close()
    logging.debug("close 5V, Module enters 0 power consumption ...")
    GPIO.output(RST_PIN, 0)
    GPIO.output(DC_PIN, 0)
    GPIO.cleanup()
EOF

# epd2in9_V2.py - Vereinfachte Version
cat > "$LIB_DIR/epd2in9_V2.py" << 'EOF'
import logging
from . import epdconfig

# Display resolution
EPD_WIDTH       = 128
EPD_HEIGHT      = 296

FULL_UPDATE = 0
PART_UPDATE = 1

logger = logging.getLogger(__name__)

class EPD:
    def __init__(self):
        self.reset_pin = epdconfig.RST_PIN
        self.dc_pin = epdconfig.DC_PIN
        self.busy_pin = epdconfig.BUSY_PIN
        self.cs_pin = epdconfig.CS_PIN
        self.width = EPD_WIDTH
        self.height = EPD_HEIGHT
        
    lut_full_update = [
        0x50, 0xAA, 0x55, 0xAA, 0x11, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0xFF, 0xFF, 0x1F, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
    ]
    
    lut_partial_update = [
        0x10, 0x18, 0x18, 0x08, 0x18, 0x18, 0x08, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x13, 0x14, 0x44, 0x12, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
    ]
    
    def reset(self):
        epdconfig.digital_write(self.reset_pin, 1)
        epdconfig.delay_ms(50)
        epdconfig.digital_write(self.reset_pin, 0)
        epdconfig.delay_ms(2)
        epdconfig.digital_write(self.reset_pin, 1)
        epdconfig.delay_ms(50)
    
    def send_command(self, command):
        epdconfig.digital_write(self.dc_pin, 0)
        epdconfig.digital_write(self.cs_pin, 0)
        epdconfig.spi_writebyte([command])
        epdconfig.digital_write(self.cs_pin, 1)

    def send_data(self, data):
        epdconfig.digital_write(self.dc_pin, 1)
        epdconfig.digital_write(self.cs_pin, 0)
        epdconfig.spi_writebyte([data])
        epdconfig.digital_write(self.cs_pin, 1)
        
    def ReadBusy(self):
        logger.debug("e-Paper busy")
        while(epdconfig.digital_read(self.busy_pin) == 1):
            epdconfig.delay_ms(10)
        logger.debug("e-Paper busy release")
        
    def TurnOnDisplay(self):
        self.send_command(0x22)
        self.send_data(0xC7)
        self.send_command(0x20)
        self.ReadBusy()
        
    def init(self):
        if (epdconfig.module_init() != 0):
            return -1
        self.reset()
        
        self.send_command(0x04)
        self.ReadBusy()
        
        self.send_command(0x00)
        self.send_data(0x1f)
        
        self.send_command(0x61)
        self.send_data(0x80)
        self.send_data(0x01)
        self.send_data(0x28)
        
        self.send_command(0X50)
        self.send_data(0x97)
        
        return 0
    
    def getbuffer(self, image):
        buf = [0xFF] * (int(self.width/8) * self.height)
        image_monocolor = image.convert('1')
        imwidth, imheight = image_monocolor.size
        pixels = image_monocolor.load()
        if(imwidth == self.width and imheight == self.height):
            logger.debug("Vertical")
            for y in range(imheight):
                for x in range(imwidth):
                    if pixels[x, y] == 0:
                        buf[int((x + y * self.width) / 8)] &= ~(0x80 >> (x % 8))
        elif(imwidth == self.height and imheight == self.width):
            logger.debug("Horizontal")
            for y in range(imheight):
                for x in range(imwidth):
                    newx = y
                    newy = self.height - x - 1
                    if pixels[x, y] == 0:
                        buf[int((newx + newy*self.width) / 8)] &= ~(0x80 >> (y % 8))
        return buf

    def display(self, image):
        self.send_command(0x24)
        for i in range(0, int(self.width * self.height / 8)):
            self.send_data(image[i])
        self.TurnOnDisplay()
    
    def Clear(self, color):
        self.send_command(0x24)
        for i in range(0, int(self.width * self.height / 8)):
            self.send_data(color)
        self.TurnOnDisplay()

    def sleep(self):
        self.send_command(0x10)
        self.send_data(0x01)
        
        epdconfig.delay_ms(100)
        epdconfig.module_exit()
EOF

# __init__.py
cat > "$LIB_DIR/__init__.py" << 'EOF'
from . import epdconfig
from . import epd2in9_V2

__all__ = ['epdconfig', 'epd2in9_V2']
EOF

chown -R $ACTUAL_USER:$ACTUAL_USER "$SCRIPT_DIR/lib"
echo "✅ Waveshare EPD Library erstellt"

# 6. Installiere Python-Pakete im venv
echo "📦 Installiere Python-Pakete im venv..."
if [ -d "$SCRIPT_DIR/.venv" ]; then
    source "$SCRIPT_DIR/.venv/bin/activate"
    pip install --quiet spidev RPi.GPIO 2>/dev/null || echo "⚠️  Konnte Pakete nicht im venv installieren"
    deactivate
else
    echo "⚠️  Kein venv gefunden, überspringe pip install"
fi

# 7. Installiere System-Pakete
echo "📦 Installiere System-Pakete..."
apt-get install -y python3-spidev python3-rpi.gpio 2>/dev/null || echo "✅ Pakete bereits installiert"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Installation abgeschlossen!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if [ $SPI_CHANGED -eq 1 ]; then
    echo "⚠️  SPI wurde aktiviert - NEUSTART ERFORDERLICH!"
    echo ""
    echo "Bitte System neu starten:"
    echo "   sudo reboot"
    echo ""
else
    echo "✅ SPI bereits aktiviert, kein Neustart nötig"
    echo ""
fi

echo "📌 Nächste Schritte:"
echo ""
echo "1. Display anschließen gemäß Waveshare Wiki:"
echo "   VCC  -> 3.3V"
echo "   GND  -> GND"
echo "   DIN  -> GPIO 10 (SPI0_MOSI)"
echo "   CLK  -> GPIO 11 (SPI0_SCLK)"
echo "   CS   -> GPIO 8  (SPI0_CS0)"
echo "   DC   -> GPIO 25"
echo "   RST  -> GPIO 17"
echo "   BUSY -> GPIO 24"
echo ""
echo "2. Display Worker starten:"
echo "   ./start_display_worker.sh"
echo ""
echo "3. Display Worker Auto-Start installieren:"
echo "   sudo ./install_display_worker.sh"
echo ""
