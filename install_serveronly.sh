#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# openPadel - Server-Only Installation
# (no Waveshare display, no IMX219 camera config – bring your own hardware)
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ACTUAL_USER="${SUDO_USER:-$USER}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# ==============================================================================
# LANGUAGE
# ==============================================================================
LANG_FILE="$SCRIPT_DIR/data/language_settings.json"
if [ -f "$LANG_FILE" ]; then
    LANGUAGE=$(python3 -c "import json; print(json.load(open('$LANG_FILE')).get('language','de'))" 2>/dev/null || echo "de")
else
    echo -e "${YELLOW}Sprache / Language / Idioma:${NC}"
    echo "  1) Deutsch"
    echo "  2) English"
    echo "  3) Español"
    echo ""
    read -p "Auswahl / Choice / Selección (1-3, default: 1): " LANG_CHOICE
    case "$LANG_CHOICE" in
        2) LANGUAGE="en" ;;
        3) LANGUAGE="es" ;;
        *) LANGUAGE="de" ;;
    esac
    mkdir -p "$SCRIPT_DIR/data"
    echo "{\"language\": \"$LANGUAGE\"}" > "$SCRIPT_DIR/data/language_settings.json"
    chown "$ACTUAL_USER:$ACTUAL_USER" "$SCRIPT_DIR/data/language_settings.json"
fi

# ==============================================================================
# TRANSLATIONS
# ==============================================================================
case "$LANGUAGE" in
"en")
    MSG_TITLE="openPadel - Server-Only Installation"
    MSG_SUBTITLE="(custom camera / custom display)"
    MSG_ROOT_ERROR="ERROR: Run as root: sudo ./install_serveronly.sh"
    MSG_WORKDIR="Working directory"
    MSG_USER_LABEL="User"
    MSG_PART1="PART 1: openPadel Server"
    MSG_PACKAGES="Installing system packages..."
    MSG_VENV_CREATE="Creating Python virtual environment..."
    MSG_VENV_DONE="Virtual environment created"
    MSG_VENV_EXISTS="Virtual environment already exists"
    MSG_PIP="Installing Python dependencies..."
    MSG_PIP_DONE="Python packages installed"
    MSG_DATA="Creating missing data files..."
    MSG_DATA_DONE="Data files ready"
    MSG_SERVICES="Installing systemd service..."
    MSG_SERVICES_DONE="Service installed"
    MSG_SERVER_START="Starting openPadel server..."
    MSG_SERVER_STARTED="Server started successfully!"
    MSG_SERVER_RUNNING="Server running at:"
    MSG_ACCESS_QUESTION_PREFIX="Can you access http://"
    MSG_ACCESS_QUESTION_SUFFIX=":8080 ?"
    MSG_ACCESS_OK="Perfect! Server is reachable."
    MSG_ACCESS_FAIL="Server not reachable. Check: journalctl -u padel-server -n 50"
    MSG_SERVER_ERROR="Server could not be started!"
    MSG_PART2="PART 2: WiFi Access Point"
    MSG_COUNTRY_PROMPT="Please enter your country code:"
    MSG_COUNTRY_READ="Country code (default: DE): "
    MSG_COUNTRY_SET="Country code:"
    MSG_SUBNET_PROMPT="Please enter subnet (first two octets):"
    MSG_SUBNET_EXAMPLE="Example: 10.20 for 10.20.0.0/24"
    MSG_SUBNET_READ="Subnet (default: 10.20): "
    MSG_SUBNET_SET="Subnet:"
    MSG_WIFI_PKGS="Installing hostapd, dnsmasq, iptables, dhcpcd..."
    MSG_WIFI_NM="Disabling NetworkManager, enabling dhcpcd..."
    MSG_WIFI_COUNTRY="Setting WiFi country code..."
    MSG_WIFI_IFACE="Configuring WiFi interface..."
    MSG_DNSMASQ_CONF="Creating dnsmasq configuration..."
    MSG_DNSMASQ_TEST="Testing dnsmasq configuration..."
    MSG_DNSMASQ_OK="dnsmasq configuration OK"
    MSG_DNSMASQ_ERROR="dnsmasq configuration invalid!"
    MSG_HOSTAPD_CONF="Creating hostapd configuration..."
    MSG_NAT="Configuring routing and NAT..."
    MSG_SUDO_CONF="Configuring sudo permissions..."
    MSG_SUDO_DONE="sudo permissions configured"
    MSG_SSID_LABEL="SSID:"
    MSG_PASS_LABEL="Password:"
    MSG_IP_LABEL="IP address:"
    MSG_WEB_LABEL="Web interface:"
    MSG_WEB_WLAN="Via WiFi"
    MSG_WEB_ETH="Via Ethernet:    "
    MSG_WIFI_DONE="WiFi access point configured!"
    MSG_SUMMARY_TITLE="Installation complete!"
    MSG_SUMMARY="Summary:"
    MSG_SERVER_CHECK="openPadel Server"
    MSG_AP_CHECK="WiFi Access Point"
    MSG_HINT="Note: SSID and password can be changed via the web interface!"
    MSG_COMMANDS="Useful commands:"
    MSG_CMD_STATUS="Check status:    "
    MSG_CMD_RESTART="Restart server:  "
    MSG_CMD_LOGS="View logs:       "
    MSG_REBOOT_QUESTION="Reboot Raspberry Pi now?"
    MSG_REBOOT_OPT1="1) Reboot now (recommended)"
    MSG_REBOOT_OPT2="2) Later – reboot manually with: sudo reboot"
    MSG_REBOOT_CHOICE="Your choice (1/2): "
    MSG_REBOOTING="System is rebooting..."
    MSG_ENJOY="Enjoy openPadel!"
    ;;
