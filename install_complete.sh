#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# openPadel - Complete Installation Script
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ACTUAL_USER="${SUDO_USER:-$USER}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# ==============================================================================
# LANGUAGE DETECTION
# ==============================================================================
LANG_FILE="$SCRIPT_DIR/data/language_settings.json"
if [ -f "$LANG_FILE" ]; then
    LANGUAGE=$(python3 -c "import json; print(json.load(open('$LANG_FILE')).get('language','de'))" 2>/dev/null || echo "de")
else
    LANGUAGE="de"
fi

# ==============================================================================
# TRANSLATIONS
# ==============================================================================
case "$LANGUAGE" in
"en")
    MSG_TITLE="openPadel - Complete Installation"
    MSG_ROOT_ERROR="ERROR: This script must be run as root"
    MSG_ROOT_HINT="Please run with 'sudo ./install_complete.sh'"
    MSG_WORKDIR="Working directory"
    MSG_USER_LABEL="User"
    MSG_BOOT_CFG="Boot config"
    MSG_YESNO_INVALID="Please enter 'yes' or 'no'"
    MSG_PART1="PART 1: E-Paper Display Installation"
    MSG_SPI_ENABLE="Enabling SPI interface..."
    MSG_SPI_DONE="SPI enabled in"
    MSG_SPI_EXISTS="SPI already enabled"
    MSG_CAM_DONE="Camera enabled in"
    MSG_CAM_EXISTS="Camera already enabled"
    MSG_SPI_MODULES="Loading SPI kernel modules..."
    MSG_SPI_REBOOT="SPI modules can only be loaded after reboot"
    MSG_PERMISSIONS="Setting permissions..."
    MSG_PACKAGES="Installing system packages..."
    MSG_LIB="Creating Waveshare EPD library..."
    MSG_TEST_SCRIPT="Creating display test script..."
    MSG_DISPLAY_DONE="Display installation complete!"
    MSG_PIN_HEADER='Waveshare 2.9" E-Paper pin layout:'
    MSG_TEST_START="Starting display test..."
    MSG_TEST_SUCCESS="Display test successful!"
    MSG_TEST_QUESTION="Does the display show 'openPadel'?"
    MSG_TEST_OK="Perfect! Display is working."
    MSG_TEST_WIRING="Display test failed. Please check wiring."
    MSG_TEST_CONTINUE="Installation will continue anyway..."
    MSG_TEST_ERROR="Display test could not be executed."
    MSG_SPI_NOT_ACTIVE="SPI not yet active (/dev/spidev0.0 missing)."
    MSG_SPI_SKIP="Display test skipped – display worker takes over after reboot."
    MSG_PART2="PART 2: openPadel Server Installation"
    MSG_VENV_CREATE="Creating Python virtual environment..."
    MSG_VENV_DONE="Virtual environment created"
    MSG_VENV_EXISTS="Virtual environment already exists"
    MSG_PIP="Installing Python dependencies..."
    MSG_PIP_DONE="Python packages installed"
    MSG_DATA="Creating missing data files..."
    MSG_DATA_DONE="Data files ready"
    MSG_START_SERVER_SH="Creating start_server.sh..."
    MSG_START_DISPLAY_SH="Creating start_display_worker.sh..."
    MSG_SERVICES="Installing systemd services..."
    MSG_SERVICES_DONE="Systemd services installed"
    MSG_SERVER_START="Starting openPadel server..."
    MSG_SERVER_STARTED="Server started successfully!"
    MSG_SERVER_RUNNING="Server running at:"
    MSG_DISPLAY_WORKER="Display worker started!"
    MSG_ACCESS_OK="Perfect! Server is reachable."
    MSG_ACCESS_FAIL="Server not reachable. Please check network/firewall."
    MSG_SERVER_ERROR="Server could not be started!"
    MSG_PART3="PART 3: WiFi Access Point Installation"
    MSG_COUNTRY_PROMPT="Please enter your country code:"
    MSG_COUNTRY_READ="Country code (default: DE): "
    MSG_COUNTRY_SET="Country code:"
    MSG_SUBNET_PROMPT="Please enter subnet (first two octets):"
    MSG_SUBNET_EXAMPLE="Example: 10.20 for 10.20.0.0/24"
    MSG_SUBNET_READ="Subnet (default: 10.20): "
    MSG_SUBNET_SET="Subnet:"
    MSG_WIFI_PKGS="Installing hostapd, dnsmasq, iptables and dhcpcd..."
    MSG_WIFI_NM="Disabling NetworkManager, enabling dhcpcd..."
    MSG_WIFI_COUNTRY="Setting WiFi country code..."
    MSG_WIFI_IFACE="Configuring WiFi interface..."
    MSG_DNSMASQ_CONF="Creating dnsmasq configuration..."
    MSG_DNSMASQ_TEST="Testing dnsmasq configuration..."
    MSG_DNSMASQ_OK="dnsmasq configuration OK"
    MSG_DNSMASQ_ERROR="dnsmasq configuration invalid!"
    MSG_HOSTAPD_CONF="Creating hostapd configuration..."
    MSG_NAT="Configuring routing and NAT..."
    MSG_SUDO_CONF="Configuring sudo permissions for web interface..."
    MSG_SUDO_DONE="sudo permissions configured"
    MSG_WIFI_AP_DISABLE="Disabling wifi-ap.service (replaced by hostapd)..."
    MSG_WIFI_DONE="WiFi access point configured!"
    MSG_AP_READY="Access point services ready!"
    MSG_CONN_INFO="Connection details:"
    MSG_SSID_LABEL="SSID:"
    MSG_PASS_LABEL="Password:"
    MSG_IP_LABEL="IP address:"
    MSG_WEB_LABEL="Web interface:"
    MSG_AP_AFTER_REBOOT="Access point configured (will start after reboot)"
    MSG_LOGS="Logs:"
    MSG_SUMMARY_TITLE="Installation complete!"
    MSG_SUMMARY="Summary:"
    MSG_DISPLAY_CHECK="E-Paper Display (please check)"
    MSG_SERVER_CHECK="openPadel Server (please check)"
    MSG_AP_CHECK="WiFi Access Point (please check)"
    MSG_NEXT_STEPS="Next steps:"
    MSG_REBOOT_REQUIRED="REBOOT REQUIRED (SPI was enabled)"
    MSG_AFTER_REBOOT="After reboot everything starts automatically"
    MSG_NO_REBOOT="No reboot required – all services are already running!"
    MSG_COMMANDS="Useful commands:"
    MSG_CMD_STATUS="Check status:    "
    MSG_CMD_RESTART="Restart server:  "
    MSG_CMD_LOGS="View logs:       "
    MSG_WEB_WLAN="Via WiFi"
    MSG_WEB_ETH="Via Ethernet:    "
    MSG_HINT="Note: SSID and password can be changed via the web interface!"
    MSG_ENJOY="Enjoy openPadel!"
    MSG_REBOOT_QUESTION="Do you want to reboot now?"
    MSG_REBOOTING="System is rebooting..."
    MSG_REBOOT_MANUAL="Please reboot manually: sudo reboot"
    MSG_ACCESS_QUESTION_PREFIX="Can you access http://"
    MSG_ACCESS_QUESTION_SUFFIX=":8080 ?"
    ;;
