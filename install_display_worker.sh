#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# Display Worker Installation Script
# Installiert den Display Worker als systemd Service
# ==============================================================================

echo "🚀 Display Worker Installation"
echo "================================"
echo ""

# Prüfe ob Skript als Root ausgeführt wird
if [ "$EUID" -ne 0 ]; then 
    echo "❌ Fehler: Dieses Skript muss als root ausgeführt werden"
    echo "Bitte mit 'sudo ./install_display_worker.sh' ausführen"
    exit 1
fi

# Bestimme aktuelles Verzeichnis und Benutzer
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ACTUAL_USER="${SUDO_USER:-$USER}"
SERVICE_FILE="padel-display.service"

echo "📁 Arbeitsverzeichnis: $SCRIPT_DIR"
echo "👤 Benutzer: $ACTUAL_USER"
echo ""

# Prüfe ob Service-Datei existiert
if [ ! -f "$SCRIPT_DIR/$SERVICE_FILE" ]; then
    echo "❌ Fehler: $SERVICE_FILE nicht gefunden in $SCRIPT_DIR"
    exit 1
fi

# Prüfe ob display_worker.py existiert
if [ ! -f "$SCRIPT_DIR/display_worker.py" ]; then
    echo "❌ Fehler: display_worker.py nicht gefunden in $SCRIPT_DIR"
    exit 1
fi

# Prüfe ob start_display_worker.sh existiert
if [ ! -f "$SCRIPT_DIR/start_display_worker.sh" ]; then
    echo "❌ Fehler: start_display_worker.sh nicht gefunden in $SCRIPT_DIR"
    exit 1
fi

# Prüfe ob start_display_worker.sh ausführbar ist
if [ ! -x "$SCRIPT_DIR/start_display_worker.sh" ]; then
    echo "🔧 Mache start_display_worker.sh ausführbar..."
    chmod +x "$SCRIPT_DIR/start_display_worker.sh"
fi

echo "✅ Alle erforderlichen Dateien gefunden"
echo ""

# Erstelle temporäre Service-Datei mit korrekten Pfaden
TEMP_SERVICE="/tmp/padel-display.service.tmp"
cat > "$TEMP_SERVICE" << EOF
[Unit]
Description=Padel Display Worker
After=padel-server.service
Requires=padel-server.service

[Service]
Type=simple
User=$ACTUAL_USER
WorkingDirectory=$SCRIPT_DIR
ExecStart=$SCRIPT_DIR/start_display_worker.sh
Restart=always
RestartSec=10
Environment="DISPLAY=:0"
Environment="XAUTHORITY=/home/$ACTUAL_USER/.Xauthority"

[Install]
WantedBy=multi-user.target
EOF

echo "📝 Service-Datei erstellt mit folgenden Parametern:"
echo "   - Benutzer: $ACTUAL_USER"
echo "   - Arbeitsverzeichnis: $SCRIPT_DIR"
echo "   - Start-Skript: $SCRIPT_DIR/start_display_worker.sh"
echo ""

# Stoppe Service falls er läuft
if systemctl is-active --quiet padel-display.service; then
    echo "🛑 Stoppe laufenden Display Worker Service..."
    systemctl stop padel-display.service
fi

# Kopiere Service-Datei
echo "📋 Kopiere Service-Datei nach /etc/systemd/system/..."
cp "$TEMP_SERVICE" /etc/systemd/system/padel-display.service
rm "$TEMP_SERVICE"

# Setze korrekte Berechtigungen
chmod 644 /etc/systemd/system/padel-display.service

# Reload systemd
echo "🔄 Lade systemd neu..."
systemctl daemon-reload

# Aktiviere Service
echo "✅ Aktiviere Display Worker Service..."
systemctl enable padel-display.service

echo ""
echo "✨ Installation abgeschlossen!"
echo ""
echo "📊 Service Status:"
systemctl status padel-display.service --no-pager || true
echo ""

# Prüfe ob padel-server läuft
if systemctl is-active --quiet padel-server.service; then
    echo "✅ Padel Server läuft bereits"
    echo ""
    echo "🎬 Starte Display Worker Service..."
    systemctl start padel-display.service
    
    # Warte kurz und prüfe Status
    sleep 2
    
    if systemctl is-active --quiet padel-display.service; then
        echo "✅ Display Worker Service läuft!"
    else
        echo "⚠️  Display Worker Service konnte nicht gestartet werden"
        echo "Prüfe die Logs mit: journalctl -u padel-display.service -n 50"
    fi
else
    echo "⚠️  Padel Server läuft nicht"
    echo "Der Display Worker wird automatisch starten, sobald der Server läuft"
    echo ""
    echo "Starte den Server mit: ./start_server.sh"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🎉 Display Worker Installation abgeschlossen!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📌 Wichtige Befehle:"
echo ""
echo "   Server starten:        ./start_server.sh"
echo "   Service Status:        sudo systemctl status padel-display.service"
echo "   Service neu starten:   sudo systemctl restart padel-display.service"
echo "   Service Logs:          journalctl -u padel-display.service -f"
echo "   Service deaktivieren:  sudo systemctl disable padel-display.service"
echo ""
echo "💡 Der Display Worker startet jetzt automatisch beim Systemstart"
echo "   und nach dem Padel Server."
echo ""
