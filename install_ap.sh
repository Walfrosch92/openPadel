#!/bin/bash
# Installation Script für WiFi Access Point nach https://www.elektronik-kompendium.de

echo "======================================"
echo "WiFi Access Point Installation"
echo "======================================"

# Prüfe Root-Rechte
if [ "$EUID" -ne 0 ]; then
    echo "Bitte als root ausführen: sudo bash install_ap.sh"
    exit 1
fi

# Hole aktuellen User
ACTUAL_USER="${SUDO_USER:-$USER}"

# Frage nach Ländercode
echo ""
echo "Bitte Ländercode eingeben:"
echo "  AT = Österreich"
echo "  DE = Deutschland"
echo "  US = United States"
echo "  GB = Großbritannien"
echo "  CH = Schweiz"
echo ""
read -p "Ländercode (Standard: DE): " COUNTRY_CODE
COUNTRY_CODE=${COUNTRY_CODE:-DE}
echo "Ländercode: $COUNTRY_CODE"

# Frage nach Subnetz
echo ""
echo "Bitte Subnetz eingeben (erste zwei Oktette):"
echo "  Beispiel: 10.20 für 10.20.0.0/24"
echo ""
read -p "Subnetz (Standard: 10.20): " SUBNET
SUBNET=${SUBNET:-10.20}
echo "Subnetz: ${SUBNET}.0.0/24"
echo ""

# Software installieren
echo "Installiere benötigte Software..."
apt install -y dnsmasq hostapd iptables dhcpcd5

# NetworkManager deaktivieren und dhcpcd aktivieren
echo "Deaktiviere NetworkManager, aktiviere dhcpcd..."
systemctl stop NetworkManager 2>/dev/null || true
systemctl disable NetworkManager 2>/dev/null || true
systemctl enable dhcpcd
systemctl start dhcpcd

# Services stoppen
systemctl stop hostapd 2>/dev/null || true
systemctl stop dnsmasq 2>/dev/null || true
systemctl unmask hostapd 2>/dev/null || true

# Setze Ländercode mit raspi-config
echo "Setze WLAN-Ländercode..."
raspi-config nonint do_wifi_country $COUNTRY_CODE

# WLAN-Interface konfigurieren (dhcpcd)
echo "Konfiguriere WLAN-Interface..."
if [ -f /etc/dhcpcd.conf ]; then
    mv /etc/dhcpcd.conf /etc/dhcpcd.conf.old
fi

cat > /etc/dhcpcd.conf << EOFDHCP
interface wlan0
    static ip_address=${SUBNET}.1.1/24
    nohook wpa_supplicant
EOFDHCP

systemctl restart dhcpcd

# DHCP-Server und DNS-Cache einrichten (dnsmasq)
echo "Konfiguriere dnsmasq..."
if [ -f /etc/dnsmasq.conf ]; then
    mv /etc/dnsmasq.conf /etc/dnsmasq.conf_alt
fi

cat > /etc/dnsmasq.conf << EOFDNSMASQ
# DHCP-Server aktiv für WLAN-Interface
interface=wlan0

# DHCP-Server nicht aktiv für bestehendes Netzwerk
no-dhcp-interface=eth0

# IPv4-Adressbereich und Lease-Time
dhcp-range=${SUBNET}.1.100,${SUBNET}.1.200,255.255.255.0,24h

# DNS
dhcp-option=option:dns-server,${SUBNET}.1.1
EOFDNSMASQ

# dnsmasq testen
echo "Teste dnsmasq Konfiguration..."
dnsmasq --test -C /etc/dnsmasq.conf

systemctl restart dnsmasq
systemctl enable dnsmasq

# Hole Serial für eindeutigen SSID
SERIAL=$(cat /proc/cpuinfo | grep Serial | awk '{print $3}' | tail -c 9)
if [ -z "$SERIAL" ]; then
    SERIAL="00000000"
fi

SSID="openPadel_${SERIAL}"
PASSWORD="openPadel"

# WLAN-AP-Host einrichten (hostapd)
echo "Konfiguriere hostapd..."
cat > /etc/hostapd/hostapd.conf << EOFHOSTAPD
# WLAN-Router-Betrieb

# Schnittstelle und Treiber
interface=wlan0
#driver=nl80211

# WLAN-Konfiguration
ssid=${SSID}
channel=1
hw_mode=g
ieee80211n=1
ieee80211d=1
country_code=${COUNTRY_CODE}
wmm_enabled=1

# WLAN-Verschlüsselung
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

# Routing und NAT für Internet-Verbindung konfigurieren
echo "Konfiguriere Routing und NAT..."
if ! grep -q "net.ipv4.ip_forward=1" /etc/sysctl.conf; then
    echo "net.ipv4.ip_forward=1" >> /etc/sysctl.conf
fi

iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
sh -c "iptables-save > /etc/iptables.ipv4.nat"

if ! grep -q "iptables-restore" /etc/rc.local; then
    sed -i '/^exit 0/i iptables-restore < /etc/iptables.ipv4.nat' /etc/rc.local
fi

# Services aktivieren
systemctl unmask hostapd
systemctl enable hostapd
systemctl enable dnsmasq

# Konfiguriere sudo-Rechte für WiFi-Verwaltung über Web-Interface
echo "Konfiguriere sudo-Rechte für Web-Interface..."
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
EOFSUDO

chmod 0440 /etc/sudoers.d/padel-wifi

# Deaktiviere wifi-ap.service falls vorhanden (Konflikt vermeiden)
if systemctl is-enabled wifi-ap.service >/dev/null 2>&1; then
    echo "Deaktiviere wifi-ap.service (wird durch hostapd ersetzt)..."
    systemctl stop wifi-ap.service 2>/dev/null || true
    systemctl disable wifi-ap.service 2>/dev/null || true
fi

echo ""
echo "======================================"
echo "Installation abgeschlossen!"
echo "======================================"
echo ""
echo "Verbindungsdaten:"
echo "  SSID: ${SSID}"
echo "  Passwort: ${PASSWORD}"
echo "  Raspberry Pi IP: ${SUBNET}.1.1"
echo ""
echo "Nützliche Befehle:"
echo "  sudo systemctl status hostapd       - hostapd Status prüfen"
echo "  sudo systemctl status dnsmasq       - dnsmasq Status prüfen"
echo "  sudo journalctl -u hostapd -f       - hostapd Logs anzeigen"
echo "  sudo journalctl -u dnsmasq -f       - dnsmasq Logs anzeigen"
echo ""
echo "Web-Interface: http://${SUBNET}.1.1:8080"
echo "Hinweis: SSID und Passwort können über das Web-Interface geändert werden!"
echo ""
echo "WICHTIG: Neustart erforderlich!"
echo "  sudo reboot"
echo "======================================"