#!/usr/bin/env python3
import os, sys, time, subprocess
from PIL import Image

# --- Root sicherstellen ------------------------------------------------------
if os.geteuid() != 0:
    os.execvp("sudo", ["sudo", "-E", sys.executable] + sys.argv)

# --- Einstellungen -----------------------------------------------------------
IMAGE_PATH = "poweroff.jpg"   # Pfad zu Ihrem Bild
DISPLAY_SECONDS = 4                              # E-Ink-Refresh dauert etwas
PANEL_W, PANEL_H = 296, 128                      # Waveshare 2.9″ V2 Auflösung
# Fallback (nur wenn Sie HDMI/Framebuffer nutzen möchten):
OPENVT = "/usr/bin/openvt"
FBI    = "/usr/bin/fbi"

# --- Waveshare 2.9″ V2 -------------------------------------------------------
def init_epd_compat(epd, drv):
    """
    Initialisiert das Panel fehlertolerant – je nach Treiberversion:
    - epd.init()
    - epd.init(drv.FULL_UPDATE) / epd.init(epd.FULL_UPDATE)
    - epd.init(0) / epd.init(1)
    """
    trials = []
    trials.append(lambda: epd.init())
    for name in ("FULL_UPDATE", "lut_full_update", "FULL"):
        if hasattr(drv, name):
            val = getattr(drv, name)
            trials.append(lambda v=val: epd.init(v))
    for name in ("FULL_UPDATE", "lut_full_update", "FULL"):
        if hasattr(epd, name):
            val = getattr(epd, name)
            trials.append(lambda v=val: epd.init(v))
    trials.append(lambda: epd.init(0))
    trials.append(lambda: epd.init(1))

    last = None
    for t in trials:
        try:
            t()
            return True
        except Exception as e:
            last = e
    if last:
        print(f"[WARN] EPD init fehlgeschlagen: {last}", file=sys.stderr)
    return False

def show_on_epd_29_v2(path: str) -> bool:
    if not os.path.exists(path):
        print(f"[WARN] Bild nicht gefunden: {path}", file=sys.stderr)
        return False
    try:
        from waveshare_epd import epd2in9_V2 as epd_driver  # **2.9″ V2**
    except Exception as e:
        print(f"[WARN] Treiber epd2in9_V2 nicht importierbar: {e}", file=sys.stderr)
        return False

    try:
        epd = epd_driver.EPD()
        if not init_epd_compat(epd, epd_driver):
            return False

        img = Image.open(path)

        # In reines Schwarz/Weiß konvertieren (1-Bit, ohne Dithering):
        img = img.convert("L").point(lambda x: 0 if x < 128 else 255, mode="1")

        # Orientierung: Viele Treiber erwarten portraitierte Maße (height/width vertauscht).
        # Für 296x128 wählen wir eine passende Rotation, falls nötig.
        target_w, target_h = PANEL_W, PANEL_H
        if (img.width > img.height and target_w < target_h) or \
           (img.width < img.height and target_w > target_h):
            img = img.rotate(90, expand=True)

        # Größe exakt ans Panel anpassen:
        img = img.resize((target_w, target_h))

        # Einige Treiber nutzen width/height gedreht; bei V2 passt meist getbuffer direkt.
        epd.display(epd.getbuffer(img))
        try:
            epd.sleep()
        except Exception:
            pass
        return True
    except Exception as e:
        print(f"[WARN] Waveshare-Rendering fehlgeschlagen: {e}", file=sys.stderr)
        return False

# --- HDMI/Framebuffer-Fallback (optional) ------------------------------------
def show_with_fbi_tty1(path: str) -> bool:
    if not (os.path.exists(FBI) and os.path.exists(OPENVT) and os.path.exists(path)):
        return False
    # TTY1 erzwingen (falls getty läuft): -f
    cmd = [OPENVT, "-f", "-c", "1", "--", FBI, "-T", "1", "-a", "-noverbose", path]
    try:
        subprocess.run(cmd, check=False)
        return True
    except Exception as e:
        print(f"[WARN] fbi/openvt fehlgeschlagen: {e}", file=sys.stderr)
        return False

def poweroff():
    for cmd in (["/usr/bin/systemctl", "poweroff"],
                ["/usr/sbin/shutdown", "-h", "now"]):
        try:
            subprocess.run(cmd, check=True)
            return
        except Exception as e:
            last = e
    print(f"[ERROR] Poweroff fehlgeschlagen: {last}", file=sys.stderr)

def main():
    # 1) Bild auf e-Ink 2.9″ V2 ausgeben
    ok = show_on_epd_29_v2(IMAGE_PATH)
    if not ok:
        # 2) Optionaler Fallback (nur falls Sie HDMI/Framebuffer haben)
        show_with_fbi_tty1(IMAGE_PATH)
    # 3) Sichtbar lassen und dann ausschalten
    time.sleep(DISPLAY_SECONDS)
    poweroff()

if __name__ == "__main__":
    main()