"es")
    MSG_TITLE="openPadel - Instalación Completa"
    MSG_ROOT_ERROR="ERROR: Este script debe ejecutarse como root"
    MSG_ROOT_HINT="Ejecutar con 'sudo ./install_complete.sh'"
    MSG_WORKDIR="Directorio de trabajo"
    MSG_USER_LABEL="Usuario"
    MSG_BOOT_CFG="Boot config"
    MSG_YESNO_INVALID="Por favor escribe 'yes' o 'no'"
    MSG_PART1="PARTE 1: Instalación del Display E-Paper"
    MSG_SPI_ENABLE="Activando interfaz SPI..."
    MSG_SPI_DONE="SPI activado en"
    MSG_SPI_EXISTS="SPI ya estaba activado"
    MSG_CAM_DONE="Cámara activada en"
    MSG_CAM_EXISTS="Cámara ya estaba activada"
    MSG_SPI_MODULES="Cargando módulos SPI del kernel..."
    MSG_SPI_REBOOT="Los módulos SPI solo se cargan tras el reinicio"
    MSG_PERMISSIONS="Configurando permisos..."
    MSG_PACKAGES="Instalando paquetes del sistema..."
    MSG_LIB="Creando librería Waveshare EPD..."
    MSG_TEST_SCRIPT="Creando script de prueba del display..."
    MSG_DISPLAY_DONE="¡Instalación del display completada!"
    MSG_PIN_HEADER='Conexiones del display Waveshare 2.9" E-Paper:'
    MSG_TEST_START="Iniciando prueba del display..."
    MSG_TEST_SUCCESS="¡Prueba del display exitosa!"
    MSG_TEST_QUESTION="¿Muestra el display 'openPadel'?"
    MSG_TEST_OK="¡Perfecto! El display funciona."
    MSG_TEST_WIRING="Prueba fallida. Por favor verifica el cableado."
    MSG_TEST_CONTINUE="La instalación continuará de todos modos..."
    MSG_TEST_ERROR="No se pudo ejecutar la prueba del display."
    MSG_SPI_NOT_ACTIVE="SPI aún no activo (/dev/spidev0.0 no encontrado)."
    MSG_SPI_SKIP="Prueba del display omitida – el worker tomará el control tras el reinicio."
    MSG_PART2="PARTE 2: Instalación del Servidor openPadel"
    MSG_VENV_CREATE="Creando entorno virtual de Python..."
    MSG_VENV_DONE="Entorno virtual creado"
    MSG_VENV_EXISTS="El entorno virtual ya existe"
    MSG_PIP="Instalando dependencias de Python..."
    MSG_PIP_DONE="Paquetes de Python instalados"
    MSG_DATA="Creando archivos de datos faltantes..."
    MSG_DATA_DONE="Archivos de datos listos"
    MSG_START_SERVER_SH="Creando start_server.sh..."
    MSG_START_DISPLAY_SH="Creando start_display_worker.sh..."
    MSG_SERVICES="Instalando servicios systemd..."
    MSG_SERVICES_DONE="Servicios systemd instalados"
    MSG_SERVER_START="Iniciando servidor openPadel..."
    MSG_SERVER_STARTED="¡Servidor iniciado correctamente!"
    MSG_SERVER_RUNNING="Servidor disponible en:"
    MSG_DISPLAY_WORKER="¡Worker del display iniciado!"
    MSG_ACCESS_OK="¡Perfecto! El servidor es accesible."
    MSG_ACCESS_FAIL="Servidor no accesible. Por favor verifica la red/firewall."
    MSG_SERVER_ERROR="¡No se pudo iniciar el servidor!"
    MSG_PART3="PARTE 3: Instalación del Punto de Acceso WiFi"
    MSG_COUNTRY_PROMPT="Por favor introduce el código de país:"
    MSG_COUNTRY_READ="Código de país (predeterminado: DE): "
    MSG_COUNTRY_SET="Código de país:"
    MSG_SUBNET_PROMPT="Por favor introduce la subred (primeros dos octetos):"
    MSG_SUBNET_EXAMPLE="Ejemplo: 10.20 para 10.20.0.0/24"
    MSG_SUBNET_READ="Subred (predeterminado: 10.20): "
    MSG_SUBNET_SET="Subred:"
    MSG_WIFI_PKGS="Instalando hostapd, dnsmasq, iptables y dhcpcd..."
    MSG_WIFI_NM="Desactivando NetworkManager, activando dhcpcd..."
    MSG_WIFI_COUNTRY="Configurando código de país WiFi..."
    MSG_WIFI_IFACE="Configurando interfaz WiFi..."
    MSG_DNSMASQ_CONF="Creando configuración de dnsmasq..."
    MSG_DNSMASQ_TEST="Probando configuración de dnsmasq..."
    MSG_DNSMASQ_OK="Configuración de dnsmasq OK"
    MSG_DNSMASQ_ERROR="¡Configuración de dnsmasq inválida!"
    MSG_HOSTAPD_CONF="Creando configuración de hostapd..."
    MSG_NAT="Configurando enrutamiento y NAT..."
    MSG_SUDO_CONF="Configurando permisos sudo para la interfaz web..."
    MSG_SUDO_DONE="Permisos sudo configurados"
    MSG_WIFI_AP_DISABLE="Desactivando wifi-ap.service (reemplazado por hostapd)..."
    MSG_WIFI_DONE="¡Punto de acceso WiFi configurado!"
    MSG_AP_READY="¡Servicios del punto de acceso listos!"
    MSG_CONN_INFO="Información de conexión:"
    MSG_SSID_LABEL="SSID:"
    MSG_PASS_LABEL="Contraseña:"
    MSG_IP_LABEL="Dirección IP:"
    MSG_WEB_LABEL="Interfaz web:"
    MSG_AP_AFTER_REBOOT="AP configurado (se iniciará tras el reinicio)"
    MSG_LOGS="Registros:"
    MSG_SUMMARY_TITLE="¡Instalación completada!"
    MSG_SUMMARY="Resumen:"
    MSG_DISPLAY_CHECK="Display E-Paper (por favor verificar)"
    MSG_SERVER_CHECK="Servidor openPadel (por favor verificar)"
    MSG_AP_CHECK="Punto de Acceso WiFi (por favor verificar)"
    MSG_NEXT_STEPS="Próximos pasos:"
    MSG_REBOOT_REQUIRED="REINICIO NECESARIO (SPI fue activado)"
    MSG_AFTER_REBOOT="Tras el reinicio todo se inicia automáticamente"
    MSG_NO_REBOOT="No es necesario reiniciar – ¡todos los servicios ya están funcionando!"
    MSG_COMMANDS="Comandos útiles:"
    MSG_CMD_STATUS="Ver estado:       "
    MSG_CMD_RESTART="Reiniciar servidor:"
    MSG_CMD_LOGS="Ver registros:    "
    MSG_WEB_WLAN="Vía WiFi"
    MSG_WEB_ETH="Vía Ethernet:     "
    MSG_HINT="Nota: ¡El SSID y la contraseña se pueden cambiar desde la interfaz web!"
    MSG_ENJOY="¡Disfruta openPadel!"
    MSG_REBOOT_QUESTION="¿Quieres reiniciar ahora?"
    MSG_REBOOTING="Reiniciando el sistema..."
    MSG_REBOOT_MANUAL="Por favor reinicia manualmente: sudo reboot"
    MSG_ACCESS_QUESTION_PREFIX="¿Puedes acceder a http://"
    MSG_ACCESS_QUESTION_SUFFIX=":8080 ?"
    ;;
