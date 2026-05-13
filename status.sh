#!/usr/bin/env bash
set -euo pipefail

echo "📊 Padel Scoring System Status"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Prüfe Server
if pgrep -f "uvicorn.*main:app" > /dev/null; then
  SERVER_PID=$(pgrep -f "uvicorn.*main:app")
  echo "✅ Server läuft (PID: $SERVER_PID)"
  
  # Prüfe Port
  if lsof -i :8080 > /dev/null 2>&1; then
    echo "   Port 8080: ✅ gebunden"
  else
    echo "   Port 8080: ❌ nicht gebunden"
  fi
  
  # Prüfe API
  if curl -sf http://localhost:8080/api/state > /dev/null 2>&1; then
    echo "   API: ✅ erreichbar"
  else
    echo "   API: ❌ nicht erreichbar"
  fi
else
  echo "❌ Server läuft nicht"
fi

echo ""

# Prüfe Display Worker
if pgrep -f "display_worker.py" > /dev/null; then
  DISPLAY_PID=$(pgrep -f "display_worker.py")
  echo "✅ Display-Worker läuft (PID: $DISPLAY_PID)"
else
  echo "❌ Display-Worker läuft nicht"
fi

echo ""

# Prüfe Logs
if [ -f /tmp/padel_server.log ]; then
  echo "📝 Server Log (letzte 5 Zeilen):"
  tail -5 /tmp/padel_server.log | sed 's/^/   /'
fi

echo ""

if [ -f /tmp/padel_display.log ]; then
  echo "📺 Display Log (letzte 5 Zeilen):"
  tail -5 /tmp/padel_display.log | sed 's/^/   /'
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "💡 Befehle:"
echo "   Server starten:  ./start_server.sh"
echo "   Server stoppen:  ./stop_server.sh"
echo "   Server Log:      tail -f /tmp/padel_server.log"
echo "   Display Log:     tail -f /tmp/padel_display.log"
echo ""
