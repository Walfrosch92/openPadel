#!/bin/bash
# Installation des Shutdown-Service für openPadel

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_FILE="/etc/systemd/system/openpadel-shutdown.service"

echo "=== openPadel Shutdown Service Installation ==="
echo "Project Directory: $PROJECT_DIR"

# Erstelle systemd Service
sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=openPadel Shutdown Handler
DefaultDependencies=no
Before=shutdown.target reboot.target halt.target
Requires=sysinit.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/true
ExecStop=/usr/bin/python3 $PROJECT_DIR/shutdown_helper.py \${MAINPID}
TimeoutStopSec=30
KillMode=none

[Install]
WantedBy=multi-user.target
EOF

echo "✓ Service-Datei erstellt: $SERVICE_FILE"

# Systemd neu laden
sudo systemctl daemon-reload
echo "✓ Systemd daemon-reload"

# Service aktivieren
sudo systemctl enable openpadel-shutdown.service
echo "✓ Service aktiviert"

# Status anzeigen
echo ""
echo "=== Service Status ==="
sudo systemctl status openpadel-shutdown.service --no-pager || true

echo ""
echo "=== Installation abgeschlossen ==="
echo "Der Shutdown-Helper wird nun beim Herunterfahren automatisch ausgeführt."
echo ""
echo "Befehle:"
echo "  Status:     sudo systemctl status openpadel-shutdown.service"
echo "  Deaktivieren: sudo systemctl disable openpadel-shutdown.service"
echo "  Logs:       journalctl -u openpadel-shutdown.service"
