#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

echo "🛑 Stoppe laufende Dienste..."

# Finde und stoppe alte Uvicorn-Prozesse
pkill -f "uvicorn.*main:app" || true

# Finde und stoppe alte Display-Worker-Prozesse
pkill -f "display_worker.py" || true

# Warte kurz
sleep 2

echo "🔄 Starte Padel-Server & Display-Worker…"

# === Server (im venv) ========================================================
if [[ ! -d ".venv" ]]; then
  echo "📦 Erstelle virtuelle Umgebung (.venv)…"
  python3 -m venv .venv
fi

. .venv/bin/activate
pip install -q -r requirements.txt
deactivate

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8080}"
APP_MODULE="${APP_MODULE:-main:app}"

echo "🚀 Starte Uvicorn im venv auf http://${HOST}:${PORT} (${APP_MODULE})"
.venv/bin/uvicorn "$APP_MODULE" --host "$HOST" --port "$PORT" > /tmp/padel_server.log 2>&1 &
SERVER_PID=$!
echo "🆔 Uvicorn PID: $SERVER_PID"

# Warten, bis API erreichbar ist
echo "⏳ Warte auf API..."
for i in {1..30}; do
  if curl -sf "http://127.0.0.1:${PORT}/api/state" >/dev/null 2>&1; then
    echo "✅ API erreichbar"
    break
  fi
  if [ $i -eq 30 ]; then
    echo "❌ API konnte nicht erreicht werden"
    cat /tmp/padel_server.log
    exit 1
  fi
  sleep 1
done

# === Display-Worker separat starten =========================================
if [ -f "./display_worker.py" ] && [ -f "./start_display_worker.sh" ]; then
  echo "🖥️  Starte Display-Worker..."
  chmod +x ./start_display_worker.sh
  nohup ./start_display_worker.sh > /tmp/padel_display.log 2>&1 &
  DISPLAY_PID=$!
  echo "🆔 Display-Worker PID: $DISPLAY_PID"
  
  # Warte kurz und prüfe ob Display-Worker läuft
  sleep 2
  if ps -p $DISPLAY_PID > /dev/null; then
    echo "✅ Display-Worker läuft"
  else
    echo "⚠️  Display-Worker konnte nicht gestartet werden"
    if [ -f /tmp/padel_display.log ]; then
      echo "Letzte Zeilen vom Log:"
      tail -10 /tmp/padel_display.log
    fi
  fi
else
  echo "⚠️  Display-Worker Dateien nicht gefunden, überspringe..."
  DISPLAY_PID=""
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🎉 Padel Scoring System läuft!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📍 URL: http://$(hostname -I | awk '{print $1}'):${PORT}"
echo "📍 Lokal: http://localhost:${PORT}"
echo ""
echo "📊 Server Log: tail -f /tmp/padel_server.log"
if [ -n "$DISPLAY_PID" ]; then
  echo "📺 Display Log: tail -f /tmp/padel_display.log"
fi
echo ""
echo "🛑 Zum Stoppen: Strg+C drücken"
echo ""

# === Cleanup ================================================================
cleanup() {
  echo ""
  echo "🧹 Stoppe Dienste..."
  
  if [ -n "${SERVER_PID:-}" ]; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
    echo "✅ Server gestoppt"
  fi
  
  if [ -n "${DISPLAY_PID:-}" ]; then
    kill "$DISPLAY_PID" 2>/dev/null || true
    echo "✅ Display-Worker gestoppt"
  fi
  
  # Cleanup übrige Prozesse
  pkill -f "uvicorn.*main:app" 2>/dev/null || true
  pkill -f "display_worker.py" 2>/dev/null || true
}
trap cleanup INT TERM EXIT

# Warte auf Server
wait "$SERVER_PID"
