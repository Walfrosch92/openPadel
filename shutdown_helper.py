#!/usr/bin/env python3
"""
Shutdown Helper - Wird beim Herunterfahren ausgeführt
1. Zeigt poweroff.jpg auf E-Paper Display
2. Beendet Display Worker
3. Beendet Server
4. Fährt System herunter
"""
import os, sys, time, pathlib, subprocess, signal
from PIL import Image

LOG = pathlib.Path('/tmp/poweroff-helper.log')

def log(msg: str):
    try:
        LOG.write_text(LOG.read_text() + msg + '\n')
    except FileNotFoundError:
        LOG.write_text(msg + '\n')
    except Exception:
        pass
    print(msg, flush=True)

def display_power_image():
    """Zeigt poweroff.jpg auf dem E-Paper Display an"""
    try:
        from waveshare_epd import epd2in9_V2
        
        project_dir = pathlib.Path(__file__).resolve().parent
        power_img = project_dir / 'poweroff.jpg'
        
        if not power_img.exists():
            log(f'[helper] poweroff.jpg nicht gefunden: {power_img}')
            return False
        
        log('[helper] Zeige poweroff.jpg auf Display...')
        
        epd = epd2in9_V2.EPD()
        epd.init()
        
        # Lade Bild (im Originalformat)
        image = Image.open(power_img)
        
        # Display-Größe
        display_width = epd.height
        display_height = epd.width
        
        # Berechne Skalierung unter Beibehaltung des Seitenverhältnisses
        img_ratio = image.width / image.height
        display_ratio = display_width / display_height
        
        if img_ratio > display_ratio:
            # Bild ist breiter - an Breite anpassen
            new_width = display_width
            new_height = int(display_width / img_ratio)
        else:
            # Bild ist höher - an Höhe anpassen
            new_height = display_height
            new_width = int(display_height * img_ratio)
        
        # ERST skalieren (in Farbe/Graustufen für bessere Qualität)
        image = image.resize((new_width, new_height), Image.LANCZOS)
        
        # Zentriere Bild auf weißem Hintergrund
        final_image = Image.new('RGB', (display_width, display_height), 'white')
        offset_x = (display_width - new_width) // 2
        offset_y = (display_height - new_height) // 2
        final_image.paste(image, (offset_x, offset_y))
        
        # DANN in Schwarz-Weiß konvertieren mit Floyd-Steinberg Dithering
        final_image = final_image.convert('1', dither=Image.FLOYDSTEINBERG)
        
        # Auf Display anzeigen
        epd.display(epd.getbuffer(final_image))
        log('[helper] poweroff.jpg angezeigt')
        
        # Sleep-Modus (Bild bleibt sichtbar)
        epd.sleep()
        
        return True
        
    except Exception as e:
        log(f'[helper] Fehler beim Anzeigen von poweroff.jpg: {e!r}')
        return False

def read_pid(p: pathlib.Path):
    try:
        return int(p.read_text().strip())
    except Exception:
        return None

def is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except Exception:
        return False

def terminate_pid(pid: int, timeout: float = 5.0):
    try:
        os.kill(pid, signal.SIGTERM)
        log(f'[helper] SIGTERM -> {pid}')
    except ProcessLookupError:
        return
    except Exception as e:
        log(f'[helper] SIGTERM error: {e!r}')
    t0 = time.time()
    while time.time() - t0 < timeout:
        if not is_alive(pid):
            return
        time.sleep(0.1)
    try:
        os.kill(pid, signal.SIGKILL)
        log(f'[helper] SIGKILL -> {pid}')
    except ProcessLookupError:
        return
    except Exception as e:
        log(f'[helper] SIGKILL error: {e!r}')

def main():
    project_dir = pathlib.Path(__file__).resolve().parent
    worker_pid_file = project_dir / 'display_worker.pid'

    log('=== shutdown_helper.py started ===')
    log(f'[helper] project_dir={project_dir}')

    # 1) Display-Worker ZUERST beenden (damit er das Display nicht mehr überschreibt)
    wp = read_pid(worker_pid_file)
    if wp and is_alive(wp):
        log(f'[helper] stop display worker (PID {wp})')
        terminate_pid(wp, timeout=5.0)
        try:
            worker_pid_file.unlink(missing_ok=True)
        except Exception:
            pass
    else:
        log('[helper] no PID file, fallback pkill -f display_worker.py')
        try:
            subprocess.run(['/usr/bin/pkill', '-f', 'display_worker.py'], check=False)
        except Exception as e:
            log(f'[helper] pkill error: {e!r}')

    # Sicherstellen, dass kein display_worker mehr läuft
    for _ in range(30):
        out = subprocess.run(['pgrep', '-f', 'display_worker.py'],
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        if not out.stdout.strip():
            break
        time.sleep(0.1)

    # Kleine Pause für SPI/GPIO Freigabe
    time.sleep(0.5)

    # 2) JETZT poweroff.jpg auf Display anzeigen
    display_power_image()
    time.sleep(1.0)

    # 3) Server beenden (wenn PID übergeben wurde)
    if len(sys.argv) >= 2:
        try:
            server_pid = int(sys.argv[1])
            log(f'[helper] stop server (PID {server_pid})')
            os.kill(server_pid, signal.SIGTERM)
        except Exception as e:
            log(f'[helper] server SIGTERM error: {e!r}')
    else:
        log('[helper] pkill -f main.py')
        try:
            subprocess.run(['/usr/bin/pkill', '-f', 'main.py'], check=False)
        except Exception as e:
            log(f'[helper] pkill main.py error: {e!r}')

    time.sleep(1.0)

    # 4) System herunterfahren
    log('[helper] System wird heruntergefahren...')
    try:
        subprocess.run(['sudo', 'shutdown', '-h', 'now'], check=False)
    except Exception as e:
        log(f'[helper] shutdown error: {e!r}')
    
    log('[helper] done')
    return 0

if __name__ == '__main__':
    sys.exit(main())
