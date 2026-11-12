#!/usr/bin/env python3
"""
Sync der eigenen Spielmodi zwischen App und Server (POST /api/game-modes/sync).

Aufruf im Server-Ordner:  python3 tests/test_game_mode_sync.py
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parent.parent
RULES = {"sets_to_win": 2, "games_to_win_set": 4, "games_minimum_difference": 2, "advantage": True,
         "tiebreak": True, "tiebreak_at_games": [4, 4], "tiebreak_points_to_win": 7,
         "tiebreak_minimum_difference": 2, "golden_point": False}


def mode(mode_id, name, updated_at=None, **extra):
    data = {"id": mode_id, "name": name, "description": "", "is_custom": True, "rules": dict(RULES), **extra}
    if updated_at is not None:
        data["updated_at"] = updated_at
    return data


def main() -> int:
    work = Path(tempfile.mkdtemp(prefix="openpadel_sync_"))
    for name in ("main.py", "updater.py", "game_modes", "templates", "static", "translations"):
        src = ROOT / name
        (shutil.copytree if src.is_dir() else shutil.copy)(src, work / name)
    os.chdir(work)
    sys.path.insert(0, str(work))
    for module in ("cv2", "mediapipe"):
        sys.modules[module] = MagicMock()
    os.environ["OPENPADEL_AUTOUPDATE"] = "0"
    import logging
    logging.disable(logging.CRITICAL)
    import main as server
    from fastapi.testclient import TestClient
    c = TestClient(server.app)

    failed = []

    def check(label, condition):
        print(("ok   " if condition else "FAIL ") + label)
        if not condition:
            failed.append(label)

    def sync(modes=(), deleted=None):
        r = c.post("/api/game-modes/sync", json={"modes": list(modes), "deleted": deleted or {}})
        assert r.status_code == 200, r.text
        data = r.json()
        data["custom"] = {m["id"]: m for m in data["modes"] if m["is_custom"]}
        return data

    # 1) Neuer Modus aus der App landet auf dem Server (inkl. Icon)
    r = sync([mode("custom_a", "A", 1000, icon_key="🎾")])
    check("App-Modus wird angelegt", r["custom"].get("custom_a", {}).get("name") == "A")
    check("Icon bleibt erhalten", r["custom"]["custom_a"].get("icon_key") == "🎾")
    check("Standard-Modi sind nicht 'custom'", sum(not m["is_custom"] for m in r["modes"]) == 4)

    # 2) Ältere Fassung der App überschreibt nichts, jüngere schon
    r = sync([mode("custom_a", "A alt", 500)])
    check("ältere App-Fassung verliert", r["custom"]["custom_a"]["name"] == "A")
    r = sync([mode("custom_a", "A neu", 2000)])
    check("jüngere App-Fassung gewinnt", r["custom"]["custom_a"]["name"] == "A neu")

    # 3) Im Web bearbeitet (jünger) -> App bekommt die Server-Fassung zurück
    c.post("/api/game-modes", json=mode("custom_a", "A web", 3000))
    r = sync([mode("custom_a", "A neu", 2000)])
    check("Web-Bearbeitung kommt in der App an", r["custom"]["custom_a"]["name"] == "A web")

    # 4) Im Web gelöscht -> App, die ihn noch kennt, legt ihn NICHT wieder an
    c.delete("/api/game-modes/custom_a?deleted_at=4000")
    r = sync([mode("custom_a", "A web", 3000)])
    check("im Web gelöschter Modus bleibt gelöscht", "custom_a" not in r["custom"])
    check("Löschmarke wird gemeldet", r["deleted"].get("custom_a") == 4000)
    r = sync([mode("custom_a", "A wieder", 5000)])
    check("danach neu angelegter Modus kommt wieder", r["custom"].get("custom_a", {}).get("name") == "A wieder")
    check("Löschmarke ist weg", "custom_a" not in r["deleted"])

    # 5) In der App (offline) gelöscht -> beim nächsten Verbinden auch am Server weg
    r = sync([], {"custom_a": 6000})
    check("in der App gelöschter Modus wird am Server gelöscht", "custom_a" not in r["custom"])
    check("Datei ist entfernt", not (work / "game_modes" / "custom_a.json").exists())
    r = sync([mode("custom_a", "A wieder", 5000)])
    check("zweites Handy legt ihn nicht wieder an", "custom_a" not in r["custom"])

    # 6) Löschung älter als die letzte Bearbeitung -> Bearbeitung gewinnt
    sync([mode("custom_b", "B", 9000)])
    r = sync([], {"custom_b": 8000})
    check("ältere Löschung verliert gegen Bearbeitung", "custom_b" in r["custom"])

    # 7) Modus des laufenden Matches wird erst nach dem Match gelöscht
    c.post("/api/reset")
    c.post("/api/settings/game-mode", json={"game_mode": "custom_b"})
    c.post("/api/point", json={"team": "a"})
    r = sync([], {"custom_b": 9500})
    check("Löschung wartet während des Matches", "custom_b" in r["custom"] and r["kept"] == ["custom_b"])
    c.post("/api/reset")
    r = sync([], {"custom_b": 9500})
    check("nach dem Match wird gelöscht", "custom_b" not in r["custom"] and r["kept"] == [])
    check("Match fällt auf Standardmodus zurück",
          c.get("/api/state").json()["state"]["game_mode"] == "mit_vorteil_tiebreak")

    # 8) Standard-Modi sind über den Sync nicht angreifbar
    r = sync([mode("kurz_set", "Hack", 99999)], {"mit_vorteil_tiebreak": 99999})
    names = {m["id"]: m["name"] for m in r["modes"]}
    check("Standard-Modi bleiben unverändert", names.get("kurz_set") == "Kurz-Set" and "mit_vorteil_tiebreak" in names)

    # 9) Alte App (ohne Zeitstempel) kann weiterhin anlegen und löschen
    check("POST ohne updated_at", c.post("/api/game-modes", json=mode("custom_c", "C")).status_code == 200)
    check("Server stempelt selbst", c.get("/api/game-modes/custom_c").json().get("updated_at", 0) > 0)
    check("DELETE ohne deleted_at", c.delete("/api/game-modes/custom_c").status_code == 200)

    shutil.rmtree(work, ignore_errors=True)
    print("OK" if not failed else f"{len(failed)} Fehler")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
