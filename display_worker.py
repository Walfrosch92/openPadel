import time
import requests
import subprocess
import io
from waveshare_epd import epd2in9_V2
from PIL import Image, ImageDraw, ImageFont

API_URL = "http://localhost:8080/api/state"
WIFI_API_URL = "http://localhost:8080/api/wifi-ap/settings"
POLL_INTERVAL = 3  # Sekunden

epd = epd2in9_V2.EPD()
epd.init()
epd.Clear(0xFF)

font_large = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 36)
font_small = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 16)
font_tiny = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 12)

# Spielmodus-Mapping für Display
MODE_NAMES = {
    "mit_vorteil_tiebreak": "Vorteil+TB",
    "ohne_vorteil_tiebreak": "Ohne Vorteil",
    "mit_vorteil_ohne_tiebreak": "Klassisch",
    "kurz_set": "Kurz-Set"
}

last_displayed_state = None
last_connection_state = None
last_wifi_settings = None  # Letzte WiFi-Einstellungen für Änderungserkennung


def check_wifi_clients():
    """Prüft ob Geräte mit dem WiFi AP verbunden sind"""
    try:
        # Prüfe ob hostapd läuft
        result = subprocess.run(['systemctl', 'is-active', 'hostapd'],
                              capture_output=True, text=True, check=False)
        if result.stdout.strip() != 'active':
            return False
        
        # Prüfe verbundene Clients über iw
        result = subprocess.run(['sudo', 'iw', 'dev', 'wlan0', 'station', 'dump'],
                              capture_output=True, text=True, check=False)
        
        # Wenn "Station" im Output vorkommt, sind Clients verbunden
        if 'Station' in result.stdout:
            # Zähle die Anzahl der Clients
            client_count = result.stdout.count('Station')
            print(f"[WiFi] {client_count} Client(s) verbunden")
            return True
        
        print("[WiFi] Keine Clients verbunden")
        return False
    except Exception as e:
        print(f"[WiFi Check Fehler] {e}")
        return False


def fetch_wifi_settings():
    """Holt WiFi-Einstellungen von der API"""
    try:
        r = requests.get(WIFI_API_URL, timeout=3)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[Fehler] WiFi API nicht erreichbar: {e}")
        return None


def get_device_ip():
    """Ermittelt die IP-Adresse des wlan0-Interfaces"""
    try:
        result = subprocess.run(['ip', '-4', 'addr', 'show', 'wlan0'],
                              capture_output=True, text=True, check=False)
        for line in result.stdout.split('\n'):
            if 'inet ' in line:
                ip = line.strip().split()[1].split('/')[0]
                return ip
        return "192.168.4.1"
    except Exception as e:
        print(f"[IP-Fehler] {e}")
        return "192.168.4.1"


def generate_qr_code(ssid, password, ip_address, port, device_name="openPadel"):
    """Generiert QR-Code mit SSID, Passwort, IP, Port und Gerätename"""
    try:
        qr_data = f"{ssid}|{password}|{ip_address}|{port}|{device_name}"
        
        result = subprocess.run(['qrencode', '-o', '-', '-t', 'PNG', '-s', '3', qr_data],
                              capture_output=True, check=True)
        
        qr_image = Image.open(io.BytesIO(result.stdout))
        return qr_image
    except subprocess.CalledProcessError as e:
        print(f"[QR-Code Fehler] qrencode fehlgeschlagen: {e}")
        return None
    except Exception as e:
        print(f"[QR-Code Fehler] {e}")
        return None