"es")
    MSG_TITLE="openPadel - Instalación Solo Servidor"
    MSG_SUBTITLE="(cámara personalizada / pantalla personalizada)"
    MSG_ROOT_ERROR="ERROR: Ejecutar como root: sudo ./install_serveronly.sh"
    MSG_WORKDIR="Directorio de trabajo"
    MSG_USER_LABEL="Usuario"
    MSG_PART1="PARTE 1: Servidor openPadel"
    MSG_PACKAGES="Instalando paquetes del sistema..."
    MSG_VENV_CREATE="Creando entorno virtual de Python..."
    MSG_VENV_DONE="Entorno virtual creado"
    MSG_VENV_EXISTS="El entorno virtual ya existe"
    MSG_PIP="Instalando dependencias de Python..."
    MSG_PIP_DONE="Paquetes de Python instalados"
    MSG_DATA="Creando archivos de datos faltantes..."
    MSG_DATA_DONE="Archivos de datos listos"
    MSG_SERVICES="Instalando servicio systemd..."
    MSG_SERVICES_DONE="Servicio instalado"
    MSG_SERVER_START="Iniciando servidor openPadel..."
    MSG_SERVER_STARTED="¡Servidor iniciado correctamente!"
    MSG_SERVER_RUNNING="Servidor disponible en:"
    MSG_ACCESS_QUESTION_PREFIX="¿Puedes acceder a http://"
    MSG_ACCESS_QUESTION_SUFFIX=":8080 ?"
    MSG_ACCESS_OK="¡Perfecto! El servidor es accesible."
    MSG_ACCESS_FAIL="Servidor no accesible. Ver: journalctl -u padel-server -n 50"
    MSG_SERVER_ERROR="¡No se pudo iniciar el servidor!"
    MSG_PART2="PARTE 2: Punto de Acceso WiFi"
    MSG_COUNTRY_PROMPT="Por favor introduce el código de país:"
    MSG_COUNTRY_READ="Código de país (predeterminado: DE): "
    MSG_COUNTRY_SET="Código de país:"
    MSG_SUBNET_PROMPT="Por favor introduce la subred (primeros dos octetos):"
    MSG_SUBNET_EXAMPLE="Ejemplo: 10.20 para 10.20.0.0/24"
    MSG_SUBNET_READ="Subred (predeterminado: 10.20): "
    MSG_SUBNET_SET="Subred:"
    MSG_WIFI_PKGS="Instalando hostapd, dnsmasq, iptables, dhcpcd..."
    MSG_WIFI_NM="Desactivando NetworkManager, activando dhcpcd..."
    MSG_WIFI_COUNTRY="Configurando código de país WiFi..."
    MSG_WIFI_IFACE="Configurando interfaz WiFi..."
    MSG_DNSMASQ_CONF="Creando configuración de dnsmasq..."
    MSG_DNSMASQ_TEST="Probando configuración de dnsmasq..."
    MSG_DNSMASQ_OK="Configuración de dnsmasq OK"
    MSG_DNSMASQ_ERROR="¡Configuración de dnsmasq inválida!"
    MSG_HOSTAPD_CONF="Creando configuración de hostapd..."
    MSG_NAT="Configurando enrutamiento y NAT..."
    MSG_SUDO_CONF="Configurando permisos sudo..."
    MSG_SUDO_DONE="Permisos sudo configurados"
    MSG_SSID_LABEL="SSID:"
    MSG_PASS_LABEL="Contraseña:"
    MSG_IP_LABEL="Dirección IP:"
    MSG_WEB_LABEL="Interfaz web:"
    MSG_WEB_WLAN="Vía WiFi"
    MSG_WEB_ETH="Vía Ethernet:    "
    MSG_WIFI_DONE="¡Punto de acceso WiFi configurado!"
    MSG_SUMMARY_TITLE="¡Instalación completa!"
    MSG_SUMMARY="Resumen:"
    MSG_SERVER_CHECK="Servidor openPadel"
    MSG_AP_CHECK="Punto de Acceso WiFi"
    MSG_HINT="¡Nota: El SSID y la contraseña se pueden cambiar desde la interfaz web!"
    MSG_COMMANDS="Comandos útiles:"
    MSG_CMD_STATUS="Ver estado:      "
    MSG_CMD_RESTART="Reiniciar:       "
    MSG_CMD_LOGS="Ver logs:        "
    MSG_REBOOT_QUESTION="¿Reiniciar el Raspberry Pi ahora?"
    MSG_REBOOT_OPT1="1) Reiniciar ahora (recomendado)"
    MSG_REBOOT_OPT2="2) Más tarde – reiniciar manualmente con: sudo reboot"
    MSG_REBOOT_CHOICE="Tu elección (1/2): "
    MSG_REBOOTING="Reiniciando el sistema..."
    MSG_ENJOY="¡Disfruta openPadel!"
    ;;
