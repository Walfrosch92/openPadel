#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# openPadel - Vollständiges Installationsskript
# ==============================================================================
# Installiert:
# 1. E-Paper Display (Waveshare 2.9")
# 2. openPadel Server und Dependencies
# 3. WiFi Access Point
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ACTUAL_USER="${SUDO_USER:-$USER}"

# Farben
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

clear
echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║         openPadel - Vollständige Installation              ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}FEHLER: Dieses Skript muss als root ausgeführt werden${NC}"
    echo -e "Bitte mit ${YELLOW}'sudo ./install_complete.sh'${NC} ausführen"
    exit 1
fi

# Raspberry Pi 5 (Bookworm) nutzt /boot/firmware/config.txt
if [ -f /boot/firmware/config.txt ]; then
    BOOT_CONFIG="/boot/firmware/config.txt"
else
    BOOT_CONFIG="/boot/config.txt"
fi

echo -e "${BLUE}Arbeitsverzeichnis:${NC} $SCRIPT_DIR"
echo -e "${BLUE}Benutzer:${NC} $ACTUAL_USER"
echo -e "${BLUE}Boot-Config:${NC} $BOOT_CONFIG"
echo ""

# ==============================================================================
# Funktion: Ja/Nein Abfrage
# ==============================================================================
ask_yes_no() {
    local prompt="$1"
    local response
    
    while true; do
        read -p "$prompt (yes/no): " response
        case "$response" in
            [yY][eE][sS]|[yY])
                return 0
                ;;
            [nN][oO]|[nN])
                return 1
                ;;
            *)
                echo -e "${YELLOW}Bitte 'yes' oder 'no' eingeben${NC}"
                ;;
        esac
    done
}

# ==============================================================================
# TEIL 1: DISPLAY INSTALLATION
# ==============================================================================
echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  TEIL 1: E-Paper Display Installation                     ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# SPI aktivieren
echo -e "${YELLOW}[1/6]${NC} Aktiviere SPI Interface..."
if ! grep -q "^dtparam=spi=on" "$BOOT_CONFIG"; then
    echo "dtparam=spi=on" >> "$BOOT_CONFIG"
    echo -e "${GREEN}SPI in $BOOT_CONFIG aktiviert${NC}"
    SPI_CHANGED=1
else
    echo -e "${GREEN}SPI bereits aktiviert${NC}"
    SPI_CHANGED=0
fi

# Kamera aktivieren
if ! grep -q "^camera_auto_detect" "$BOOT_CONFIG"; then
    echo "camera_auto_detect=1" >> "$BOOT_CONFIG"
    echo -e "${GREEN}Kamera in $BOOT_CONFIG aktiviert${NC}"
    SPI_CHANGED=1
fi

# SPI-Modul laden
echo -e "${YELLOW}[2/6]${NC} Lade SPI-Kernel-Module..."
if ! lsmod | grep -q spi_bcm2835; then
    modprobe spi_bcm2835 2>/dev/null || echo -e "${YELLOW}SPI-Module können erst nach Neustart geladen werden${NC}"
fi

# Berechtigungen
echo -e "${YELLOW}[3/6]${NC} Setze Berechtigungen..."
usermod -a -G spi,gpio $ACTUAL_USER 2>/dev/null || true

# System-Pakete
echo -e "${YELLOW}[4/6]${NC} Installiere System-Pakete..."
apt-get update -qq
apt-get install -y \
    python3-pip python3-venv python3-spidev python3-rpi.gpio python3-pil git \
    rpicam-apps \
    qrencode \
    iw \
    fonts-dejavu-core \
    -qq 2>/dev/null || true

# Waveshare Library
echo -e "${YELLOW}[5/6]${NC} Erstelle Waveshare EPD Library..."
LIB_DIR="$SCRIPT_DIR/lib/waveshare_epd"
mkdir -p "$LIB_DIR"

cat > "$LIB_DIR/epdconfig.py" << 'EOFCONFIG'
import os
import sys
import time
import logging

try:
    import spidev
    import RPi.GPIO as GPIO
except ImportError:
    sys.exit("This library requires the spidev & RPi.GPIO libraries\nInstall with: sudo apt install python3-spidev python3-rpi.gpio")

RST_PIN = 17
DC_PIN = 25
CS_PIN = 8
BUSY_PIN = 24

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
EOFCONFIG

cat > "$LIB_DIR/epd2in9_V2.py" << 'EOFEPD'
import logging
from . import epdconfig

