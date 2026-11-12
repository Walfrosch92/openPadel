#!/usr/bin/env python3
"""
Zählweise Server == App.

tests/engine_fixture.json.gz enthält Punkt-für-Punkt-Stände der Zähl-Engine der
App (OfflineGameManager) für alle Standard-Modi und mehrere eigene Modi in
allen Match-Formaten. Dieser Test spielt dieselben Punktfolgen über die API
des Servers nach und vergleicht nach jedem Punkt: Punkte, Aufschläger,
Tie-Break, Sätze und Match-Ende.

Aufruf (im Server-Ordner, braucht fastapi + httpx; Kamera-Module werden ersetzt):
    python3 tests/test_engine_parity.py
Die Vorlage erzeugt die App mit: flutter test test/engine_fixture_test.dart
"""
import gzip
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = Path(__file__).resolve().parent / "engine_fixture.json.gz"
BEST_OF = {"best_of_3": 3, "best_of_5": 5, "single_set": 1}


def trim(sets):
    """Laufender 0:0-Satz zählt nicht als Unterschied."""
    sets = [list(s) for s in sets]
    while sets and sets[-1] == [0, 0]:
        sets.pop()
    return sets


def main() -> int:
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as f:
        fixture = json.load(f)

    # In einer Kopie arbeiten: der Test legt Modi an und spielt Matches
    work = Path(tempfile.mkdtemp(prefix="openpadel_parity_"))
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
    client = TestClient(server.app)

    # Standard-Modi müssen mit der App übereinstimmen
    failures = []
    for mode in fixture["default_modes"]:
        got = client.get(f"/api/game-modes/{mode['id']}").json().get("rules")
        if got != mode["rules"]:
            failures.append(f"Standard-Modus {mode['id']}: Server {got} != App {mode['rules']}")
    for mode in fixture["custom_modes"]:
        assert client.post("/api/game-modes", json=mode).status_code == 200, mode["id"]

    points = 0
    for index, case in enumerate(fixture["cases"]):
        label = f"#{index} {case['mode']}|{case['format']} (Start {case['server']})"
        client.post("/api/reset")
        client.post("/api/settings/game-mode", json={"game_mode": case["mode"]})
        client.post("/api/settings/best-of", json={"best_of": BEST_OF[case["format"]]})
        client.post("/api/settings/serve", json={"team": case["server"].lower()})
        for n, step in enumerate(case["steps"], 1):
            state = client.post("/api/point", json={"team": step["t"].lower()}).json()["state"]
            points += 1
            game = state["current_game"]
            got = {
                "p": [game["points"]["A"], game["points"]["B"]],
                "s": game["server"],
                "tb": game["tiebreak"],
                "sw": [state["sets_won"]["A"], state["sets_won"]["B"]],
                "sets": trim([[s["score_a"], s["score_b"]] for s in state["sets"]]),
                "done": state["match_completed"],
                "w": state["match_winner"],
            }
            want = {k: step[k] for k in got}
            want["sets"] = trim(want["sets"])
            if want["done"]:
                # Nach dem Match-Ende zeigt keine Seite mehr einen Aufschläger/Punktestand an
                for key in ("p", "s", "tb"):
                    got.pop(key), want.pop(key)
            if got != want:
                diff = {k: (want[k], got[k]) for k in got if got[k] != want[k]}
                failures.append(f"{label}, Punkt {n}: (App, Server) {diff}")
                break

    shutil.rmtree(work, ignore_errors=True)
    print(f"{len(fixture['cases'])} Matches, {points} Punkte verglichen")
    for line in failures[:25]:
        print("ABWEICHUNG:", line)
    print("OK - Server zählt wie die App" if not failures else f"{len(failures)} Abweichungen")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