def draw_wifi_qr_display(ssid, password, ip_address, port, device_name="openPadel"):
    """Zeigt WiFi QR-Code auf dem Display mit SSID und Passwort darunter"""
    image = Image.new('1', (epd.height, epd.width), 255)
    draw = ImageDraw.Draw(image)
    
    # QR-Code generieren
    qr_image = generate_qr_code(ssid, password, ip_address, port, device_name)
    
    if qr_image:
        # QR-Code in Schwarz/Weiß konvertieren
        qr_image = qr_image.convert('1')
        
        # Display-Größe: 296x128 (height x width)
        # Platz für Text unten reservieren (ca. 30 Pixel)
        text_height = 30
        available_height = epd.width - text_height - 10  # 10px Abstand
        
        # Maximale Größe für QR-Code berechnen
        max_width = epd.height - 40  # Seitenrand
        max_height = available_height - 10  # Oberrand
        
        # Skaliere QR-Code proportional auf die kleinere Dimension
        max_size = min(max_width, max_height)
        qr_image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        
        print(f"[QR-Code] Größe: {qr_image.width}x{qr_image.height}, Display: {epd.height}x{epd.width}")
        
        # Zentriere QR-Code horizontal, positioniere oben
        qr_x = (epd.height - qr_image.width) // 2
        qr_y = 5
        
        image.paste(qr_image, (qr_x, qr_y))
        
        # Text unterhalb des QR-Codes
        text_y_start = qr_y + qr_image.height + 5
        
        # SSID
        ssid_text = f"{ssid}"
        bbox_ssid = draw.textbbox((0, 0), ssid_text, font=font_tiny)
        ssid_x = (epd.height - (bbox_ssid[2] - bbox_ssid[0])) // 2
        draw.text((ssid_x, text_y_start), ssid_text, font=font_tiny, fill=0)
        
        # Passwort
        pwd_text = f"PW: {password}"
        bbox_pwd = draw.textbbox((0, 0), pwd_text, font=font_tiny)
        pwd_x = (epd.height - (bbox_pwd[2] - bbox_pwd[0])) // 2
        draw.text((pwd_x, text_y_start + 12), pwd_text, font=font_tiny, fill=0)
        
        # IP und Port
        conn_text = f"{ip_address}:{port}"
        bbox_conn = draw.textbbox((0, 0), conn_text, font=font_tiny)
        conn_x = (epd.height - (bbox_conn[2] - bbox_conn[0])) // 2
        draw.text((conn_x, text_y_start + 24), conn_text, font=font_tiny, fill=0)
        
    else:
        # Fallback wenn QR-Code nicht generiert werden kann
        fallback = f"SSID: {ssid}"
        bbox_fb = draw.textbbox((0, 0), fallback, font=font_small)
        fb_x = (epd.height - (bbox_fb[2] - bbox_fb[0])) // 2
        draw.text((fb_x, 40), fallback, font=font_small, fill=0)
        
        pwd_text = f"Password: {password}"
        bbox_pwd = draw.textbbox((0, 0), pwd_text, font=font_tiny)
        pwd_x = (epd.height - (bbox_pwd[2] - bbox_pwd[0])) // 2
        draw.text((pwd_x, 70), pwd_text, font=font_tiny, fill=0)
    
    epd.display(epd.getbuffer(image))


def draw_display(state):
    image = Image.new('1', (epd.height, epd.width), 255)
    draw = ImageDraw.Draw(image)

    team_a = state.get("team_a_name", "Team A")
    team_b = state.get("team_b_name", "Team B")
    serve = state.get("serve", "a")
    score_a = state.get("points_a_display", "0")
    score_b = state.get("points_b_display", "0")

    col_width = epd.height // 2
    padding_top = 10
    spacing = 6

    # === Team A ===
    x_a = 0
    bbox_score_a = draw.textbbox((0, 0), score_a, font=font_large)
    score_a_x = x_a + (col_width - (bbox_score_a[2] - bbox_score_a[0])) // 2
    draw.text((score_a_x, padding_top), score_a, font=font_large, fill=0)

    bbox_name_a = draw.textbbox((0, 0), team_a, font=font_small)
    name_a_y = padding_top + bbox_score_a[3] + spacing
    name_a_x = x_a + (col_width - (bbox_name_a[2] - bbox_name_a[0])) // 2
    draw.text((name_a_x, name_a_y), team_a, font=font_small, fill=0)

    if serve == "a":
        indicator = "⬤"
        bbox_i = draw.textbbox((0, 0), indicator, font=font_small)
        indicator_y = name_a_y + bbox_name_a[3] + spacing
        indicator_x = x_a + (col_width - (bbox_i[2] - bbox_i[0])) // 2
        draw.text((indicator_x, indicator_y), indicator, font=font_small, fill=0)

    # === Team B ===
    x_b = col_width
    bbox_score_b = draw.textbbox((0, 0), score_b, font=font_large)
    score_b_x = x_b + (col_width - (bbox_score_b[2] - bbox_score_b[0])) // 2
    draw.text((score_b_x, padding_top), score_b, font=font_large, fill=0)

    bbox_name_b = draw.textbbox((0, 0), team_b, font=font_small)
    name_b_y = padding_top + bbox_score_b[3] + spacing
    name_b_x = x_b + (col_width - (bbox_name_b[2] - bbox_name_b[0])) // 2
    draw.text((name_b_x, name_b_y), team_b, font=font_small, fill=0)

    if serve == "b":
        indicator = "⬤"
        bbox_i = draw.textbbox((0, 0), indicator, font=font_small)
        indicator_y = name_b_y + bbox_name_b[3] + spacing
        indicator_x = x_b + (col_width - (bbox_i[2] - bbox_i[0])) // 2
        draw.text((indicator_x, indicator_y), indicator, font=font_small, fill=0)

    # === Untere Infozeile ===
    sets_a = state.get("sets_a", 0)
    sets_b = state.get("sets_b", 0)
    games_a = state.get("games_a", 0)
    games_b = state.get("games_b", 0)
    game_mode = state.get("game_mode", "mit_vorteil_tiebreak")
    best_of = state.get("best_of", 3)
    
    # Obere Info-Zeile: Spielmodus und Best-of
    mode_display = MODE_NAMES.get(game_mode, game_mode)
    header_text = f"{mode_display} | Best of {best_of}"
    bbox_header = draw.textbbox((0, 0), header_text, font=font_tiny)
    header_x = (epd.height - (bbox_header[2] - bbox_header[0])) // 2
    header_y = 2
    draw.text((header_x, header_y), header_text, font=font_tiny, fill=0)

    # Untere Info-Zeile: Sets und Games
    footer_text = f"S: {sets_a}–{sets_b} | G: {games_a}–{games_b}"
    bbox_footer = draw.textbbox((0, 0), footer_text, font=font_small)
    footer_x = (epd.height - (bbox_footer[2] - bbox_footer[0])) // 2
    footer_y = epd.width - 20
    draw.text((footer_x, footer_y), footer_text, font=font_small, fill=0)

    epd.display(epd.getbuffer(image))


