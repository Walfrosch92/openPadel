#!/usr/bin/env python3
"""
Gestenerkennung: Regeln (Hand über Kopf, T-Pose), Haltezeit/Loslassen,
Erkennungsbereich und die Kamera-Einstellungen der API.

Aufruf (im Server-Ordner, braucht fastapi + httpx; Kamera-Module werden ersetzt):
    python3 tests/test_gestures.py
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parent.parent


def person(nose=(0.5, 0.30), ls=(0.56, 0.40), rs=(0.44, 0.40),
           lw=(0.58, 0.70), rw=(0.42, 0.70), lw_vis=1.0, rw_vis=1.0):
    """Pose-Landmarks einer Person, die zur Kamera schaut (ungespiegeltes Bild:
    ihre linke Seite ist im Bild rechts). Schulterbreite 0.12, Arme unten."""
    lm = [SimpleNamespace(x=0.0, y=0.0, visibility=0.0) for _ in range(33)]
    for index, (x, y), vis in ((0, nose, 1.0), (11, ls, 1.0), (12, rs, 1.0),
                               (15, lw, lw_vis), (16, rw, rw_vis)):
        lm[index] = SimpleNamespace(x=x, y=y, visibility=vis)
    return lm


def main() -> int:
    work = Path(tempfile.mkdtemp(prefix="openpadel_gestures_"))
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

    failures = []

    def check(name, got, expected):
        if got != expected:
            failures.append(f"{name}: erwartet {expected!r}, bekommen {got!r}")

    # --- Haltung einer Person -------------------------------------------------
    classify = server.classify_pose
    check("Arme unten", classify(person()), None)
    check("rechte Hand über Kopf", classify(person(rw=(0.42, 0.15))), "team_a")
    check("linke Hand über Kopf", classify(person(lw=(0.58, 0.15))), "team_b")
    check("beide Hände oben", classify(person(lw=(0.58, 0.15), rw=(0.42, 0.15))), None)
    check("Hand nur auf Kopfhöhe", classify(person(rw=(0.42, 0.29))), None)
    check("Hand oben, andere verdeckt",
          classify(person(rw=(0.42, 0.15), lw=(0.58, 0.10), lw_vis=0.1)), "team_a")
    check("gehobene Hand nicht sichtbar", classify(person(rw=(0.42, 0.15), rw_vis=0.1)), None)
    check("T-Pose", classify(person(lw=(0.72, 0.41), rw=(0.28, 0.39))), "undo")
    check("T-Pose, Arme zu tief", classify(person(lw=(0.72, 0.60), rw=(0.28, 0.60))), None)
    check("nur ein Arm seitlich", classify(person(lw=(0.72, 0.41))), None)
    check("Arme vor dem Körper", classify(person(lw=(0.52, 0.40), rw=(0.48, 0.40))), None)
    # Wer weit hinten steht, ist klein und tief im Bild - zählt trotzdem
    far = person(nose=(0.5, 0.700), ls=(0.512, 0.720), rs=(0.488, 0.720),
                 lw=(0.515, 0.78), rw=(0.485, 0.66))
    check("kleine Person, rechte Hand oben", classify(far), "team_a")
    # Hand oben im Bild, aber unter dem Kopf der Person (nah an der Kamera)
    near = person(nose=(0.5, 0.05), ls=(0.7, 0.30), rs=(0.3, 0.30),
                  lw=(0.72, 0.9), rw=(0.28, 0.20))
    check("Hand im oberen Bildteil, aber unter dem Kopf", classify(near), None)

    # --- Haltezeit, Loslassen, Cooldown --------------------------------------
    def run(sequence, cooldown=10):
        tracker = server.GestureTracker()
        fired = []
        for t, candidate in sequence:
            event = tracker.update(candidate, t, cooldown)
            if event:
                fired.append((round(t, 1), event))
        return fired

    def hold(gesture, start, seconds):
        return [(start + i * 0.2, gesture) for i in range(int(seconds / 0.2) + 1)]

    check("kurz (Smash) zählt nicht", run(hold("team_a", 0, 0.4) + hold(None, 0.6, 2)), [])
    check("gehalten zählt genau einmal", run(hold("team_a", 0, 30)), [(0.8, "team_a")])
    check("Undo gehalten: nur ein Undo", run(hold("undo", 0, 10)), [(0.8, "undo")])
    check("Undo, senken, Undo",
          run(hold("undo", 0, 1) + hold(None, 1.2, 1) + hold("undo", 2.4, 1)),
          [(0.8, "undo"), (3.2, "undo")])
    check("zweiter Punkt im Cooldown zählt nicht",
          run(hold("team_a", 0, 1) + hold(None, 1.2, 1) + hold("team_b", 2.4, 1)),
          [(0.8, "team_a")])
    check("zweiter Punkt nach dem Cooldown",
          run(hold("team_a", 0, 1) + hold(None, 1.2, 1) + hold("team_b", 2.4, 1), cooldown=1),
          [(0.8, "team_a"), (3.2, "team_b")])
    check("Undo direkt nach Punkt (Cooldown gilt nicht)",
          run(hold("team_a", 0, 1) + hold(None, 1.2, 1) + hold("undo", 2.4, 1)),
          [(0.8, "team_a"), (3.2, "undo")])
    check("ohne Senken zählt die nächste Geste nicht",
          run(hold("team_a", 0, 1) + hold("undo", 1.2, 3)), [(0.8, "team_a")])
    check("einzelner Aussetzer unterbricht nicht",
          run([(0, "team_a"), (0.2, "team_a"), (0.4, None), (0.6, "team_a"), (0.8, "team_a")]),
          [(0.8, "team_a")])
    check("Wechsel der Geste startet die Haltezeit neu",
          run(hold("team_a", 0, 0.6) + hold("team_b", 0.8, 0.6)), [])

    # Anzeige, warum eine Geste (noch) nicht zählt
    tracker = server.GestureTracker()
    for t, c in hold("team_a", 0, 1):
        tracker.update(c, t, 10)
    check("nach dem Zählen: Arme senken", tracker.blocked(1.0, 10)[0], "release")
    for t, c in hold(None, 1.2, 1) + hold("team_b", 2.4, 0.4):
        tracker.update(c, t, 10)
    check("zweiter Punkt in der Pause", tracker.blocked(2.8, 10)[0], "cooldown")
    check("Restzeit der Pause", round(tracker.blocked(2.8, 10)[1]), 8)
    for t, c in hold(None, 3.0, 1) + hold("undo", 4.2, 0.4):
        tracker.update(c, t, 10)
    check("Undo ist in der Pause nicht blockiert", tracker.blocked(4.6, 10)[0], None)

    # --- Erkennungsbereich ----------------------------------------------------
    # Person steht im ungespiegelten Bild bei x=0.5..: im Vorschaubild rechts
    right_side = person(ls=(0.26, 0.4), rs=(0.14, 0.4))   # Vorschau: x = 0.8
    left_half = [[0, 0], [0.5, 0], [0.5, 1], [0, 1]]
    right_half = [[0.5, 0], [1, 0], [1, 1], [0.5, 1]]
    check("ohne ROI zählt jede Person", server.person_in_roi(right_side, []), True)
    check("Person außerhalb der ROI", server.person_in_roi(right_side, left_half), False)
    check("Person in der ROI", server.person_in_roi(right_side, right_half), True)
    check("ROI in Pixeln wird umgerechnet",
          server.normalize_roi([[0, 0], [320, 0], [320, 480]], 640, 480),
          [[0.0, 0.0], [0.5, 0.0], [0.5, 1.0]])
    check("ROI mit 2 Punkten = keine ROI", server.normalize_roi([[0, 0], [1, 1]], 640, 480), [])
    check("Empfindlichkeit hoch = Schwelle niedrig",
          server.sensitivity_to_confidence(1.0) < server.sensitivity_to_confidence(0.0), True)

    # --- API ------------------------------------------------------------------
    client = TestClient(server.app)
    settings = client.get("/api/webcam/settings").json()
    check("cooldown_seconds ist int (App liest int)", type(settings["cooldown_seconds"]), int)

    roi = [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9]]
    check("ROI speichern", client.post("/api/webcam/roi", json={"points": roi}).json()["status"], "success")
    # App und Web-Oberfläche schicken die Einstellungen ohne ROI
    payload = {"enabled": settings["enabled"], "camera_index": 0, "detection_sensitivity": 0.4,
               "cooldown_seconds": 3, "width": settings["width"], "height": settings["height"],
               "fps": settings["fps"], "gesture_recognition_enabled": True}
    check("Einstellungen speichern", client.post("/api/webcam/settings", json=payload).status_code, 200)
    settings = client.get("/api/webcam/settings").json()
    check("ROI bleibt beim Speichern der Einstellungen", settings["roi_polygon"], roi)
    check("Empfindlichkeit gespeichert", settings["detection_sensitivity"], 0.4)
    check("Cooldown gespeichert", settings["cooldown_seconds"], 3)
    check("ROI überlebt Neuladen", server.WebcamSettingsManager().settings.roi_polygon, roi)
    client.post("/api/webcam/roi", json={"roi": []})
    check("ROI löschen", client.get("/api/webcam/settings").json()["roi_polygon"], [])
    check("Status in last-gesture", "status" in client.get("/api/webcam/last-gesture").json(), True)

    shutil.rmtree(work, ignore_errors=True)
    if failures:
        print(f"FEHLER ({len(failures)}):")
        for failure in failures:
            print("  -", failure)
        return 1
    print("OK - Gestenerkennung")
    return 0


if __name__ == "__main__":
    sys.exit(main())