*)
    MSG_TITLE="openPadel - Server-Only Installation"
    MSG_SUBTITLE="(eigene Kamera / eigenes Display)"
    MSG_ROOT_ERROR="FEHLER: Als root ausführen: sudo ./install_serveronly.sh"
    MSG_WORKDIR="Arbeitsverzeichnis"
    MSG_USER_LABEL="Benutzer"
    MSG_PART1="TEIL 1: openPadel Server"
    MSG_PACKAGES="Installiere System-Pakete..."
    MSG_VENV_CREATE="Erstelle Python Virtual Environment..."
    MSG_VENV_DONE="Virtual Environment erstellt"
    MSG_VENV_EXISTS="Virtual Environment existiert bereits"
    MSG_PIP="Installiere Python-Abhängigkeiten..."
    MSG_PIP_DONE="Python-Pakete installiert"
    MSG_DATA="Erstelle fehlende Datendateien..."
    MSG_DATA_DONE="Datendateien bereit"
    MSG_SERVICES="Installiere systemd-Dienst..."
    MSG_SERVICES_DONE="Dienst installiert"
    MSG_SERVER_START="Starte openPadel Server..."
    MSG_SERVER_STARTED="Server erfolgreich gestartet!"
    MSG_SERVER_RUNNING="Server erreichbar unter:"
    MSG_ACCESS_QUESTION_PREFIX="Kannst du http://"
    MSG_ACCESS_QUESTION_SUFFIX=":8080 aufrufen?"
    MSG_ACCESS_OK="Perfekt! Server ist erreichbar."
    MSG_ACCESS_FAIL="Server nicht erreichbar. Prüfe: journalctl -u padel-server -n 50"
    MSG_SERVER_ERROR="Server konnte nicht gestartet werden!"
    MSG_PART2="TEIL 2: WiFi Access Point"
    MSG_COUNTRY_PROMPT="Bitte Ländercode eingeben:"
    MSG_COUNTRY_READ="Ländercode (Standard: DE): "
    MSG_COUNTRY_SET="Ländercode:"
    MSG_SUBNET_PROMPT="Bitte Subnetz eingeben (erste zwei Oktette):"
    MSG_SUBNET_EXAMPLE="Beispiel: 10.20 für 10.20.0.0/24"
    MSG_SUBNET_READ="Subnetz (Standard: 10.20): "
    MSG_SUBNET_SET="Subnetz:"
    MSG_WIFI_PKGS="Installiere hostapd, dnsmasq, iptables, dhcpcd..."
    MSG_WIFI_NM="Deaktiviere NetworkManager, aktiviere dhcpcd..."
    MSG_WIFI_COUNTRY="Setze WiFi-Ländercode..."
    MSG_WIFI_IFACE="Konfiguriere WiFi-Interface..."
    MSG_DNSMASQ_CONF="Erstelle dnsmasq-Konfiguration..."
    MSG_DNSMASQ_TEST="Teste dnsmasq-Konfiguration..."
    MSG_DNSMASQ_OK="dnsmasq-Konfiguration OK"
    MSG_DNSMASQ_ERROR="dnsmasq-Konfiguration ungültig!"
    MSG_HOSTAPD_CONF="Erstelle hostapd-Konfiguration..."
    MSG_NAT="Konfiguriere Routing und NAT..."
    MSG_SUDO_CONF="Konfiguriere sudo-Berechtigungen..."
    MSG_SUDO_DONE="sudo-Berechtigungen konfiguriert"
    MSG_SSID_LABEL="SSID:"
    MSG_PASS_LABEL="Passwort:"
    MSG_IP_LABEL="IP-Adresse:"
    MSG_WEB_LABEL="Web-Interface:"
    MSG_WEB_WLAN="Über WiFi"
    MSG_WEB_ETH="Über Ethernet:   "
    MSG_WIFI_DONE="WiFi Access Point konfiguriert!"
    MSG_SUMMARY_TITLE="Installation abgeschlossen!"
    MSG_SUMMARY="Zusammenfassung:"
    MSG_SERVER_CHECK="openPadel Server"
    MSG_AP_CHECK="WiFi Access Point"
    MSG_HINT="Hinweis: SSID und Passwort können über das Web-Interface geändert werden!"
    MSG_COMMANDS="Nützliche Befehle:"
    MSG_CMD_STATUS="Status prüfen:   "
    MSG_CMD_RESTART="Server neustarten: "
    MSG_CMD_LOGS="Logs anzeigen:   "
    MSG_REBOOT_QUESTION="Raspberry Pi jetzt neu starten?"
    MSG_REBOOT_OPT1="1) Jetzt neu starten (empfohlen)"
    MSG_REBOOT_OPT2="2) Später – manuell neu starten mit: sudo reboot"
    MSG_REBOOT_CHOICE="Deine Wahl (1/2): "
    MSG_REBOOTING="System wird neu gestartet..."
    MSG_ENJOY="Viel Spaß mit openPadel!"
    ;;