EPD_WIDTH = 128
EPD_HEIGHT = 296

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
EOFEPD

cat > "$LIB_DIR/__init__.py" << 'EOFINIT'
from . import epdconfig
from . import epd2in9_V2

__all__ = ['epdconfig', 'epd2in9_V2']
EOFINIT

chown -R $ACTUAL_USER:$ACTUAL_USER "$SCRIPT_DIR/lib"

# Display Test Script
echo -e "${YELLOW}[6/6]${NC} Erstelle Display-Test-Script..."
cat > "$SCRIPT_DIR/test_display.py" << EOFTEST
#!/usr/bin/env python3
import sys
sys.path.insert(0, '$SCRIPT_DIR/lib')

from waveshare_epd import epd2in9_V2
from PIL import Image, ImageDraw, ImageFont

print("Initialisiere Display...")
epd = epd2in9_V2.EPD()
epd.init()
print("Display bereit!")

print("Erstelle Test-Bild...")
image = Image.new('1', (epd.height, epd.width), 255)
draw = ImageDraw.Draw(image)

try:
    font_large = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 40)
    font_small = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 20)
except:
    font_large = ImageFont.load_default()
    font_small = ImageFont.load_default()

draw.text((50, 50), "openPadel", font=font_large, fill=0)
draw.text((70, 110), "Display Test", font=font_small, fill=0)
draw.text((90, 140), "erfolgreich!", font=font_small, fill=0)

print("Zeige auf Display...")
epd.display(epd.getbuffer(image))
print("Fertig! Display sollte jetzt 'openPadel' anzeigen")

epd.sleep()
EOFTEST

chmod +x "$SCRIPT_DIR/test_display.py"

echo ""
echo -e "${GREEN}Display-Installation abgeschlossen!${NC}"
echo ""
echo -e "${BLUE}Pinbelegung Waveshare 2.9\" E-Paper:${NC}"
echo "  VCC  -> 3.3V"
echo "  GND  -> GND"
echo "  DIN  -> GPIO 10 (SPI0_MOSI)"
echo "  CLK  -> GPIO 11 (SPI0_SCLK)"
echo "  CS   -> GPIO 8  (SPI0_CS0)"
echo "  DC   -> GPIO 25"
echo "  RST  -> GPIO 17"
echo "  BUSY -> GPIO 24"
echo ""

# Display-Test – nur wenn SPI bereits im Kernel aktiv ist
if [ -e /dev/spidev0.0 ]; then
    echo -e "${YELLOW}Starte Display-Test...${NC}"
    if python3 "$SCRIPT_DIR/test_display.py" 2>&1; then
        echo ""
        echo -e "${GREEN}Display-Test erfolgreich durchgeführt!${NC}"
        echo ""
        if ask_yes_no "Zeigt das Display 'openPadel' an?"; then
            echo -e "${GREEN}Perfekt! Display funktioniert.${NC}"
            DISPLAY_OK=1
        else
            echo -e "${YELLOW}Display-Test fehlgeschlagen. Bitte Verkabelung prüfen.${NC}"
            echo -e "${YELLOW}Installation wird trotzdem fortgesetzt...${NC}"
            DISPLAY_OK=0
        fi
    else
        echo -e "${RED}Display-Test konnte nicht ausgeführt werden.${NC}"
        DISPLAY_OK=0
    fi
else
    echo -e "${YELLOW}SPI noch nicht aktiv (/dev/spidev0.0 fehlt).${NC}"
    echo -e "${YELLOW}Display-Test wird nach dem Neustart am Ende automatisch übersprungen –${NC}"
    echo -e "${YELLOW}der Display Worker übernimmt dann die Kontrolle.${NC}"
    DISPLAY_OK=0
fi

# ==============================================================================
# TEIL 2: openPadel SERVER INSTALLATION
# ==============================================================================
echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  TEIL 2: openPadel Server Installation                    ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Virtual Environment
echo -e "${YELLOW}[1/6]${NC} Erstelle Python Virtual Environment..."
if [ ! -d "$SCRIPT_DIR/.venv" ]; then
    su - $ACTUAL_USER -c "cd $SCRIPT_DIR && python3 -m venv .venv"
    echo -e "${GREEN}Virtual Environment erstellt${NC}"
else
    echo -e "${GREEN}Virtual Environment existiert bereits${NC}"
fi