*)  # de (default)
    MSG_TITLE="openPadel - Vollständige Installation"
    MSG_ROOT_ERROR="FEHLER: Dieses Skript muss als root ausgeführt werden"
    MSG_ROOT_HINT="Bitte mit 'sudo ./install_complete.sh' ausführen"
    MSG_WORKDIR="Arbeitsverzeichnis"
    MSG_USER_LABEL="Benutzer"
    MSG_BOOT_CFG="Boot-Config"
    MSG_YESNO_INVALID="Bitte 'yes' oder 'no' eingeben"
    MSG_PART1="TEIL 1: E-Paper Display Installation"
    MSG_SPI_ENABLE="Aktiviere SPI Interface..."
    MSG_SPI_DONE="SPI aktiviert in"
    MSG_SPI_EXISTS="SPI bereits aktiviert"
    MSG_CAM_DONE="Kamera aktiviert in"
    MSG_CAM_EXISTS="Kamera bereits aktiviert"
    MSG_SPI_MODULES="Lade SPI-Kernel-Module..."
    MSG_SPI_REBOOT="SPI-Module können erst nach Neustart geladen werden"
    MSG_PERMISSIONS="Setze Berechtigungen..."
    MSG_PACKAGES="Installiere System-Pakete..."
    MSG_LIB="Erstelle Waveshare EPD Library..."
    MSG_TEST_SCRIPT="Erstelle Display-Test-Script..."
    MSG_DISPLAY_DONE="Display-Installation abgeschlossen!"
    MSG_PIN_HEADER='Pinbelegung Waveshare 2.9" E-Paper:'
    MSG_TEST_START="Starte Display-Test..."
    MSG_TEST_SUCCESS="Display-Test erfolgreich durchgeführt!"
    MSG_TEST_QUESTION="Zeigt das Display 'openPadel' an?"
    MSG_TEST_OK="Perfekt! Display funktioniert."
    MSG_TEST_WIRING="Display-Test fehlgeschlagen. Bitte Verkabelung prüfen."
    MSG_TEST_CONTINUE="Installation wird trotzdem fortgesetzt..."
    MSG_TEST_ERROR="Display-Test konnte nicht ausgeführt werden."
    MSG_SPI_NOT_ACTIVE="SPI noch nicht aktiv (/dev/spidev0.0 fehlt)."
    MSG_SPI_SKIP="Display-Test übersprungen – Display Worker übernimmt nach Neustart."
    MSG_PART2="TEIL 2: openPadel Server Installation"
    MSG_VENV_CREATE="Erstelle Python Virtual Environment..."
    MSG_VENV_DONE="Virtual Environment erstellt"
    MSG_VENV_EXISTS="Virtual Environment existiert bereits"
    MSG_PIP="Installiere Python-Abhängigkeiten..."
    MSG_PIP_DONE="Python-Pakete installiert"
    MSG_DATA="Erstelle fehlende Datendateien..."
    MSG_DATA_DONE="Datendateien bereit"
    MSG_START_SERVER_SH="Erstelle start_server.sh..."
    MSG_START_DISPLAY_SH="Erstelle start_display_worker.sh..."
    MSG_SERVICES="Installiere Systemd-Services..."
    MSG_SERVICES_DONE="Systemd-Services installiert"
    MSG_SERVER_START="Starte openPadel Server..."
    MSG_SERVER_STARTED="Server erfolgreich gestartet!"
    MSG_SERVER_RUNNING="Server läuft auf:"
    MSG_DISPLAY_WORKER="Display Worker gestartet!"
    MSG_ACCESS_OK="Perfekt! Server ist erreichbar."
    MSG_ACCESS_FAIL="Server nicht erreichbar. Bitte Netzwerk/Firewall prüfen."
    MSG_SERVER_ERROR="Server konnte nicht gestartet werden!"
    MSG_PART3="TEIL 3: WiFi Access Point Installation"
    MSG_COUNTRY_PROMPT="Bitte Ländercode eingeben:"
    MSG_COUNTRY_READ="Ländercode (Standard: DE): "
    MSG_COUNTRY_SET="Ländercode:"
    MSG_SUBNET_PROMPT="Bitte Subnetz eingeben (erste zwei Oktette):"
    MSG_SUBNET_EXAMPLE="Beispiel: 10.20 für 10.20.0.0/24"
    MSG_SUBNET_READ="Subnetz (Standard: 10.20): "
    MSG_SUBNET_SET="Subnetz:"
    MSG_WIFI_PKGS="Installiere hostapd, dnsmasq, iptables und dhcpcd..."
    MSG_WIFI_NM="Deaktiviere NetworkManager, aktiviere dhcpcd..."
    MSG_WIFI_COUNTRY="Setze WLAN-Ländercode..."
    MSG_WIFI_IFACE="Konfiguriere WLAN-Interface..."
    MSG_DNSMASQ_CONF="Erstelle dnsmasq Konfiguration..."
    MSG_DNSMASQ_TEST="Teste dnsmasq Konfiguration..."
    MSG_DNSMASQ_OK="dnsmasq Konfiguration OK"
    MSG_DNSMASQ_ERROR="dnsmasq Konfiguration fehlerhaft!"
    MSG_HOSTAPD_CONF="Erstelle hostapd Konfiguration..."
    MSG_NAT="Konfiguriere Routing und NAT..."
    MSG_SUDO_CONF="Konfiguriere sudo-Rechte für Web-Interface..."
    MSG_SUDO_DONE="sudo-Rechte konfiguriert"
    MSG_WIFI_AP_DISABLE="Deaktiviere wifi-ap.service (wird durch hostapd ersetzt)..."
    MSG_WIFI_DONE="WiFi Access Point konfiguriert!"
    MSG_AP_READY="Access Point Services bereit!"
    MSG_CONN_INFO="Verbindungsinformationen:"
    MSG_SSID_LABEL="SSID:"
    MSG_PASS_LABEL="Passwort:"
    MSG_IP_LABEL="IP-Adresse:"
    MSG_WEB_LABEL="Web-Interface:"
    MSG_AP_AFTER_REBOOT="Access Point konfiguriert (startet nach Neustart)"
    MSG_LOGS="Logs:"
    MSG_SUMMARY_TITLE="Installation abgeschlossen!"
    MSG_SUMMARY="Zusammenfassung:"
    MSG_DISPLAY_CHECK="E-Paper Display (bitte prüfen)"
    MSG_SERVER_CHECK="openPadel Server (bitte prüfen)"
    MSG_AP_CHECK="WiFi Access Point (bitte prüfen)"
    MSG_NEXT_STEPS="Nächste Schritte:"
    MSG_REBOOT_REQUIRED="NEUSTART ERFORDERLICH (SPI wurde aktiviert)"
    MSG_AFTER_REBOOT="Nach dem Neustart startet alles automatisch"
    MSG_NO_REBOOT="Kein Neustart erforderlich – alle Services laufen bereits!"
    MSG_COMMANDS="Wichtige Befehle:"
    MSG_CMD_STATUS="Status prüfen:      "
    MSG_CMD_RESTART="Server neu starten: "
    MSG_CMD_LOGS="Logs anzeigen:      "
    MSG_WEB_WLAN="Über WLAN"
    MSG_WEB_ETH="Über Ethernet:       "
    MSG_HINT="Hinweis: SSID und Passwort können über das Web-Interface geändert werden!"
    MSG_ENJOY="Viel Spaß mit openPadel!"
    MSG_REBOOT_QUESTION="Möchtest du jetzt neu starten?"
    MSG_REBOOTING="System wird neu gestartet..."
    MSG_REBOOT_MANUAL="Bitte manuell neu starten mit: sudo reboot"
    MSG_ACCESS_QUESTION_PREFIX="Kannst du auf http://"
    MSG_ACCESS_QUESTION_SUFFIX=":8080 zugreifen?"
    ;;
