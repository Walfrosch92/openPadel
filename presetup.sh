#!/usr/bin/env bash
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

clear
echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║       openPadel - Pre-Setup (SPI + Camera)                 ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}ERROR / FEHLER / ERROR: sudo ./presetup.sh${NC}"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ACTUAL_USER="${SUDO_USER:-$USER}"

# Detect boot config path (Pi 5 vs older models)
if [ -f /boot/firmware/config.txt ]; then
    BOOT_CONFIG="/boot/firmware/config.txt"
else
    BOOT_CONFIG="/boot/config.txt"
fi

# ==============================================================================
# LANGUAGE SELECTION
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

# ==============================================================================
# TRANSLATIONS
# ==============================================================================
case "$LANGUAGE" in
"en")
    MSG_BOOT_CFG="Boot config"
    MSG_LANG_SAVED="Language saved"
    MSG_SPI_EXISTS="SPI already enabled"
    MSG_SPI_DONE="SPI enabled"
    MSG_CAM_EXISTS="Camera already enabled"
    MSG_CAM_DONE="Camera enabled"
    MSG_ALL_DONE="Everything already configured – no reboot required."
    MSG_NEXT_STEP="You can now run"
    MSG_REBOOT_REQUIRED="Reboot required to activate SPI and camera."
    MSG_AFTER_REBOOT="Then run"
    MSG_REBOOT_QUESTION="Reboot now? (yes/no): "
    MSG_REBOOTING="System is rebooting..."
    MSG_REBOOT_MANUAL="Please reboot manually: sudo reboot"
    ;;
"es")
    MSG_BOOT_CFG="Boot config"
    MSG_LANG_SAVED="Idioma guardado"
    MSG_SPI_EXISTS="SPI ya estaba activado"
    MSG_SPI_DONE="SPI activado"
    MSG_CAM_EXISTS="Cámara ya estaba activada"
    MSG_CAM_DONE="Cámara activada"
    MSG_ALL_DONE="Todo ya configurado – no es necesario reiniciar."
    MSG_NEXT_STEP="Ahora puedes ejecutar"
    MSG_REBOOT_REQUIRED="Reinicio necesario para activar SPI y cámara."
    MSG_AFTER_REBOOT="Luego ejecuta"
    MSG_REBOOT_QUESTION="¿Reiniciar ahora? (yes/no): "
    MSG_REBOOTING="El sistema se está reiniciando..."
    MSG_REBOOT_MANUAL="Por favor reinicia manualmente: sudo reboot"
    ;;
*)
    MSG_BOOT_CFG="Boot-Config"
    MSG_LANG_SAVED="Sprache gespeichert"
    MSG_SPI_EXISTS="SPI bereits aktiviert"
    MSG_SPI_DONE="SPI aktiviert"
    MSG_CAM_EXISTS="Kamera bereits aktiviert"
    MSG_CAM_DONE="Kamera aktiviert"
    MSG_ALL_DONE="Alles bereits konfiguriert – kein Neustart nötig."
    MSG_NEXT_STEP="Du kannst jetzt direkt"
    MSG_REBOOT_REQUIRED="Neustart erforderlich, damit SPI und Kamera aktiv werden."
    MSG_AFTER_REBOOT="Danach:"
    MSG_REBOOT_QUESTION="Jetzt neu starten? (yes/no): "
    MSG_REBOOTING="System wird neu gestartet..."
    MSG_REBOOT_MANUAL="Bitte manuell neu starten: sudo reboot"
    ;;
esac

echo ""
echo -e "${BLUE}${MSG_BOOT_CFG}:${NC} $BOOT_CONFIG"
echo ""

# Save language
mkdir -p "$SCRIPT_DIR/data"
echo "{\"language\": \"$LANGUAGE\"}" > "$SCRIPT_DIR/data/language_settings.json"
chown "$ACTUAL_USER:$ACTUAL_USER" "$SCRIPT_DIR/data/language_settings.json"
echo -e "${GREEN}✓ ${MSG_LANG_SAVED}: $LANGUAGE${NC}"
echo ""

CHANGED=0

# Enable SPI
if grep -q "^dtparam=spi=on" "$BOOT_CONFIG"; then
    echo -e "${GREEN}✓ ${MSG_SPI_EXISTS}${NC}"
else
    echo "dtparam=spi=on" >> "$BOOT_CONFIG"
    echo -e "${GREEN}✓ ${MSG_SPI_DONE}${NC}"
    CHANGED=1
fi

# Enable camera
if grep -q "^camera_auto_detect" "$BOOT_CONFIG"; then
    echo -e "${GREEN}✓ ${MSG_CAM_EXISTS}${NC}"
else
    echo "camera_auto_detect=1" >> "$BOOT_CONFIG"
    echo -e "${GREEN}✓ ${MSG_CAM_DONE}${NC}"
    CHANGED=1
fi

echo ""

if [ $CHANGED -eq 0 ]; then
    echo -e "${GREEN}${MSG_ALL_DONE}${NC}"
    echo -e "${MSG_NEXT_STEP} ${YELLOW}sudo ./install_complete.sh${NC}"
    echo ""
    exit 0
fi

echo -e "${YELLOW}${MSG_REBOOT_REQUIRED}${NC}"
echo ""
echo -e "${MSG_AFTER_REBOOT} ${YELLOW}sudo ./install_complete.sh${NC}"
echo ""
read -p "$MSG_REBOOT_QUESTION" ANSWER
if [[ "$ANSWER" =~ ^[yY] ]]; then
    echo -e "${GREEN}${MSG_REBOOTING}${NC}"
    sleep 1
    reboot
else
    echo -e "${YELLOW}${MSG_REBOOT_MANUAL}${NC}"
fi