# Python Dependencies
echo -e "${YELLOW}[2/6]${NC} Installiere Python-Abhängigkeiten..."
su - $ACTUAL_USER -c "cd $SCRIPT_DIR && source .venv/bin/activate && pip install --quiet --upgrade pip && pip install --quiet -r requirements.txt"
echo -e "${GREEN}Python-Pakete installiert${NC}"

# Erstelle fehlende Datendateien mit sicheren Defaults
echo -e "${YELLOW}[3/6]${NC} Erstelle fehlende Datendateien..."
mkdir -p "$SCRIPT_DIR/data"
if [ ! -f "$SCRIPT_DIR/data/match_history.json" ]; then
    echo "[]" > "$SCRIPT_DIR/data/match_history.json"
fi
if [ ! -f "$SCRIPT_DIR/data/stats.json" ]; then
    echo '{"history":[]}' > "$SCRIPT_DIR/data/stats.json"
fi
if [ ! -f "$SCRIPT_DIR/data/state_backup.json" ]; then
    cp "$SCRIPT_DIR/data/state.json" "$SCRIPT_DIR/data/state_backup.json"
fi
if [ ! -f "$SCRIPT_DIR/data/wifi_config.json" ]; then
    echo '{"ssid_suffix":"","created":""}' > "$SCRIPT_DIR/data/wifi_config.json"
fi
chown -R $ACTUAL_USER:$ACTUAL_USER "$SCRIPT_DIR/data"
echo -e "${GREEN}Datendateien bereit${NC}"

# Erstelle start_server.sh falls nicht vorhanden
if [ ! -f "$SCRIPT_DIR/start_server.sh" ]; then
    echo -e "${YELLOW}[4/6]${NC} Erstelle start_server.sh..."
    cat > "$SCRIPT_DIR/start_server.sh" << 'EOFSERVER'
#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
source .venv/bin/activate
exec python3 main.py
EOFSERVER
    chmod +x "$SCRIPT_DIR/start_server.sh"
    chown $ACTUAL_USER:$ACTUAL_USER "$SCRIPT_DIR/start_server.sh"
fi

# Erstelle start_display_worker.sh falls nicht vorhanden
if [ ! -f "$SCRIPT_DIR/start_display_worker.sh" ]; then
    echo -e "${YELLOW}[5/6]${NC} Erstelle start_display_worker.sh..."
    cat > "$SCRIPT_DIR/start_display_worker.sh" << 'EOFWORKER'
#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
source .venv/bin/activate
exec python3 display_worker.py
EOFWORKER
    chmod +x "$SCRIPT_DIR/start_display_worker.sh"
    chown $ACTUAL_USER:$ACTUAL_USER "$SCRIPT_DIR/start_display_worker.sh"
fi

# Systemd Services
echo -e "${YELLOW}[6/6]${NC} Installiere Systemd-Services..."

# Server Service
cat > /etc/systemd/system/padel-server.service << EOFSERVICE
[Unit]
Description=openPadel Server
After=network.target

[Service]
Type=simple
User=$ACTUAL_USER
WorkingDirectory=$SCRIPT_DIR
ExecStart=$SCRIPT_DIR/start_server.sh
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOFSERVICE

# Display Service
cat > /etc/systemd/system/padel-display.service << EOFDISPLAY
[Unit]
Description=openPadel Display Worker
After=padel-server.service
Requires=padel-server.service

[Service]
Type=simple
User=$ACTUAL_USER
WorkingDirectory=$SCRIPT_DIR
ExecStart=$SCRIPT_DIR/start_display_worker.sh
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOFDISPLAY

systemctl daemon-reload
systemctl enable padel-server.service
systemctl enable padel-display.service

echo -e "${GREEN}Systemd-Services installiert${NC}"

# Starte Server
echo ""
echo -e "${YELLOW}Starte openPadel Server...${NC}"
systemctl start padel-server.service
sleep 3