esac

# ==============================================================================
# START
# ==============================================================================
clear
echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║         ${MSG_TITLE}${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}${MSG_ROOT_ERROR}${NC}"
    echo -e "  ${YELLOW}${MSG_ROOT_HINT}${NC}"
    exit 1
fi

# Raspberry Pi 5 (Bookworm) nutzt /boot/firmware/config.txt
if [ -f /boot/firmware/config.txt ]; then
    BOOT_CONFIG="/boot/firmware/config.txt"
else
    BOOT_CONFIG="/boot/config.txt"
fi

echo -e "${BLUE}${MSG_WORKDIR}:${NC} $SCRIPT_DIR"
echo -e "${BLUE}${MSG_USER_LABEL}:${NC} $ACTUAL_USER"
echo -e "${BLUE}${MSG_BOOT_CFG}:${NC} $BOOT_CONFIG"
echo ""

# ==============================================================================
# YES/NO HELPER
# ==============================================================================
ask_yes_no() {
    local prompt="$1"
    local response
    while true; do
        read -p "$prompt (yes/no): " response
        case "$response" in
            [yY][eE][sS]|[yY]) return 0 ;;
            [nN][oO]|[nN])     return 1 ;;
            *) echo -e "${YELLOW}${MSG_YESNO_INVALID}${NC}" ;;
        esac
    done
}

