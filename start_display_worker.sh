#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

echo "🔧 Starte display_worker.py (Host)…"
/usr/bin/env python3 display_worker.py