if systemctl is-active --quiet padel-server.service; then
    echo -e "${GREEN}Server erfolgreich gestartet!${NC}"
    
    # Hole IP-Adresse
    IP_ADDRESS=$(hostname -I | awk '{print $1}')
    
    echo ""
    echo -e "${BLUE}Server läuft auf:${NC}"
    echo -e "  ${GREEN}http://$IP_ADDRESS:8080${NC}"
    echo -e "  ${GREEN}http://localhost:8080${NC}"
    echo ""
    
    # Starte Display Worker
    systemctl start padel-display.service
    sleep 2
    
    if systemctl is-active --quiet padel-display.service; then
        echo -e "${GREEN}Display Worker gestartet!${NC}"
    fi
    
    echo ""
    if ask_yes_no "Kannst du auf http://$IP_ADDRESS:8080 zugreifen?"; then
        echo -e "${GREEN}Perfekt! Server ist erreichbar.${NC}"
        SERVER_OK=1
    else
        echo -e "${YELLOW}Server nicht erreichbar. Bitte Netzwerk/Firewall prüfen.${NC}"
        SERVER_OK=0
    fi
else
    echo -e "${RED}Server konnte nicht gestartet werden!${NC}"
    echo -e "Logs: ${YELLOW}journalctl -u padel-server.service -n 50${NC}"
    SERVER_OK=0
fi

# ==============================================================================
# TEIL 3: WIFI ACCESS POINT INSTALLATION
# ==============================================================================
echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  TEIL 3: WiFi Access Point Installation                   ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Frage nach Ländercode
echo -e "${YELLOW}Bitte Ländercode eingeben:${NC}"
echo "  AT = Österreich"
echo "  DE = Deutschland"
echo "  US = United States"
echo "  GB = Großbritannien"
echo "  CH = Schweiz"
echo ""
read -p "Ländercode (Standard: DE): " COUNTRY_CODE
COUNTRY_CODE=${COUNTRY_CODE:-DE}
echo -e "${GREEN}Ländercode: $COUNTRY_CODE${NC}"

# Frage nach Subnetz
echo ""
echo -e "${YELLOW}Bitte Subnetz eingeben (erste zwei Oktette):${NC}"
echo "  Beispiel: 10.20 für 10.20.0.0/24"
echo ""
read -p "Subnetz (Standard: 10.20): " SUBNET
SUBNET=${SUBNET:-10.20}
echo -e "${GREEN}Subnetz: ${SUBNET}.0.0/24${NC}"

# Installiere hostapd, dnsmasq und iptables
echo -e "${YELLOW}[1/8]${NC} Installiere hostapd, dnsmasq, iptables und dhcpcd..."
apt-get install -y dnsmasq hostapd iptables dhcpcd5 -qq 2>/dev/null

# NetworkManager deaktivieren und dhcpcd aktivieren
echo -e "${YELLOW}[2/8]${NC} Deaktiviere NetworkManager, aktiviere dhcpcd..."
systemctl stop NetworkManager 2>/dev/null || true
systemctl disable NetworkManager 2>/dev/null || true
systemctl enable dhcpcd
systemctl start dhcpcd

# Stoppe Services
systemctl stop hostapd 2>/dev/null || true
systemctl stop dnsmasq 2>/dev/null || true
systemctl unmask hostapd 2>/dev/null || true

# Setze Ländercode mit raspi-config
echo -e "${YELLOW}[3/8]${NC} Setze WLAN-Ländercode..."
raspi-config nonint do_wifi_country $COUNTRY_CODE

# Hole Serial für eindeutigen SSID
SERIAL=$(cat /proc/cpuinfo | grep Serial | awk '{print $3}' | tail -c 9)
if [ -z "$SERIAL" ]; then
    SERIAL="00000000"
fi

SSID="openPadel_${SERIAL}"
PASSWORD="openPadel"

echo -e "${BLUE}SSID:${NC} $SSID"
echo -e "${BLUE}Passwort:${NC} $PASSWORD"

# WLAN-Interface konfigurieren (dhcpcd)
echo -e "${YELLOW}[4/8]${NC} Konfiguriere WLAN-Interface..."
if [ -f /etc/dhcpcd.conf ]; then
    mv /etc/dhcpcd.conf /etc/dhcpcd.conf.old
fi

cat > /etc/dhcpcd.conf << EOFDHCP
interface wlan0
    static ip_address=${SUBNET}.1.1/24
    nohook wpa_supplicant
EOFDHCP

systemctl restart dhcpcd

# dnsmasq Konfiguration
echo -e "${YELLOW}[5/8]${NC} Erstelle dnsmasq Konfiguration..."
if [ -f /etc/dnsmasq.conf ]; then
    mv /etc/dnsmasq.conf /etc/dnsmasq.conf_alt
fi

cat > /etc/dnsmasq.conf << EOFDNSMASQ
interface=wlan0
no-dhcp-interface=eth0
dhcp-range=${SUBNET}.1.100,${SUBNET}.1.200,255.255.255.0,24h
dhcp-option=option:dns-server,${SUBNET}.1.1
EOFDNSMASQ

