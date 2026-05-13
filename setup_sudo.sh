#!/bin/bash
# Erlaubt dem padel-User sudo für hostapd/dnsmasq ohne Passwort

if [ "$EUID" -ne 0 ]; then 
    echo "Bitte als root ausführen: sudo ./setup_sudo.sh"
    exit 1
fi

ACTUAL_USER="${SUDO_USER:-$USER}"

echo "Konfiguriere sudo-Rechte für User: $ACTUAL_USER"

# Erstelle sudoers.d Datei
cat > /etc/sudoers.d/padel-wifi << EOF
# Erlaube padel-user WiFi AP Verwaltung ohne Passwort
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
EOF

# Setze korrekte Rechte
chmod 0440 /etc/sudoers.d/padel-wifi

echo "✓ sudo-Rechte konfiguriert"
echo ""
echo "Der User '$ACTUAL_USER' kann jetzt folgende Befehle ohne Passwort ausführen:"
echo "  - sudo systemctl restart/stop/start/status hostapd"
echo "  - sudo systemctl restart/stop/start/status dnsmasq"
echo "  - sudo cp/mv/chmod für hostapd.conf"
