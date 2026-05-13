#!/usr/bin/env bash
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

clear
echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║         openPadel - Pre-Setup (SPI + Kamera)               ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}FEHLER: Bitte als root ausführen: sudo ./presetup.sh${NC}"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ACTUAL_USER="${SUDO_USER:-$USER}"

# Korrekten Config-Pfad ermitteln (Pi 5 vs. ältere Modelle)
if [ -f /boot/firmware/config.txt ]; then
    BOOT_CONFIG="/boot/firmware/config.txt"
else
    BOOT_CONFIG="/boot/config.txt"
fi

echo -e "${BLUE}Boot-Config:${NC} $BOOT_CONFIG"
echo ""

# ==============================================================================
# SPRACHE WÄHLEN
# ==============================================================================
echo -e "${YELLOW}Sprache / Language / Idioma:${NC}"
echo "  1) Deutsch"
echo "  2) English"
echo "  3) Español"
echo ""
read -p "Auswahl / Choice / Selección (1-3, Standard/Default: 1): " LANG_CHOICE

case "$LANG_CHOICE" in
    2) LANGUAGE="en" ;;
    3) LANGUAGE="es" ;;
    *) LANGUAGE="de" ;;
esac

mkdir -p "$SCRIPT_DIR/data"
echo "{\"language\": \"$LANGUAGE\"}" > "$SCRIPT_DIR/data/language_settings.json"
chown "$ACTUAL_USER:$ACTUAL_USER" "$SCRIPT_DIR/data/language_settings.json"
echo -e "${GREEN}✓ Sprache gespeichert: $LANGUAGE${NC}"
echo ""

CHANGED=0

# SPI aktivieren
if grep -q "^dtparam=spi=on" "$BOOT_CONFIG"; then
    echo -e "${GREEN}✓ SPI bereits aktiviert${NC}"
else
    echo "dtparam=spi=on" >> "$BOOT_CONFIG"
    echo -e "${GREEN}✓ SPI aktiviert${NC}"
    CHANGED=1
fi

# Kamera aktivieren
if grep -q "^camera_auto_detect" "$BOOT_CONFIG"; then
    echo -e "${GREEN}✓ Kamera bereits aktiviert${NC}"
else
    echo "camera_auto_detect=1" >> "$BOOT_CONFIG"
    echo -e "${GREEN}✓ Kamera aktiviert${NC}"
    CHANGED=1
fi

echo ""

if [ $CHANGED -eq 0 ]; then
    echo -e "${GREEN}Alles bereits konfiguriert – kein Neustart nötig.${NC}"
    echo -e "Du kannst jetzt direkt ${YELLOW}sudo ./install_complete.sh${NC} ausführen."
    echo ""
    exit 0
fi

echo -e "${YELLOW}Neustart erforderlich, damit SPI und Kamera aktiv werden.${NC}"
echo ""
echo -e "Danach: ${YELLOW}sudo ./install_complete.sh${NC}"
echo ""
read -p "Jetzt neu starten? (yes/no): " ANSWER
if [[ "$ANSWER" =~ ^[yY] ]]; then
    echo -e "${GREEN}System wird neu gestartet...${NC}"
    sleep 1
    reboot
else
    echo -e "${YELLOW}Bitte manuell neu starten: sudo reboot${NC}"
fi
