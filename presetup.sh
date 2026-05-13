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

# Korrekten Config-Pfad ermitteln (Pi 5 vs. ältere Modelle)
if [ -f /boot/firmware/config.txt ]; then
    BOOT_CONFIG="/boot/firmware/config.txt"
else
    BOOT_CONFIG="/boot/config.txt"
fi

echo -e "${BLUE}Boot-Config:${NC} $BOOT_CONFIG"
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
