#!/usr/bin/env bash
set -euo pipefail

echo "🛑 Stoppe Padel Scoring System..."

# Stoppe Uvicorn Server
if pkill -f "uvicorn.*main:app"; then
  echo "✅ Server gestoppt"
else
  echo "ℹ️  Kein Server-Prozess gefunden"
fi

# Stoppe Display Worker
if pkill -f "display_worker.py"; then
  echo "✅ Display-Worker gestoppt"
else
  echo "ℹ️  Kein Display-Worker-Prozess gefunden"
fi

sleep 1

# Prüfe ob noch Prozesse laufen
if pgrep -f "uvicorn.*main:app" > /dev/null || pgrep -f "display_worker.py" > /dev/null; then
  echo "⚠️  Einige Prozesse laufen noch, erzwinge Stopp..."
  pkill -9 -f "uvicorn.*main:app" 2>/dev/null || true
  pkill -9 -f "display_worker.py" 2>/dev/null || true
  sleep 1
fi

echo "✅ Alle Dienste gestoppt"