# dnsmasq testen und starten
echo -e "${YELLOW}[6/8]${NC} Teste dnsmasq Konfiguration..."
if dnsmasq --test -C /etc/dnsmasq.conf; then
    echo -e "${GREEN}dnsmasq Konfiguration OK${NC}"
else
    echo -e "${RED}dnsmasq Konfiguration fehlerhaft!${NC}"
fi

systemctl restart dnsmasq
systemctl enable dnsmasq

# hostapd Konfiguration
echo -e "${YELLOW}[7/8]${NC} Erstelle hostapd Konfiguration..."
cat > /etc/hostapd/hostapd.conf << EOFHOSTAPD
interface=wlan0
#driver=nl80211
ssid=${SSID}
channel=1
hw_mode=g
ieee80211n=1
ieee80211d=1
country_code=${COUNTRY_CODE}
wmm_enabled=1
auth_algs=1
wpa=2
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
wpa_passphrase=${PASSWORD}
EOFHOSTAPD

chmod 600 /etc/hostapd/hostapd.conf

# hostapd Daemon-Konfiguration
if ! grep -q "DAEMON_CONF" /etc/default/hostapd 2>/dev/null; then
    cat >> /etc/default/hostapd << EOFDEFAULT
RUN_DAEMON=yes
DAEMON_CONF="/etc/hostapd/hostapd.conf"
EOFDEFAULT
fi

# Routing und NAT konfigurieren
echo -e "${YELLOW}[8/8]${NC} Konfiguriere Routing und NAT..."
if ! grep -q "net.ipv4.ip_forward=1" /etc/sysctl.conf; then
    echo "net.ipv4.ip_forward=1" >> /etc/sysctl.conf
fi

iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
sh -c "iptables-save > /etc/iptables.ipv4.nat"

if ! grep -q "iptables-restore" /etc/rc.local; then
    sed -i '/^exit 0/i iptables-restore < /etc/iptables.ipv4.nat' /etc/rc.local
fi

# Services aktivieren und starten
systemctl unmask hostapd
systemctl enable hostapd
systemctl enable dnsmasq

# Konfiguriere sudo-Rechte für WiFi-Verwaltung über Web-Interface
echo ""
echo -e "${YELLOW}Konfiguriere sudo-Rechte für Web-Interface...${NC}"
cat > /etc/sudoers.d/padel-wifi << EOFSUDO
# Erlaube $ACTUAL_USER WiFi AP Verwaltung ohne Passwort
$ACTUAL_USER ALL=(ALL) NOPASSWD: /bin/systemctl restart hostapd
$ACTUAL_USER ALL=(ALL) NOPASSWD: /bin/systemctl restart dnsmasq
$ACTUAL_USER ALL=(ALL) NOPASSWD: /bin/systemctl stop hostapd
$ACTUAL_USER ALL=(ALL) NOPASSWD: /bin/systemctl stop dnsmasq
$ACTUAL_USER ALL=(ALL) NOPASSWD: /bin/systemctl start hostapd
$ACTUAL_USER ALL=(ALL) NOPASSWD: /bin/systemctl start dnsmasq
$ACTUAL_USER ALL=(ALL) NOPASSWD: /bin/systemctl status hostapd
$ACTUAL_USER ALL=(ALL) NOPASSWD: /bin/systemctl status dnsmasq
$ACTUAL_USER ALL=(ALL) NOPASSWD: /bin/cp /etc/hostapd/hostapd.conf /etc/hostapd/hostapd.conf.backup
$ACTUAL_USER ALL=(ALL) NOPASSWD: /bin/mv /tmp/hostapd.conf.new /etc/hostapd/hostapd.conf
$ACTUAL_USER ALL=(ALL) NOPASSWD: /bin/chmod 600 /etc/hostapd/hostapd.conf
$ACTUAL_USER ALL=(ALL) NOPASSWD: /usr/sbin/iw dev wlan0 station dump
EOFSUDO

chmod 0440 /etc/sudoers.d/padel-wifi
echo -e "${GREEN}sudo-Rechte konfiguriert${NC}"

