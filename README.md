<p align="center">
  <img src="banner.PNG" alt="openPadel – Play. Score. Win." width="100%">
</p>

# 🎾 Open Padel - Tennis & Padel Scoring System

A comprehensive, web-based scoring system for tennis, padel and similar sports with gesture recognition, live camera streaming and multi-language support. Optimized for Raspberry Pi with E-Paper display and UPS support.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.11+-blue.svg)
![Platform](https://img.shields.io/badge/platform-Raspberry%20Pi-red.svg)
[![iOS App Store](https://img.shields.io/badge/iOS-App%20Store-000000.svg?logo=apple)](https://apps.apple.com/at/app/openpadel/id6756242520)
[![Get it on Google Play](https://img.shields.io/badge/Get%20it%20on-Google%20Play-3DDC84.svg?logo=google-play)](https://play.google.com/store/apps/details?id=com.Walfrosch92.openPadel)

[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-Support-orange?logo=buy-me-a-coffee)](https://buymeacoffee.com/walfrosch92)

> Support the project with a voluntary contribution – every coffee counts! ☕

## 📋 Table of Contents

- [About the Project](#-about-the-project)
- [Hardware Components](#-hardware-components)
- [Display Wiring](#-display-wiring)
- [Features](#-features)
- [Installation](#-installation)
- [Update](#-update)
- [First Start](#-first-start)
- [Project Structure](#-project-structure)
- [Usage](#-usage)
- [Configuration](#-configuration)
- [API Endpoints](#-api-endpoints)
- [Troubleshooting](#-troubleshooting)
- [Performance Optimization](#-performance-optimization)
- [Adding New Languages](#-adding-new-languages)
- [Contributing](#-contributing)
- [Roadmap](#-roadmap)
- [Support](#-support)

## 🎯 About the Project

Open Padel turns a Raspberry Pi with an attached camera into an interactive scoring system. Using hand gestures (hands above head or T-position) you can record points – ideal for training, matches with friends, tournaments or clubs. The system runs completely autonomously, starts automatically after setup and displays the score on a power-saving E-Paper display.

## 🖥️ Hardware Components

| Component | Product | Link |
|-----------|---------|------|
| **Main Board** | Raspberry Pi 5 (or Pi 4/Zero 2 W) | – |
| **Camera** | 8 MP IMX219 Sensor with 200° Fisheye | [AliExpress](https://a.aliexpress.com/_Eyk2yMS) |
| **Camera Cable** | Flex cable (15 cm FFC, CSI interface) | often included with camera |
| **UPS HAT** | 18650 Li-Battery HAT (uninterruptible power supply, I2C) | [AliExpress](https://a.aliexpress.com/_Ey5HKRu) |
| **Batteries** | 18650 Li-Ion cells (4 recommended) | – |
| **Display** | 2.9″ E-Paper Module (296×128, two-color, SPI) | [Amazon](https://amzn.eu/d/0baDggak) |

> 💡 **Component Notes:**
> - The **200° fisheye camera** captures you on the playing field – ideal for gesture recognition.
> - The **UPS HAT** enables location-independent use, allowing the openPadel device to be mounted directly on the outside of the glass.
> - The **E-Paper display** is extremely power-efficient and shows the score even without backlight (power is only consumed when refreshing).

## 🔌 Display Wiring

Connect the **Waveshare 2.9″ E-Paper module** to the Raspberry Pi GPIO header as follows:

| Display Pin | Raspberry Pi Pin | GPIO |
|-------------|-----------------|------|
| **VCC** | 3.3V (Pin 1 or 17) | – |
| **GND** | GND (Pin 6, 9, 14, 20 …) | – |
| **DIN** | Pin 19 | GPIO 10 (SPI0_MOSI) |
| **CLK** | Pin 23 | GPIO 11 (SPI0_SCLK) |
| **CS** | Pin 24 | GPIO 8 (SPI0_CE0) |
| **DC** | Pin 22 | GPIO 25 |
| **RST** | Pin 11 | GPIO 17 |
| **BUSY** | Pin 18 | GPIO 24 |

> ⚠️ **Important:** The display runs on **3.3 V** only – never connect it to the 5 V rail!  
> The SPI interface must be enabled before first use. The installation script handles this automatically and prompts you to reboot.


## ✨ Features

### 📊 Scoreboard
- **Real-time scoring** for tennis, padel or similar sports
- **Multiple game modes**: With/without advantage, tiebreak, golden point
- **Custom game modes**: create, edit and delete your own modes in the web interface ("New match") or in the app – the four built-in modes are protected
- **Best-of series**: Best-of-3 or Best-of-5 selectable
- **Undo function** for scoring errors
- **Match history**: Point-by-point tracking
- **Statistics dashboard**: overview, game durations, hold/break-point rates, team ranking with form, head-to-head
- **Match details**: momentum chart, key figures and every point of every game

### 📸 Camera & Gesture Recognition
- **Live camera streaming** via web interface & iOS app
- **Hand gesture recognition** with MediaPipe:
  - ✋ Right hand above head → Point for Team A
  - ✋ Left hand above head → Point for Team B
  - 🙌 Both arms outstretched at shoulder height (T-position) → Undo last point
- **ROI editor** (Region of Interest) for custom detection zones
- **Adjustable resolution** (640x480 to 1920x1080) & FPS (10-30)
- **Gesture recognition can be toggled** – saves CPU resources

### 🌍 Multi-language Support
- **3 pre-installed languages**: English, German, Spanish
- **Easily expandable** via JSON files
- **Language preference saved** across reboots
- **Server-side & client-side i18n**

### 🔧 System Administration
- **WiFi Access Point** configuration (SSID: `openPadel_<serial_number>`)
- **System control**: Restart services, shutdown Pi
- **Automatic software updates** from GitHub over LAN – also triggerable from the admin panel and the app
- **Status monitoring**: Camera, system, services
- **Web-based admin panel**

### 📱 User Interface
- **Responsive design** – works on PC, tablet & smartphone
- **Touch-optimized** – ideal for mobile devices
- **Same look as the app**: dark glass design, blue/purple team colours, light & dark mode follow the system
- **Works offline**: no external fonts or icon CDNs – everything is served by the Pi
- **Confetti effect** when match ends

## 🛠️ Installation

### Prerequisites

| Component | Requirement |
|-----------|-------------|
| Hardware | Raspberry Pi 4 or 5 (5 recommended) |
| Camera | IMX219 with 200° fisheye (see hardware table) |
| OS | **Raspberry Pi OS Bookworm** (Debian 12, Lite recommended) |
| Python | 3.11 or newer (included in Bookworm) |
| Network | **LAN cable required** during installation |

> ⚠️ **OS Note:** openPadel is developed and tested on **Raspberry Pi OS Bookworm** (the current stable release). Older versions (Bullseye, Buster) are not officially supported.

> 🌐 **Network Note:** Installation and updates must be performed **over a wired LAN connection**. During setup the Pi configures its own WiFi access point, which means the WiFi interface is no longer available for internet access. Always connect the Pi via Ethernet cable before running the installer or updater.

### ⚡ Installation Steps

**Step 1 – Flash & boot Raspberry Pi OS Bookworm**

Use [Raspberry Pi Imager](https://www.raspberrypi.com/software/) to flash **Raspberry Pi OS Lite (Bookworm, 64-bit)** onto an SD card. Boot the Pi and connect it via **LAN cable**.

**Step 2 – SSH Connection**

Open a terminal on your main PC and connect via SSH to your Raspberry Pi.

```bash
ssh user@raspberry-pi-ip
```

**Step 3 – Install Git**

```bash
sudo apt-get install git
```

**Step 4 – Clone the repository**

```bash
git clone https://github.com/Walfrosch92/openPadel.git
cd openPadel
```

**Step 5 – Run the Presetup script**

```bash
sudo ./presetup.sh
```

A reboot is required because the SPI interface is activated for the first time. Reconnect afterwards via SSH again.

**Step 6 – Run the installer**

```bash
cd openPadel
sudo ./install_complete.sh
```

> 💡 **Server-only mode** (custom display, custom camera):
>
> ```bash
> sudo ./install_serveronly.sh
> ```

### 🔧 What the Setup Automatically Does

| Step | Action |
|:----:|--------|
| 1 | Enable SPI interface & camera overlay in `/boot/firmware/config.txt` (handled by `presetup.sh`) |
| 2 | Install system packages (spidev, lgpio, rpicam-apps, fonts, …) |
| 3 | Compile Waveshare E-Paper library |
| 4 | Create Python venv & install all pip dependencies |
| 5 | Set up `padel-server` & `padel-display` as systemd services (autostart) |
| 6 | Configure WiFi Access Point (SSID: `openPadel_<serial_number>`) |
| 7 | Ask for country code and subnet, then configure hostapd & dnsmasq |

> 💡 **Note:** At the end of setup you will be asked: **"Reboot now? (1/2)"**  
> After the reboot, all services start automatically.

---

## 🔄 Update

### Automatic update

The server updates itself. While the Pi is connected via **Ethernet cable**, it checks GitHub (`main` branch) 90 seconds after boot and then every 30 minutes. When a newer commit exists it:

1. downloads it (`git fetch`) – DNS problems caused by the access point setup are worked around automatically,
2. keeps your data (`data/`, `game_modes/`) and replaces the code,
3. restarts the server; new Python packages from `requirements.txt` are installed during the restart.

Safety nets:

- No automatic restart while a match is running (last point less than 20 minutes ago) – the update is installed afterwards.
- If the new code has a syntax error or fails to start twice, the previous version is restored and that commit is skipped.
- Changes to `install_complete.sh` (system packages, services) are **not** applied automatically – the admin panel shows a hint, then run the manual update below once.

Status, a "check now" button and the on/off switch are in the **admin panel → Software Update** (`/admin`). API: `GET /api/update/status`, `POST /api/update/check` (`{"apply": true}` installs immediately), `POST /api/update/settings` (`{"enabled": false, "interval_minutes": 60}`). On the command line: `python3 updater.py --check` / `--apply`.

> The auto-updater only installs when the server runs as systemd service (i.e. on the Pi). Installations older than the auto-updater need **one** manual update to get it.

### Update from the app

The openPadel app can trigger the update too: connect to the scoreboard, open **Settings** on the scoreboard screen and scroll to **Server update**. There you see the installed version and the last check, can search for updates, install one and switch automatic updates on or off.

- The phone only *triggers* the update. The Pi downloads it itself, so the **Ethernet cable must be plugged in** – otherwise the app shows "Server has no internet (LAN cable?)".
- "Install" works immediately, even while a match is running (the app asks first). The score is kept; the server is unreachable for about a minute while it restarts.
- Servers without the auto-updater show a hint to update manually once.
- After the update the installed version (short commit id) changes in the app and in the admin panel.

### Manual update

> 🌐 **LAN required:** Connect the Raspberry Pi via **Ethernet cable** and SSH into it before updating. The WiFi interface is used as an access point and has no internet access.

### Step 1 – Restore DNS resolution

After the WiFi access point has been set up, the Pi may lose DNS resolution over LAN. Run these two commands first to fix it:

```bash
sudo sh -c "echo 'nameserver 8.8.8.8' > /etc/resolv.conf"
sudo sh -c "echo 'nameserver 8.8.4.4' >> /etc/resolv.conf"
```

### Step 2 – Pull the latest code

```bash
cd ~/openPadel
git pull
```

### Step 3 – Re-run the installer

The installer is idempotent – it skips steps that are already done and only applies what has changed:

```bash
sudo ./install_complete.sh
```

> After the update, a reboot is usually required.

### Quick update (dependencies only)

If you only want to refresh Python packages without running the full installer:

```bash
cd ~/openPadel
source .venv/bin/activate
pip install --quiet -r requirements.txt
sudo systemctl restart padel-server padel-display
```

---

## 🚀 First Start

After reboot **everything runs automatically**:
- The web server starts on its own
- The display worker is active
- The WiFi AP is ready

### Connect to the System

1. **Connect your device** (laptop, smartphone, tablet) to the Pi's WiFi:
   - **SSID:** `openPadel_<serial_number>`
   - **Password:** `openPadel`

2. **Open your browser** and navigate to:
   ```
   http://openpadel.local:8080
   ```
   or directly via IP address (shown on the display):
   ```
   http://<raspberry-pi-ip>:8080
   ```

> ✨ **Tip:** This works with any smartphone, any brand – completely without an additional app!

### Alternative Access

| Access | Method |
|--------|---------|
| On-site at Pi | `http://localhost:8080` (with connected monitor) |

### iOS & Android App "openPadel"

[![Download on the App Store](https://img.shields.io/badge/Download_on_the-App%20Store-000000?style=for-the-badge&logo=apple)](https://apps.apple.com/at/app/openpadel/id6756242520)
[![Get it on Google Play](https://img.shields.io/badge/Get_it_on-Google%20Play-3DDC84?style=for-the-badge&logo=google-play)](https://play.google.com/store/apps/details?id=com.Walfrosch92.openPadel)

| Platform | Setup Method |
|----------|--------------|
| iOS & Android | Open the "Setup" tab in the app and scan the QR code displayed on the e-Ink display |

## 📁 Project Structure

```
openPadel/
├── main.py                 # Main application (FastAPI)
├── updater.py             # Auto-updater (GitHub → Pi, rollback on failure)
├── display_worker.py      # E-Paper display worker
├── webcam.py              # Camera control (rpicam-vid)
├── shutdown_helper.py     # System shutdown
├── install_complete.sh    # Full installation (display + server + WiFi AP)
├── install_serveronly.sh  # Server-only installation (custom hardware)
├── requirements.txt       # Python dependencies
├── game_modes/            # Game mode definitions (JSON)
├── data/                  # Configurations & state
│   ├── match_state.json
│   ├── webcam_settings.json
│   ├── wifi_ap_settings.json
│   └── language_settings.json
├── static/                # Static files
│   ├── app.css           # Design system (same tokens as the app)
│   ├── logo.png          # Logo with transparent background
│   ├── js/i18n.js        # Internationalization (client)
│   └── js/stats.js       # Statistics page
├── templates/             # HTML templates
│   ├── _head.html        # Shared <head> (styles, translations)
│   ├── _nav.html         # Shared navigation & icons
│   ├── index.html        # Scoreboard
│   ├── webcam.html       # Camera & gestures
│   ├── stats.html        # Statistics
│   ├── admin.html        # Admin panel
│   └── settings.html     # New match (format, mode, team names, serve)
└── translations/          # Language files
    ├── en.json           # English
    ├── de.json           # German
    └── es.json           # Spanish
```

## 🎮 Usage

### Starting a Match & Usage

1. Go to the **New Game** page
2. Select match format
3. Select the game mode
4. Click on a team name to edit player names & save
5. Select the serve
6. Click on Scoreboard
7. Use **+Point** to award points or use gesture control
8. Use **Undo** to correct mistakes
9. The match progresses automatically: points → games → sets

### Gesture Recognition

Open the **Gestures** page and make sure the camera is active and gesture recognition is turned on. Show the corresponding hand gesture in front of the camera:

| Gesture | Action |
|---------|--------|
| ✋ Right hand above head | Point for Team A |
| ✋ Left hand above head | Point for Team B |
| 🙌 Both arms at shoulder height (T-position) outstretched | Undo last point |

> ⏱️ The cooldown time between gestures is 10 seconds by default (adjustable in the UI).

### Setting up ROI (Recognition Area)

1. Camera page → click **"Edit ROI"**
2. Click points in the preview to set the polygon
3. **Double-click** to close the polygon
4. Click **"Save ROI"** – recognition now only works within this area

### Changing Language

1. Open **Settings** page
2. Under **System Control**, select the desired language
3. Click **"Save Language"**
4. The page will automatically reload

## ⚙️ Configuration

All settings can be made either through the user interface or directly in the JSON files.

### Camera Settings (`data/webcam_settings.json`)
```json
{
  "enabled": true,
  "camera_index": 0,
  "detection_sensitivity": 0.7,
  "cooldown_seconds": 10.0,
  "width": 640,
  "height": 480,
  "fps": 10,
  "gesture_recognition_enabled": true
}
```

### Language Settings (`data/language_settings.json`)
```json
{
  "language": "en"
}
```

### WiFi AP Settings (`data/wifi_ap_settings.json`)
```json
{
  "enabled": false,
  "ssid": "openPadel_<serial_number>",
  "password": "openPadel"
}
```

## 🌐 API Endpoints

### Match Control

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Scoreboard page |
| GET | `/api/match-status` | Get current match status |
| POST | `/api/point/{player}` | Add point for player 1 or 2 |
| POST | `/api/undo` | Undo last point |
| POST | `/api/new-match` | Start new match |

### Webcam

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/webcam` | Camera page |
| GET | `/webcam/stream` | MJPEG video stream |
| GET | `/api/webcam/settings` | Get settings |
| POST | `/api/webcam/settings` | Update settings |
| POST | `/api/webcam/roi` | Save ROI polygon |
| GET | `/api/webcam/last-gesture` | Get last gesture |

### System

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/admin` | Admin panel |
| GET | `/api/language` | Current language |
| POST | `/api/language` | Set language |
| GET | `/api/translations` | Get all translations |
| POST | `/api/system/shutdown` | Shutdown system |
| POST | `/api/system/restart` | Restart the server service |
| GET | `/api/update/status` | Auto-update status & installed version |
| POST | `/api/update/check` | Check for updates (`{"apply": true}` installs now) |
| POST | `/api/update/settings` | Enable/disable auto-update, set interval |

### Statistics

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/stats` | Statistics page |
| GET | `/api/stats` | Get match statistics |
| GET | `/api/state` | Current match state (web fields + app format: `sets`, `current_game`, `mode`, `match_completed`) |
| GET | `/api/history` | Match history, oldest first. `history` = app format incl. `point_history`, `matches` = web format |
| DELETE | `/api/history/{id}` | Delete one match (idempotent, unknown ids return 200) |
| POST | `/api/history/delete` | Delete one match via JSON body `{"id": "..."}` |
| DELETE | `/api/history` | Delete all matches (idempotent) |
| GET | `/api/game-stats` | Game durations over all saved matches + the running match |

Each saved match has a stable `id`. `point_history` lists every set in order:
`{"sets":[{"games":[{"w":"A","s":"B","tb":false,"p":["A","B","A","A","A"],"u":0,"d":95}],"unknown_games":0}]}`
(`w` game winner, `s` serving team, `tb` tie-break, `p` point winners, `d` seconds from the game's first to its last point).

## 🔧 Troubleshooting

### Camera not working

```bash
# Check if camera is detected
libcamera-hello --list-cameras

# Take a test image
rpicam-still -o test.jpg

# Check permissions
sudo usermod -a -G video $USER
```

### "Cannot read frame" error

- Camera properly connected?
- Check `webcam_settings.json` for correct values
- Try lower resolution/FPS
- Disable gesture recognition (test stream only)

### High CPU usage

- Reduce FPS (10 instead of 30)
- Lower resolution (640x480 instead of 1280x720)
- Disable gesture recognition when not needed
- Keep only one camera stream active

### Gesture recognition not working

- Is `gesture_recognition_enabled: true` set?
- Check lighting conditions
- Hand must be clearly visible
- Adjust `detection_sensitivity`
- ROI area correctly set?

### No internet / DNS on LAN during update

The WiFi AP setup replaces the default network configuration. If `git pull` or `apt` fails with DNS errors, run:

```bash
sudo sh -c "echo 'nameserver 8.8.8.8' > /etc/resolv.conf"
sudo sh -c "echo 'nameserver 8.8.4.4' >> /etc/resolv.conf"
```

Then retry the update command.

### Display shows nothing / SPI errors

- Check wiring against the [Display Wiring](#-display-wiring) table
- Make sure SPI is enabled: `ls /dev/spidev*` should show `/dev/spidev0.0`
- If not present, reboot – SPI is activated on first boot after installation
- Verify display is connected to **3.3 V**, not 5 V

## 🚀 Performance Optimization

### For Raspberry Pi 4/5

| Setting | Recommendation |
|---------|---------------|
| Resolution | 640x480 |
| FPS | 10-15 |
| Overclocking | Optional |
| OS | Raspberry Pi OS Lite Bookworm (without desktop) |

### Reducing CPU Load

1. Disable gesture recognition when not needed
2. Lower resolution and FPS
3. Close unnecessary browser tabs
4. Limit concurrent connections

## 📝 Adding New Languages

> **Note:** `language` is a placeholder – for French use `fr`, etc.

1. **Create new translation file:**
   ```bash
   cp translations/en.json translations/language.json
   ```

2. **Translate all strings in `language.json`**

3. **Update `LanguageManager` in `main.py`:**
   ```python
   AVAILABLE_LANGUAGES = {
       "en": "English",
       "de": "Deutsch",
       "es": "Español",
       "language": "Language Name"  # e.g. "fr": "Français"
   }
   ```

4. **Extend language dropdown in `admin.html`**

## 🤝 Contributing

Contributions are very welcome!

1. Fork the project
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 🗺️ Roadmap

- [ ] Tournament mode with bracket generation
- [x] iOS app
- [x] Android app
- [ ] WiFi scoreboard via ESP32
- [ ] AI-powered point detection

## 📞 Support

For problems, questions or suggestions:
- Open a **GitHub Issue**
- Search existing issues (maybe there's already a solution)

## 📄 License

This project is licensed under the **MIT License** – see the [LICENSE](LICENSE) file for details.

## 👏 Acknowledgments

- [MediaPipe](https://mediapipe.dev) – Hand gesture recognition
- [FastAPI](https://fastapi.tiangolo.com) – Modern web framework
- [OpenCV](https://opencv.org) – Computer Vision
- [rpicam-apps](https://github.com/raspberrypi/rpicam-apps) – Camera utilities

---

Made with ❤️ for the padel & tennis community.