# ==============================================================================
# PART 1: DISPLAY
# ==============================================================================
echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  ${MSG_PART1}${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

SPI_CHANGED=0

echo -e "${YELLOW}[1/6]${NC} ${MSG_SPI_ENABLE}"
if ! grep -q "^dtparam=spi=on" "$BOOT_CONFIG"; then
    echo "dtparam=spi=on" >> "$BOOT_CONFIG"
    echo -e "${GREEN}${MSG_SPI_DONE} $BOOT_CONFIG${NC}"
    SPI_CHANGED=1
else
    echo -e "${GREEN}${MSG_SPI_EXISTS}${NC}"
fi

if ! grep -q "^camera_auto_detect" "$BOOT_CONFIG"; then
    echo "camera_auto_detect=1" >> "$BOOT_CONFIG"
    echo -e "${GREEN}${MSG_CAM_DONE} $BOOT_CONFIG${NC}"
    SPI_CHANGED=1
else
    echo -e "${GREEN}${MSG_CAM_EXISTS}${NC}"
fi

echo -e "${YELLOW}[2/6]${NC} ${MSG_SPI_MODULES}"
if ! lsmod | grep -q spi_bcm2835; then
    modprobe spi_bcm2835 2>/dev/null || echo -e "${YELLOW}${MSG_SPI_REBOOT}${NC}"
fi

echo -e "${YELLOW}[3/6]${NC} ${MSG_PERMISSIONS}"
usermod -a -G spi,gpio $ACTUAL_USER 2>/dev/null || true

echo -e "${YELLOW}[4/6]${NC} ${MSG_PACKAGES}"
apt-get update -qq
apt-get install -y \
    python3-pip python3-venv python3-spidev python3-lgpio python3-pil git \
    rpicam-apps \
    qrencode \
    iw \
    fonts-dejavu-core \
    -qq 2>/dev/null || true

echo -e "${YELLOW}[5/6]${NC} ${MSG_LIB}"
LIB_DIR="$SCRIPT_DIR/lib/waveshare_epd"
mkdir -p "$LIB_DIR"

cat > "$LIB_DIR/epdconfig.py" << 'EOFCONFIG'
import os
import sys
import time
import logging

try:
    import spidev
    import lgpio
except ImportError:
    sys.exit("This library requires spidev and lgpio\nInstall with: sudo apt install python3-spidev python3-lgpio")

RST_PIN  = 17
DC_PIN   = 25
CS_PIN   = 8   # controlled by spidev – do NOT claim via lgpio
BUSY_PIN = 24

# Pi 5 uses gpiochip4 (RP1), older Pi use gpiochip0
GPIO_CHIP = 4 if os.path.exists('/dev/gpiochip4') else 0

SPI = spidev.SpiDev(0, 0)
_h  = None  # lgpio chip handle

def _claim_out(h, pin):
    try:
        lgpio.gpio_claim_output(h, pin)
    except lgpio.error:
        lgpio.gpio_free(h, pin)
        lgpio.gpio_claim_output(h, pin)

def _claim_in(h, pin):
    try:
        lgpio.gpio_claim_input(h, pin)
    except lgpio.error:
        lgpio.gpio_free(h, pin)
        lgpio.gpio_claim_input(h, pin)

def digital_write(pin, value):
    if pin == CS_PIN:
        return  # spidev handles CS automatically
    lgpio.gpio_write(_h, pin, value)

def digital_read(pin):
    return lgpio.gpio_read(_h, pin)

def delay_ms(delaytime):
    time.sleep(delaytime / 1000.0)

def spi_writebyte(data):
    SPI.writebytes(data)

def module_init():
    global _h
    _h = lgpio.gpiochip_open(GPIO_CHIP)
    _claim_out(_h, RST_PIN)
    _claim_out(_h, DC_PIN)
    # CS_PIN is owned by the SPI kernel driver – skip
    _claim_in(_h, BUSY_PIN)
    SPI.open(0, 0)
    SPI.max_speed_hz = 4000000
    SPI.mode = 0b00
    return 0

def module_exit():
    SPI.close()
    lgpio.gpio_write(_h, RST_PIN, 0)
    lgpio.gpio_write(_h, DC_PIN, 0)
    lgpio.gpiochip_close(_h)
EOFCONFIG

cat > "$LIB_DIR/epd2in9_V2.py" << 'EOFEPD'
import logging
from . import epdconfig

EPD_WIDTH  = 128
EPD_HEIGHT = 296

logger = logging.getLogger(__name__)

class EPD:
    def __init__(self):
        self.reset_pin = epdconfig.RST_PIN
        self.dc_pin    = epdconfig.DC_PIN
        self.busy_pin  = epdconfig.BUSY_PIN
        self.cs_pin    = epdconfig.CS_PIN
        self.width     = EPD_WIDTH
        self.height    = EPD_HEIGHT

    def reset(self):
        epdconfig.digital_write(self.reset_pin, 1)
        epdconfig.delay_ms(100)
        epdconfig.digital_write(self.reset_pin, 0)
        epdconfig.delay_ms(2)
        epdconfig.digital_write(self.reset_pin, 1)
        epdconfig.delay_ms(100)

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

    def ReadBusy(self, timeout_ms=30000):
        logger.debug("e-Paper busy")
        elapsed = 0
        while epdconfig.digital_read(self.busy_pin) == 1:
            epdconfig.delay_ms(10)
            elapsed += 10
            if elapsed >= timeout_ms:
                logger.warning("ReadBusy timeout after %dms", elapsed)
                break
        logger.debug("e-Paper busy release")

    def TurnOnDisplay(self):
        self.send_command(0x22)
        self.send_data(0xF7)
        self.send_command(0x20)
        self.ReadBusy()

    def init(self):
        if epdconfig.module_init() != 0:
            return -1
        self.reset()
        self.ReadBusy()

        self.send_command(0x12)  # Software reset (SSD1680)
        self.ReadBusy()

        self.send_command(0x01)  # Driver output control: 296 lines
        self.send_data(0x27)     # (296-1) = 0x127 → low byte
        self.send_data(0x01)     # high byte
        self.send_data(0x00)

        self.send_command(0x11)  # Data entry mode: X+, Y+
        self.send_data(0x03)

        self.send_command(0x44)  # RAM X start/end: bytes 0–15 → 128 pixels
        self.send_data(0x00)
        self.send_data(0x0F)

        self.send_command(0x45)  # RAM Y start/end: 0x127 → 0x000
        self.send_data(0x27)
        self.send_data(0x01)
        self.send_data(0x00)
        self.send_data(0x00)

        self.send_command(0x3C)  # Border waveform
        self.send_data(0x05)

        self.send_command(0x18)  # Use built-in temperature sensor
        self.send_data(0x80)

        self.send_command(0x4E)  # RAM X address counter = 0
        self.send_data(0x00)

        self.send_command(0x4F)  # RAM Y address counter = 0x127
        self.send_data(0x27)
        self.send_data(0x01)

        self.ReadBusy()
        return 0

    def getbuffer(self, image):
        buf = [0xFF] * (int(self.width / 8) * self.height)
        image_mono = image.convert('1')
        imwidth, imheight = image_mono.size
        pixels = image_mono.load()
        if imwidth == self.width and imheight == self.height:
            for y in range(imheight):
                for x in range(imwidth):
                    if pixels[x, y] == 0:
                        buf[int((x + y * self.width) / 8)] &= ~(0x80 >> (x % 8))
        elif imwidth == self.height and imheight == self.width:
            for y in range(imheight):
                for x in range(imwidth):
                    newx = y
                    newy = self.height - x - 1
                    if pixels[x, y] == 0:
                        buf[int((newx + newy * self.width) / 8)] &= ~(0x80 >> (y % 8))
        return buf

    def display(self, image):
        self.send_command(0x24)
        for b in image:
            self.send_data(b)
        self.TurnOnDisplay()

    def Clear(self, color=0xFF):
        self.send_command(0x24)
        for _ in range(int(self.width * self.height / 8)):
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

echo -e "${YELLOW}[6/6]${NC} ${MSG_TEST_SCRIPT}"
cat > "$SCRIPT_DIR/test_display.py" << EOFTEST
#!/usr/bin/env python3
import sys
sys.path.insert(0, '$SCRIPT_DIR/lib')

from waveshare_epd import epd2in9_V2
from PIL import Image

print("Initializing display...")
epd = epd2in9_V2.EPD()
epd.init()
print("Display ready!")

image = Image.open('$SCRIPT_DIR/poweroff.jpg')
display_width = epd.height   # 296
display_height = epd.width   # 128

img_ratio = image.width / image.height
display_ratio = display_width / display_height
if img_ratio > display_ratio:
    new_width = display_width
    new_height = int(display_width / img_ratio)
else:
    new_height = display_height
    new_width = int(display_height * img_ratio)

image = image.resize((new_width, new_height), Image.LANCZOS)
final_image = Image.new('RGB', (display_width, display_height), 'white')
offset_x = (display_width - new_width) // 2
offset_y = (display_height - new_height) // 2
final_image.paste(image, (offset_x, offset_y))
final_image = final_image.convert('1', dither=Image.FLOYDSTEINBERG)

print("Sending image to display...")
epd.display(epd.getbuffer(final_image))
print("Done!")
epd.sleep()
EOFTEST

chmod +x "$SCRIPT_DIR/test_display.py"

echo ""
echo -e "${GREEN}${MSG_DISPLAY_DONE}${NC}"
echo ""
echo -e "${BLUE}${MSG_PIN_HEADER}${NC}"
echo "  VCC  -> 3.3V"
echo "  GND  -> GND"
echo "  DIN  -> GPIO 10 (SPI0_MOSI)"
echo "  CLK  -> GPIO 11 (SPI0_SCLK)"
echo "  CS   -> GPIO 8  (SPI0_CS0)"
echo "  DC   -> GPIO 25"
echo "  RST  -> GPIO 17"
echo "  BUSY -> GPIO 24"
echo ""

DISPLAY_OK=0
if [ -e /dev/spidev0.0 ]; then
    echo -e "${YELLOW}${MSG_TEST_START}${NC}"
    if python3 "$SCRIPT_DIR/test_display.py" 2>&1; then
        echo ""
        echo -e "${GREEN}${MSG_TEST_SUCCESS}${NC}"
        echo ""
        if ask_yes_no "$MSG_TEST_QUESTION"; then
            echo -e "${GREEN}${MSG_TEST_OK}${NC}"
            DISPLAY_OK=1
        else
            echo -e "${YELLOW}${MSG_TEST_WIRING}${NC}"
            echo -e "${YELLOW}${MSG_TEST_CONTINUE}${NC}"
        fi
    else
        echo -e "${RED}${MSG_TEST_ERROR}${NC}"
    fi
else
    echo -e "${YELLOW}${MSG_SPI_NOT_ACTIVE}${NC}"
    echo -e "${YELLOW}${MSG_SPI_SKIP}${NC}"
fi

# ==============================================================================
# PART 2: SERVER
# ==============================================================================
echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  ${MSG_PART2}${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

echo -e "${YELLOW}[1/6]${NC} ${MSG_VENV_CREATE}"
if [ ! -d "$SCRIPT_DIR/.venv" ]; then
    su - $ACTUAL_USER -c "cd $SCRIPT_DIR && python3 -m venv .venv"
    echo -e "${GREEN}${MSG_VENV_DONE}${NC}"
else
    echo -e "${GREEN}${MSG_VENV_EXISTS}${NC}"
fi

echo -e "${YELLOW}[2/6]${NC} ${MSG_PIP}"
su - $ACTUAL_USER -c "cd $SCRIPT_DIR && source .venv/bin/activate && pip install --quiet --upgrade pip && pip install --quiet -r requirements.txt"
echo -e "${GREEN}${MSG_PIP_DONE}${NC}"

echo -e "${YELLOW}[3/6]${NC} ${MSG_DATA}"
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
echo -e "${GREEN}${MSG_DATA_DONE}${NC}"

if [ ! -f "$SCRIPT_DIR/start_server.sh" ]; then
    echo -e "${YELLOW}[4/6]${NC} ${MSG_START_SERVER_SH}"
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

if [ ! -f "$SCRIPT_DIR/start_display_worker.sh" ]; then
    echo -e "${YELLOW}[5/6]${NC} ${MSG_START_DISPLAY_SH}"
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

echo -e "${YELLOW}[6/6]${NC} ${MSG_SERVICES}"

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
echo -e "${GREEN}${MSG_SERVICES_DONE}${NC}"

echo ""
echo -e "${YELLOW}${MSG_SERVER_START}${NC}"
systemctl start padel-server.service
sleep 3

SERVER_OK=0
IP_ADDRESS=""
if systemctl is-active --quiet padel-server.service; then
    echo -e "${GREEN}${MSG_SERVER_STARTED}${NC}"
    IP_ADDRESS=$(hostname -I | awk '{print $1}')
    echo ""
    echo -e "${BLUE}${MSG_SERVER_RUNNING}${NC}"
    echo -e "  ${GREEN}http://$IP_ADDRESS:8080${NC}"
    echo -e "  ${GREEN}http://localhost:8080${NC}"
    echo ""

    systemctl start padel-display.service
    sleep 2
    if systemctl is-active --quiet padel-display.service; then
        echo -e "${GREEN}${MSG_DISPLAY_WORKER}${NC}"
    fi

    echo ""
    if ask_yes_no "${MSG_ACCESS_QUESTION_PREFIX}${IP_ADDRESS}${MSG_ACCESS_QUESTION_SUFFIX}"; then
        echo -e "${GREEN}${MSG_ACCESS_OK}${NC}"
        SERVER_OK=1
    else
        echo -e "${YELLOW}${MSG_ACCESS_FAIL}${NC}"
    fi
else
    echo -e "${RED}${MSG_SERVER_ERROR}${NC}"
    echo -e "  journalctl -u padel-server.service -n 50"
fi

# ==============================================================================
# PART 3: WIFI AP
# ==============================================================================
echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  ${MSG_PART3}${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

echo -e "${YELLOW}${MSG_COUNTRY_PROMPT}${NC}"
echo "  AT = Österreich / Austria / Austria"
echo "  DE = Deutschland / Germany / Alemania"
echo "  US = United States"
echo "  GB = United Kingdom"
echo "  CH = Schweiz / Switzerland / Suiza"
echo ""
read -p "$MSG_COUNTRY_READ" COUNTRY_CODE
COUNTRY_CODE=${COUNTRY_CODE:-DE}
echo -e "${GREEN}${MSG_COUNTRY_SET} $COUNTRY_CODE${NC}"

echo ""
echo -e "${YELLOW}${MSG_SUBNET_PROMPT}${NC}"
echo "  ${MSG_SUBNET_EXAMPLE}"
echo ""
read -p "$MSG_SUBNET_READ" SUBNET
SUBNET=${SUBNET:-10.20}
echo -e "${GREEN}${MSG_SUBNET_SET} ${SUBNET}.0.0/24${NC}"

echo -e "${YELLOW}[1/8]${NC} ${MSG_WIFI_PKGS}"
apt-get install -y dnsmasq hostapd iptables dhcpcd5 -qq 2>/dev/null

echo -e "${YELLOW}[2/8]${NC} ${MSG_WIFI_NM}"
systemctl stop NetworkManager 2>/dev/null || true
systemctl disable NetworkManager 2>/dev/null || true
systemctl enable dhcpcd
systemctl start dhcpcd

systemctl stop hostapd 2>/dev/null || true
systemctl stop dnsmasq 2>/dev/null || true
systemctl unmask hostapd 2>/dev/null || true

echo -e "${YELLOW}[3/8]${NC} ${MSG_WIFI_COUNTRY}"
raspi-config nonint do_wifi_country $COUNTRY_CODE

SERIAL=$(cat /proc/cpuinfo | grep Serial | awk '{print $3}' | tail -c 9)
if [ -z "$SERIAL" ]; then
    SERIAL="00000000"
fi
SSID="openPadel_${SERIAL}"
PASSWORD="openPadel"

echo -e "${BLUE}${MSG_SSID_LABEL}${NC} $SSID"
echo -e "${BLUE}${MSG_PASS_LABEL}${NC} $PASSWORD"

echo -e "${YELLOW}[4/8]${NC} ${MSG_WIFI_IFACE}"
if [ -f /etc/dhcpcd.conf ]; then
    mv /etc/dhcpcd.conf /etc/dhcpcd.conf.old
fi

cat > /etc/dhcpcd.conf << EOFDHCP
interface wlan0
    static ip_address=${SUBNET}.1.1/24
    nohook wpa_supplicant
EOFDHCP

systemctl restart dhcpcd

echo -e "${YELLOW}[5/8]${NC} ${MSG_DNSMASQ_CONF}"
if [ -f /etc/dnsmasq.conf ]; then
    mv /etc/dnsmasq.conf /etc/dnsmasq.conf_alt
fi

cat > /etc/dnsmasq.conf << EOFDNSMASQ
interface=wlan0
no-dhcp-interface=eth0
dhcp-range=${SUBNET}.1.100,${SUBNET}.1.200,255.255.255.0,24h
dhcp-option=option:dns-server,${SUBNET}.1.1
EOFDNSMASQ

echo -e "${YELLOW}[6/8]${NC} ${MSG_DNSMASQ_TEST}"
if dnsmasq --test -C /etc/dnsmasq.conf; then
    echo -e "${GREEN}${MSG_DNSMASQ_OK}${NC}"
else
    echo -e "${RED}${MSG_DNSMASQ_ERROR}${NC}"
fi

systemctl restart dnsmasq
systemctl enable dnsmasq

echo -e "${YELLOW}[7/8]${NC} ${MSG_HOSTAPD_CONF}"
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

if ! grep -q "DAEMON_CONF" /etc/default/hostapd 2>/dev/null; then
    cat >> /etc/default/hostapd << EOFDEFAULT
RUN_DAEMON=yes
DAEMON_CONF="/etc/hostapd/hostapd.conf"
EOFDEFAULT
fi

echo -e "${YELLOW}[8/8]${NC} ${MSG_NAT}"
if ! grep -q "net.ipv4.ip_forward=1" /etc/sysctl.conf; then
    echo "net.ipv4.ip_forward=1" >> /etc/sysctl.conf
fi

iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
sh -c "iptables-save > /etc/iptables.ipv4.nat"

if ! grep -q "iptables-restore" /etc/rc.local; then
    sed -i '/^exit 0/i iptables-restore < /etc/iptables.ipv4.nat' /etc/rc.local
fi

systemctl unmask hostapd
systemctl enable hostapd
systemctl enable dnsmasq

echo ""
echo -e "${YELLOW}${MSG_SUDO_CONF}${NC}"
cat > /etc/sudoers.d/padel-wifi << EOFSUDO
# openPadel wifi management
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
echo -e "${GREEN}${MSG_SUDO_DONE}${NC}"

if systemctl is-enabled wifi-ap.service >/dev/null 2>&1; then
    echo -e "${YELLOW}${MSG_WIFI_AP_DISABLE}${NC}"
    systemctl stop wifi-ap.service 2>/dev/null || true
    systemctl disable wifi-ap.service 2>/dev/null || true
fi

echo ""
echo -e "${GREEN}${MSG_WIFI_DONE}${NC}"
echo ""

AP_OK=0
if systemctl status hostapd >/dev/null 2>&1 && systemctl status dnsmasq >/dev/null 2>&1; then
    echo -e "${GREEN}${MSG_AP_READY}${NC}"
    echo ""
    echo -e "${BLUE}${MSG_CONN_INFO}${NC}"
    echo -e "  ${MSG_SSID_LABEL} ${GREEN}${SSID}${NC}"
    echo -e "  ${MSG_PASS_LABEL} ${GREEN}${PASSWORD}${NC}"
    echo -e "  ${MSG_IP_LABEL}  ${GREEN}${SUBNET}.1.1${NC}"
    echo -e "  ${MSG_WEB_LABEL} ${GREEN}http://${SUBNET}.1.1:8080${NC}"
    AP_OK=1
else
    echo -e "${YELLOW}${MSG_AP_AFTER_REBOOT}${NC}"
    echo -e "${BLUE}${MSG_LOGS}${NC}"
    echo -e "  hostapd: journalctl -u hostapd -n 20"
    echo -e "  dnsmasq: journalctl -u dnsmasq -n 20"
    AP_OK=1
fi

# ==============================================================================
# SUMMARY
# ==============================================================================
echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║              ${MSG_SUMMARY_TITLE}${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

echo -e "${BLUE}${MSG_SUMMARY}${NC}"
echo ""
if [ $DISPLAY_OK -eq 1 ]; then
    echo -e "  ${GREEN}✓${NC} E-Paper Display"
else
    echo -e "  ${YELLOW}⚠${NC}  ${MSG_DISPLAY_CHECK}"
fi

if [ $SERVER_OK -eq 1 ]; then
    echo -e "  ${GREEN}✓${NC} openPadel Server"
else
    echo -e "  ${YELLOW}⚠${NC}  ${MSG_SERVER_CHECK}"
fi

if [ $AP_OK -eq 1 ]; then
    echo -e "  ${GREEN}✓${NC} WiFi Access Point"
else
    echo -e "  ${YELLOW}⚠${NC}  ${MSG_AP_CHECK}"
fi

echo ""
echo -e "${BLUE}${MSG_NEXT_STEPS}${NC}"
echo ""

if [ $SPI_CHANGED -eq 1 ]; then
    echo -e "  ${YELLOW}1. ${MSG_REBOOT_REQUIRED}${NC}"
    echo -e "     ${GREEN}sudo reboot${NC}"
    echo ""
    echo -e "  ${YELLOW}2. ${MSG_AFTER_REBOOT}${NC}"
else
    echo -e "  ${GREEN}${MSG_NO_REBOOT}${NC}"
fi

echo ""
echo -e "${BLUE}${MSG_COMMANDS}${NC}"
echo -e "  ${MSG_CMD_STATUS}${GREEN}sudo systemctl status padel-server padel-display hostapd dnsmasq${NC}"
echo -e "  ${MSG_CMD_RESTART}${GREEN}sudo systemctl restart padel-server${NC}"
echo -e "  ${MSG_CMD_LOGS}${GREEN}journalctl -u padel-server -f${NC}"
echo ""
echo -e "${BLUE}${MSG_WEB_LABEL}${NC}"
echo -e "  ${MSG_WEB_WLAN} (${SSID}): ${GREEN}http://${SUBNET}.1.1:8080${NC}"
if [ -n "$IP_ADDRESS" ]; then
    echo -e "  ${MSG_WEB_ETH}${GREEN}http://${IP_ADDRESS}:8080${NC}"
fi
echo ""
echo -e "${YELLOW}${MSG_HINT}${NC}"
echo ""

if [ $SPI_CHANGED -eq 1 ]; then
    echo ""
    if ask_yes_no "$MSG_REBOOT_QUESTION"; then
        echo -e "${GREEN}${MSG_REBOOTING}${NC}"
        sleep 2
        reboot
    else
        echo -e "${YELLOW}${MSG_REBOOT_MANUAL}${NC}"
    fi
fi

echo ""
echo -e "${GREEN}${MSG_ENJOY}${NC}"
echo ""