# Deaktiviere wifi-ap.service falls vorhanden (Konflikt vermeiden)
if systemctl is-enabled wifi-ap.service >/dev/null 2>&1; then
    echo -e "${YELLOW}Deaktiviere wifi-ap.service (wird durch hostapd ersetzt)...${NC}"
    systemctl stop wifi-ap.service 2>/dev/null || true
    systemctl disable wifi-ap.service 2>/dev/null || true
fi

echo ""
echo -e "${GREEN}WiFi Access Point konfiguriert!${NC}"
echo ""

# Status prüfen
AP_OK=0
if systemctl status hostapd >/dev/null 2>&1 && systemctl status dnsmasq >/dev/null 2>&1; then
    echo -e "${GREEN}Access Point Services bereit!${NC}"
    echo ""
    echo -e "${BLUE}Verbindungsinformationen:${NC}"
    echo -e "  SSID: ${GREEN}${SSID}${NC}"
    echo -e "  Passwort: ${GREEN}${PASSWORD}${NC}"
    echo -e "  IP-Adresse: ${GREEN}${SUBNET}.1.1${NC}"
    echo -e "  Web-Interface: ${GREEN}http://${SUBNET}.1.1:8080${NC}"
    AP_OK=1
else
    echo -e "${YELLOW}Access Point Services konfiguriert (starten nach Neustart)${NC}"
    echo -e "${YELLOW}Logs:${NC}"
    echo -e "  hostapd: ${YELLOW}journalctl -u hostapd -n 20${NC}"
    echo -e "  dnsmasq: ${YELLOW}journalctl -u dnsmasq -n 20${NC}"
    AP_OK=1
fi

# ==============================================================================
# ABSCHLUSS
# ==============================================================================
echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║              Installation abgeschlossen!                   ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

echo -e "${BLUE}Zusammenfassung:${NC}"
echo ""
if [ $DISPLAY_OK -eq 1 ]; then
    echo -e "  ${GREEN}✓${NC} E-Paper Display"
else
    echo -e "  ${YELLOW}⚠${NC} E-Paper Display (bitte prüfen)"
fi

if [ $SERVER_OK -eq 1 ]; then
    echo -e "  ${GREEN}✓${NC} openPadel Server"
else
    echo -e "  ${YELLOW}⚠${NC} openPadel Server (bitte prüfen)"
fi

if [ $AP_OK -eq 1 ]; then
    echo -e "  ${GREEN}✓${NC} WiFi Access Point"
else
    echo -e "  ${YELLOW}⚠${NC} WiFi Access Point (bitte prüfen)"
fi

echo ""
echo -e "${BLUE}Nächste Schritte:${NC}"
echo ""

if [ $SPI_CHANGED -eq 1 ]; then
    echo -e "  ${YELLOW}1. NEUSTART ERFORDERLICH (SPI wurde aktiviert)${NC}"
    echo -e "     ${GREEN}sudo reboot${NC}"
    echo ""
    echo -e "  ${YELLOW}2. Nach dem Neustart startet alles automatisch${NC}"
else
    echo -e "  ${GREEN}Kein Neustart erforderlich - alle Services laufen bereits!${NC}"
fi

echo ""
echo -e "${BLUE}Wichtige Befehle:${NC}"
echo -e "  Status prüfen:      ${GREEN}sudo systemctl status padel-server padel-display hostapd dnsmasq${NC}"
echo -e "  Server neu starten: ${GREEN}sudo systemctl restart padel-server${NC}"
echo -e "  Logs anzeigen:      ${GREEN}journalctl -u padel-server -f${NC}"
echo ""
echo -e "${BLUE}Web-Interface:${NC}"
echo -e "  Über WLAN (${SSID}): ${GREEN}http://${SUBNET}.1.1:8080${NC}"
if [ -n "$IP_ADDRESS" ]; then
    echo -e "  Über Ethernet:       ${GREEN}http://${IP_ADDRESS}:8080${NC}"
fi
echo ""
echo -e "${YELLOW}Hinweis: SSID und Passwort können über das Web-Interface geändert werden!${NC}"
echo ""

# Abschlussfrage für Reboot
if [ $SPI_CHANGED -eq 1 ]; then
    echo ""
    if ask_yes_no "Möchtest du jetzt neu starten?"; then
        echo -e "${GREEN}System wird neu gestartet...${NC}"
        sleep 2
        reboot
    else
        echo -e "${YELLOW}Bitte manuell neu starten mit: ${GREEN}sudo reboot${NC}"
    fi
fi

echo ""
echo -e "${GREEN}Viel Spaß mit openPadel!${NC}"
echo ""