def fetch_state():
    try:
        r = requests.get(API_URL, timeout=3)
        r.raise_for_status()
        data = r.json()
        return data.get("state")
    except Exception as e:
        print(f"[Fehler] API nicht erreichbar: {e}")
        return None


def state_changed(old, new):
    if old is None:
        return True
    return (
        old.get("points_a_display") != new.get("points_a_display") or
        old.get("points_b_display") != new.get("points_b_display") or
        old.get("games_a") != new.get("games_a") or
        old.get("games_b") != new.get("games_b") or
        old.get("sets_a") != new.get("sets_a") or
        old.get("sets_b") != new.get("sets_b") or
        old.get("serve") != new.get("serve") or
        old.get("team_a_name") != new.get("team_a_name") or
        old.get("team_b_name") != new.get("team_b_name") or
        old.get("game_mode") != new.get("game_mode") or
        old.get("best_of") != new.get("best_of")
    )


if __name__ == "__main__":
    print("[Display Worker] Gestartet...")

    while True:
        # Prüfe ob WiFi-Clients verbunden sind
        clients_connected = check_wifi_clients()

        # Wenn keine Clients verbunden sind, zeige QR-Code
        if not clients_connected:
            wifi_settings = fetch_wifi_settings()

            # Prüfe ob WiFi-Einstellungen sich geändert haben
            wifi_settings_changed = (
                last_wifi_settings is None or
                last_wifi_settings.get('ssid') != wifi_settings.get('ssid') or
                last_wifi_settings.get('password') != wifi_settings.get('password')
            )

            # QR-Code anzeigen wenn: Zustandswechsel ODER Einstellungen geändert
            if last_connection_state != 'qr' or wifi_settings_changed:
                if wifi_settings_changed and last_connection_state == 'qr':
                    print("[Display] WiFi-Einstellungen geändert - aktualisiere QR-Code")
                else:
                    print("[Display] Keine WiFi-Clients - zeige QR-Code")

                if wifi_settings:
                    ssid = wifi_settings.get('ssid', 'openPadel')
                    password = wifi_settings.get('password', 'openpadel')
                    ip_address = get_device_ip()
                    port = "8080"
                    device_name = "openPadel"

                    try:
                        draw_wifi_qr_display(ssid, password, ip_address, port, device_name)
                        last_connection_state = 'qr'
                        last_wifi_settings = wifi_settings
                        print(f"[Display] QR-Code angezeigt - SSID: {ssid}, IP: {ip_address}:{port}")
                    except Exception as e:
                        print(f"[Fehler] QR-Code konnte nicht angezeigt werden: {e}")
        else:
            # Clients verbunden - zeige Scoreboard
            state = fetch_state()
            
            if state and state_changed(last_displayed_state, state):
                try:
                    draw_display(state)
                    last_displayed_state = state
                    last_connection_state = 'scoreboard'
                    print(f"[Display] Aktualisiert: {state['team_a_name']} {state['points_a_display']}-{state['points_b_display']} {state['team_b_name']}")
                except Exception as e:
                    print(f"[Fehler] Anzeige konnte nicht aktualisiert werden: {e}")
            elif last_connection_state != 'scoreboard':
                # Initialer Wechsel zu Scoreboard
                if state:
                    try:
                        draw_display(state)
                        last_displayed_state = state
                        last_connection_state = 'scoreboard'
                        print(f"[Display] Wechsel zu Scoreboard")
                    except Exception as e:
                        print(f"[Fehler] Anzeige konnte nicht aktualisiert werden: {e}")
        
        time.sleep(POLL_INTERVAL)