esac

# ==============================================================================
# HELPER
# ==============================================================================
ask_yes_no() {
    local prompt="$1"
    while true; do
        read -p "$prompt (yes/no): " yn
        case "$yn" in
            [Yy]*) return 0 ;;
            [Nn]*) return 1 ;;
        esac
    done
}

# ==============================================================================
# START
# ==============================================================================
clear
echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  ${MSG_TITLE}${NC}"
echo -e "${GREEN}║  ${MSG_SUBTITLE}${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}${MSG_ROOT_ERROR}${NC}"
    exit 1
fi

echo -e "${BLUE}${MSG_WORKDIR}:${NC} $SCRIPT_DIR"
echo -e "${BLUE}${MSG_USER_LABEL}:${NC} $ACTUAL_USER"
echo ""

OS_CODENAME=$(. /etc/os-release && echo "$VERSION_CODENAME")

# Python: Bookworm (3.11) und Trixie (3.13) - alle Pakete aus requirements.txt
# gibt es für beide als fertige 64-Bit-Wheels (mediapipe ab 1.0 ist
# unabhängig von der Python-Version).
PYTHON_BIN="python3"

# ==============================================================================
# PART 1: SERVER
# ==============================================================================
echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  ${MSG_PART1}${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

echo -e "${YELLOW}[1/5]${NC} ${MSG_PACKAGES}"
apt-get update -qq
GLIB_PKG="libglib2.0-0"
[ "$OS_CODENAME" = "trixie" ] && GLIB_PKG="libglib2.0-0t64"

apt-get install -y \
    python3-pip python3-venv git \
    rpicam-apps \
    qrencode \
    iw \
    libgl1 "$GLIB_PKG" \
    -qq 2>/dev/null || true
usermod -aG video "$ACTUAL_USER" 2>/dev/null || true

echo -e "${YELLOW}[2/5]${NC} ${MSG_VENV_CREATE}"
if [ ! -d "$SCRIPT_DIR/.venv" ]; then
    su - $ACTUAL_USER -c "cd $SCRIPT_DIR && $PYTHON_BIN -m venv .venv"
    echo -e "${GREEN}${MSG_VENV_DONE}${NC}"
else
    echo -e "${GREEN}${MSG_VENV_EXISTS}${NC}"
fi

echo -e "${YELLOW}[3/5]${NC} ${MSG_PIP}"
su - $ACTUAL_USER -c "cd $SCRIPT_DIR && source .venv/bin/activate && pip install --quiet -r requirements.txt"
echo -e "${GREEN}${MSG_PIP_DONE}${NC}"

echo -e "${YELLOW}[4/5]${NC} ${MSG_DATA}"
mkdir -p "$SCRIPT_DIR/data"
if [ ! -f "$SCRIPT_DIR/data/match_history.json" ]; then
    echo "[]" > "$SCRIPT_DIR/data/match_history.json"
fi
if [ ! -f "$SCRIPT_DIR/data/stats.json" ]; then
    echo '{"history":[]}' > "$SCRIPT_DIR/data/stats.json"
fi
if [ ! -f "$SCRIPT_DIR/data/state_backup.json" ] && [ -f "$SCRIPT_DIR/data/state.json" ]; then
    cp "$SCRIPT_DIR/data/state.json" "$SCRIPT_DIR/data/state_backup.json"
fi
if [ ! -f "$SCRIPT_DIR/data/wifi_config.json" ]; then
    echo '{"ssid_suffix":"","created":""}' > "$SCRIPT_DIR/data/wifi_config.json"
fi
chown -R $ACTUAL_USER:$ACTUAL_USER "$SCRIPT_DIR/data"
echo -e "${GREEN}${MSG_DATA_DONE}${NC}"

if [ ! -f "$SCRIPT_DIR/start_server.sh" ]; then
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

echo -e "${YELLOW}[5/5]${NC} ${MSG_SERVICES}"
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

systemctl daemon-reload
systemctl enable padel-server.service
echo -e "${GREEN}${MSG_SERVICES_DONE}${NC}"

echo ""
echo -e "${YELLOW}${MSG_SERVER_START}${NC}"
systemctl restart padel-server.service
sleep 4

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
    if ask_yes_no "${MSG_ACCESS_QUESTION_PREFIX}${IP_ADDRESS}${MSG_ACCESS_QUESTION_SUFFIX}"; then
        echo -e "${GREEN}${MSG_ACCESS_OK}${NC}"
        SERVER_OK=1
    else
        echo -e "${YELLOW}${MSG_ACCESS_FAIL}${NC}"
    fi
else
    echo -e "${RED}${MSG_SERVER_ERROR}${NC}"
    echo "  journalctl -u padel-server.service -n 50"
fi

# ==============================================================================
# PART 2: WIFI AP
# ==============================================================================
echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  ${MSG_PART2}${NC}"
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
# Trixie: NM's wpa_supplicant-Instanz muss explizit gestoppt werden
systemctl stop wpa_supplicant 2>/dev/null || true
systemctl disable wpa_supplicant 2>/dev/null || true
systemctl mask wpa_supplicant 2>/dev/null || true
systemctl enable dhcpcd
systemctl start dhcpcd
systemctl stop hostapd 2>/dev/null || true
systemctl stop dnsmasq 2>/dev/null || true
systemctl unmask hostapd 2>/dev/null || true

echo -e "${YELLOW}[3/8]${NC} ${MSG_WIFI_COUNTRY}"
raspi-config nonint do_wifi_country $COUNTRY_CODE

SERIAL=$(cat /proc/cpuinfo | grep Serial | awk '{print $3}' | tail -c 9)
[ -z "$SERIAL" ] && SERIAL="00000000"
SSID="openPadel_${SERIAL}"
PASSWORD="openPadel"

cat > "$SCRIPT_DIR/data/wifi_ap_settings.json" << EOFJSON
{"ssid": "$SSID", "password": "$PASSWORD"}
EOFJSON
chown "$ACTUAL_USER:$ACTUAL_USER" "$SCRIPT_DIR/data/wifi_ap_settings.json"

cat > "$SCRIPT_DIR/data/wifi_config.json" << EOFJSON2
{"ssid_suffix": "${SERIAL}", "country_code": "${COUNTRY_CODE}", "channel": 1, "created": "$(date -Iseconds)"}
EOFJSON2
chown "$ACTUAL_USER:$ACTUAL_USER" "$SCRIPT_DIR/data/wifi_config.json"

echo -e "${BLUE}${MSG_SSID_LABEL}${NC} $SSID"
echo -e "${BLUE}${MSG_PASS_LABEL}${NC} $PASSWORD"

echo -e "${YELLOW}[4/8]${NC} ${MSG_WIFI_IFACE}"
[ -f /etc/dhcpcd.conf ] && mv /etc/dhcpcd.conf /etc/dhcpcd.conf.old
cat > /etc/dhcpcd.conf << EOFDHCP
interface wlan0
    static ip_address=${SUBNET}.1.1/24
    nohook wpa_supplicant
EOFDHCP
systemctl restart dhcpcd

echo -e "${YELLOW}[5/8]${NC} ${MSG_DNSMASQ_CONF}"
[ -f /etc/dnsmasq.conf ] && mv /etc/dnsmasq.conf /etc/dnsmasq.conf_alt
cat > /etc/dnsmasq.conf << EOFDNS
interface=wlan0
dhcp-range=${SUBNET}.1.2,${SUBNET}.1.20,255.255.255.0,24h
domain=local
address=/openpadel.local/${SUBNET}.1.1
EOFDNS

echo -e "${YELLOW}[6/8]${NC} ${MSG_DNSMASQ_TEST}"
if dnsmasq --test 2>&1; then
    echo -e "${GREEN}${MSG_DNSMASQ_OK}${NC}"
else
    echo -e "${RED}${MSG_DNSMASQ_ERROR}${NC}"
fi
systemctl enable dnsmasq
systemctl restart dnsmasq 2>/dev/null || true

echo -e "${YELLOW}[7/8]${NC} ${MSG_HOSTAPD_CONF}"
cat > /etc/hostapd/hostapd.conf << EOFHOSTAPD
interface=wlan0
driver=nl80211
ssid=${SSID}
hw_mode=g
channel=7
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=${PASSWORD}
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP
country_code=${COUNTRY_CODE}
EOFHOSTAPD
echo 'DAEMON_CONF="/etc/hostapd/hostapd.conf"' > /etc/default/hostapd
systemctl unmask hostapd
systemctl enable hostapd
systemctl restart hostapd 2>/dev/null || true

echo -e "${YELLOW}[8/8]${NC} ${MSG_NAT}"
echo "net.ipv4.ip_forward=1" >> /etc/sysctl.conf
sysctl -p /etc/sysctl.conf -q
iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
iptables -A FORWARD -i eth0 -o wlan0 -m state --state RELATED,ESTABLISHED -j ACCEPT
iptables -A FORWARD -i wlan0 -o eth0 -j ACCEPT

if dpkg -l iptables-persistent &>/dev/null; then
    mkdir -p /etc/iptables
    sh -c "iptables-save > /etc/iptables/rules.v4"
else
    sh -c "iptables-save > /etc/iptables.ipv4.nat"
    if [ ! -f /etc/rc.local ]; then
        printf '#!/bin/sh -e\nexit 0\n' > /etc/rc.local
        chmod +x /etc/rc.local
        systemctl enable rc-local 2>/dev/null || true
    fi
    if ! grep -q "iptables-restore" /etc/rc.local; then
        sed -i '/^exit 0/i iptables-restore < /etc/iptables.ipv4.nat' /etc/rc.local
    fi
fi

echo -e "${YELLOW}${MSG_SUDO_CONF}${NC}"
cat > /etc/sudoers.d/padel-web << EOFSUDO
$ACTUAL_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl start hostapd
$ACTUAL_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl stop hostapd
$ACTUAL_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart hostapd
$ACTUAL_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl status hostapd
$ACTUAL_USER ALL=(ALL) NOPASSWD: /usr/sbin/iw dev wlan0 station dump
$ACTUAL_USER ALL=(ALL) NOPASSWD: /sbin/shutdown -h now
$ACTUAL_USER ALL=(ALL) NOPASSWD: /sbin/reboot
EOFSUDO
chmod 440 /etc/sudoers.d/padel-web
echo -e "${GREEN}${MSG_SUDO_DONE}${NC}"

echo ""
echo -e "${GREEN}${MSG_WIFI_DONE}${NC}"

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
[ $SERVER_OK -eq 1 ] && echo -e "  ${GREEN}✓ ${MSG_SERVER_CHECK}${NC}" || echo -e "  ${YELLOW}? ${MSG_SERVER_CHECK}${NC}"
echo -e "  ${GREEN}✓ ${MSG_AP_CHECK}${NC}"
echo ""
echo -e "${BLUE}${MSG_COMMANDS}${NC}"
echo -e "  ${MSG_CMD_STATUS}${GREEN}sudo systemctl status padel-server hostapd dnsmasq${NC}"
echo -e "  ${MSG_CMD_RESTART}${GREEN}sudo systemctl restart padel-server${NC}"
echo -e "  ${MSG_CMD_LOGS}${GREEN}journalctl -u padel-server -f${NC}"
echo ""
echo -e "${BLUE}${MSG_WEB_LABEL}${NC}"
echo -e "  ${MSG_WEB_WLAN} (${SSID}): ${GREEN}http://${SUBNET}.1.1:8080${NC}"
[ -n "$IP_ADDRESS" ] && echo -e "  ${MSG_WEB_ETH}${GREEN}http://${IP_ADDRESS}:8080${NC}"
echo ""
echo -e "${YELLOW}${MSG_HINT}${NC}"
echo ""

# ==============================================================================
# REBOOT
# ==============================================================================
echo -e "${YELLOW}${MSG_REBOOT_QUESTION}${NC}"
echo -e "  ${MSG_REBOOT_OPT1}"
echo -e "  ${MSG_REBOOT_OPT2}"
echo ""
read -p "$MSG_REBOOT_CHOICE" REBOOT_CHOICE
if [ "$REBOOT_CHOICE" = "1" ]; then
    echo ""
    echo -e "${GREEN}${MSG_REBOOTING}${NC}"
    sleep 2
    reboot
else
    echo ""
    echo -e "${GREEN}${MSG_ENJOY}${NC}"
    echo ""
fi
