#!/bin/bash
# WiFi Access Point Installation für Raspberry Pi
# Autor: openPadel Team
# Beschreibung: Installiert und konfiguriert einen WiFi Access Point

set -e  # Stop bei Fehler

# Farben für Output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}================================${NC}"
echo -e "${GREEN}WiFi Access Point Installation${NC}"
echo -e "${GREEN}================================${NC}"

# Prüfe ob Script als root läuft
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}Fehler: Bitte als root ausführen (sudo ./install_wifi_ap.sh)${NC}"
    exit 1
fi

# Frage nach Subnetz
echo ""
echo -e "${YELLOW}Bitte Subnetz eingeben (erste zwei Oktette):${NC}"
echo "  Beispiel: 10.20 für 10.20.0.0/24"
echo ""
read -p "Subnetz (Standard: 10.20): " SUBNET
SUBNET=${SUBNET:-10.20}
echo -e "${GREEN}Subnetz: ${SUBNET}.0.0/24${NC}"

# Aktualisiere Paketliste
echo -e "${YELLOW}Aktualisiere Paketliste...${NC}"
apt-get update -qq

# Installiere benötigte Pakete
echo -e "${YELLOW}Installiere hostapd, dnsmasq, iptables und dhcpcd...${NC}"
apt-get install -y hostapd dnsmasq iptables dhcpcd5

# NetworkManager deaktivieren und dhcpcd aktivieren
echo -e "${YELLOW}Deaktiviere NetworkManager, aktiviere dhcpcd...${NC}"
systemctl stop NetworkManager 2>/dev/null || true
systemctl disable NetworkManager 2>/dev/null || true
systemctl enable dhcpcd
systemctl start dhcpcd

# Stoppe Services
echo -e "${YELLOW}Stoppe Services...${NC}"
systemctl stop hostapd || true
systemctl stop dnsmasq || true

# Unmask hostapd falls masked
systemctl unmask hostapd || true

# Hole Raspberry Pi Serial für eindeutigen SSID
SERIAL=$(cat /proc/cpuinfo | grep Serial | awk '{print $3}' | tail -c 9)
if [ -z "$SERIAL" ]; then
    SERIAL="00000000"
fi

SSID="openPadel_${SERIAL}"
PASSWORD="openPadel"

echo -e "${GREEN}SSID wird sein: ${SSID}${NC}"
echo -e "${GREEN}Standard-Passwort: ${PASSWORD}${NC}"

# Erstelle hostapd Konfiguration
echo -e "${YELLOW}Erstelle hostapd Konfiguration...${NC}"
cat > /etc/hostapd/hostapd.conf << EOF
interface=wlan0
#driver=nl80211
ssid=${SSID}
hw_mode=g
channel=1
ieee80211n=1
ieee80211d=1
wmm_enabled=1
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=${PASSWORD}
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
EOF

chmod 600 /etc/hostapd/hostapd.conf

# Setze hostapd config path
echo -e "${YELLOW}Konfiguriere hostapd default...${NC}"
if ! grep -q "DAEMON_CONF" /etc/default/hostapd 2>/dev/null; then
    cat >> /etc/default/hostapd << EOF
RUN_DAEMON=yes
DAEMON_CONF="/etc/hostapd/hostapd.conf"
EOF
fi

# Backup original dnsmasq config
if [ -f /etc/dnsmasq.conf ]; then
    mv /etc/dnsmasq.conf /etc/dnsmasq.conf.old
fi

# Erstelle dnsmasq Konfiguration
echo -e "${YELLOW}Erstelle dnsmasq Konfiguration...${NC}"
cat > /etc/dnsmasq.conf << EOF
# DHCP-Server aktiv für WLAN-Interface
interface=wlan0

# DHCP-Server nicht aktiv für bestehendes Netzwerk
no-dhcp-interface=eth0

# IPv4-Adressbereich und Lease-Time
dhcp-range=${SUBNET}.1.100,${SUBNET}.1.200,255.255.255.0,24h

# DNS
dhcp-option=option:dns-server,${SUBNET}.1.1
EOF

# Konfiguriere dhcpcd für statische IP
echo -e "${YELLOW}Konfiguriere dhcpcd...${NC}"
if [ -f /etc/dhcpcd.conf ]; then
    mv /etc/dhcpcd.conf /etc/dhcpcd.conf.old
fi

cat > /etc/dhcpcd.conf << EOF
interface wlan0
    static ip_address=${SUBNET}.1.1/24
    nohook wpa_supplicant
EOF

systemctl restart dhcpcd

# Aktiviere IP Forwarding
echo -e "${YELLOW}Aktiviere IP Forwarding und NAT...${NC}"
if ! grep -q "net.ipv4.ip_forward=1" /etc/sysctl.conf; then
    echo "net.ipv4.ip_forward=1" >> /etc/sysctl.conf
fi
echo 1 > /proc/sys/net/ipv4/ip_forward

# NAT konfigurieren
iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
sh -c "iptables-save > /etc/iptables.ipv4.nat"

# Konfiguriere Netzwerk Interface
echo -e "${YELLOW}Konfiguriere wlan0...${NC}"
ip addr flush dev wlan0 || true
ip addr add ${SUBNET}.1.1/24 dev wlan0 || true
ip link set wlan0 up || true

# Aktiviere Services für automatischen Start
echo -e "${YELLOW}Aktiviere Services...${NC}"
systemctl enable hostapd
systemctl enable dnsmasq

# Starte Services
echo -e "${YELLOW}Starte Services...${NC}"
systemctl restart dnsmasq
sleep 2
systemctl restart hostapd

# Prüfe Status
sleep 3
echo ""
echo -e "${GREEN}================================${NC}"
echo -e "${GREEN}Installation abgeschlossen!${NC}"
echo -e "${GREEN}================================${NC}"
echo ""

# Zeige Service Status
if systemctl is-active --quiet hostapd; then
    echo -e "${GREEN}✓ hostapd läuft${NC}"
else
    echo -e "${RED}✗ hostapd läuft NICHT${NC}"
    echo "Status: $(systemctl status hostapd --no-pager -l | head -10)"
fi

if systemctl is-active --quiet dnsmasq; then
    echo -e "${GREEN}✓ dnsmasq läuft${NC}"
else
    echo -e "${RED}✗ dnsmasq läuft NICHT${NC}"
    echo "Status: $(systemctl status dnsmasq --no-pager -l | head -10)"
fi

echo ""
echo -e "${GREEN}Verbindungsinformationen:${NC}"
echo -e "  SSID: ${YELLOW}${SSID}${NC}"
echo -e "  Passwort: ${YELLOW}${PASSWORD}${NC}"
echo -e "  IP-Adresse: ${YELLOW}${SUBNET}.1.1${NC}"
echo -e "  Web-Interface: ${YELLOW}http://${SUBNET}.1.1:8000${NC}"
echo ""
echo -e "${YELLOW}Hinweis: Diese Einstellungen können später im Admin-Panel geändert werden.${NC}"
echo ""

