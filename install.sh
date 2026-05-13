#!/bin/bash
set -e

echo "======================================"
echo "openPadel Installation Script"
echo "======================================"
echo ""

if [ ! -f "main.py" ]; then
    echo "Fehler: Bitte im Projekt-Verzeichnis ausführen!"
    exit 1
fi

echo "Schritt 1: System-Packages installieren..."
sudo apt-get update
sudo apt-get install -y python3-pip python3-venv libcamera-apps

echo ""
echo "Schritt 2: Python Virtual Environment erstellen..."
python3 -m venv .venv

echo ""
echo "Schritt 3: Dependencies installieren..."
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "Schritt 4: Verzeichnisse erstellen..."
mkdir -p data static templates

echo ""
echo "Schritt 5: Start-Script ausführbar machen..."
chmod +x start_server.sh

echo ""
echo "======================================"
echo "Installation abgeschlossen!"
echo "======================================"
echo ""
echo "Server starten mit:"
echo "  ./start_server.sh"
echo ""
echo "Oder manuell:"
echo "  source .venv/bin/activate"
echo "  python3 main.py"
echo ""
echo "Web-Interface öffnen:"
echo "  http://localhost:8000"
echo ""
echo "Auto-Start einrichten:"
echo "  sudo cp padel-server.service /etc/systemd/system/"
echo "  sudo systemctl enable padel-server.service"
echo "  sudo systemctl start padel-server.service"
echo ""
