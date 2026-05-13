import json, time, threading, io, cv2, numpy as np, os, asyncio, subprocess, queue, math
from pathlib import Path
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
import mediapipe as mp
import requests

def angle_deg(a, b, c):
    """Winkel am Punkt b für Dreieck (a-b-c). a,b,c sind (x,y)."""
    ax, ay = a; bx, by = b; cx, cy = c
    v1x, v1y = ax - bx, ay - by
    v2x, v2y = cx - bx, cy - by
    dot = v1x*v2x + v1y*v2y
    n1 = math.hypot(v1x, v1y); n2 = math.hypot(v2x, v2y)
    if n1*n2 == 0: return 0.0
    cosang = max(-1.0, min(1.0, dot/(n1*n2)))
    return math.degrees(math.acos(cosang))

def visible(lm, thresh=0.5):
    return getattr(lm, "visibility", 1.0) >= thresh

def in01(p):
    x,y = p
    return 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0

router = APIRouter(prefix="/api/webcam", tags=["webcam"])

# === Settings/Persistenz ===
SETTINGS_PATH = Path("data/webcam_settings.json")
SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)

DEFAULT_SETTINGS = {
    "device": "/dev/video0",
    "roi_polygon": [],
    "hand_over_head_margin": 0.02,
    "cooldown_ms": 1500,
    "width": 640,
    "height": 480,
    "fps": 15
}

def load_settings():
    if SETTINGS_PATH.exists():
        return json.loads(SETTINGS_PATH.read_text())
    SETTINGS_PATH.write_text(json.dumps(DEFAULT_SETTINGS, indent=2))
    return DEFAULT_SETTINGS.copy()

def save_settings(s):
    SETTINGS_PATH.write_text(json.dumps(s, indent=2))

# === Kamera-Thread (RASPBERRY PI 5 OPTIMIERT) ===
class Camera:
    def __init__(self, width=640, height=480, fps=15):
        self.width = width
        self.height = height
        self.queue = queue.Queue(maxsize=2)
        self.lock = threading.Lock()
        self.frame = None
        self.running = True
        self.frame_count = 0
        
        print(f"[Camera] Starting camera: {width}x{height} @ {fps}fps")
        
        # Start rpicam-vid process
        self.process = subprocess.Popen([
            'rpicam-vid', '-t', '0',
            '--width', str(width),
            '--height', str(height),
            '--framerate', str(fps),
            '--codec', 'mjpeg',
            '--nopreview',
            '-o', '-'
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=10**8)
        
        print(f"[Camera] rpicam-vid process started, PID: {self.process.pid}")
        
        self.thread = threading.Thread(target=self._read_stream, daemon=True)
        self.thread.start()
        time.sleep(2)
        print(f"[Camera] Initialization complete")

    def _read_stream(self):
        bytes_buffer = b''
        data_received = 0
        frames_decoded = 0
        
        print(f"[Camera] Stream reader thread started")
        
        while self.running and self.process.poll() is None:
            try:
                # Read from process
                data = self.process.stdout.read(65536)
                if not data:
                    if self.process.poll() is not None:
                        print(f"[Camera] Process ended, poll={self.process.poll()}")
                        break
                    time.sleep(0.01)
                    continue
                
                data_received += len(data)
                if data_received % 1000000 < 65536:
                    print(f"[Camera] Received {data_received} bytes, {frames_decoded} frames decoded")
                
                bytes_buffer += data
                a = bytes_buffer.find(b'\xff\xd8')  # JPEG start
                b = bytes_buffer.find(b'\xff\xd9')  # JPEG end
                
                while a != -1 and b != -1 and b > a:
                    jpg = bytes_buffer[a:b+2]
                    bytes_buffer = bytes_buffer[b+2:]
                    
                    # Decode JPEG
                    nparr = np.frombuffer(jpg, np.uint8)
                    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    
                    if frame is not None:
                        with self.lock:
                            self.frame = frame
                            self.frame_count += 1
                        frames_decoded += 1
                        if frames_decoded % 30 == 0:
                            print(f"[Camera] Decoded {frames_decoded} frames")
                    
                    # Find next JPEG
                    a = bytes_buffer.find(b'\xff\xd8')
                    b = bytes_buffer.find(b'\xff\xd9')
            except Exception as e:
                print(f"[Camera] Error in stream: {e}")
                time.sleep(0.1)
                continue
        
        print(f"[Camera] Stream reader thread ended")

    def get_frame(self):
        with self.lock:
            return None if self.frame is None else self.frame.copy()

    def stop(self):
        self.running = False
        if self.process:
            self.process.terminate()
            self.process.wait(timeout=2)
        if self.thread:
            self.thread.join(timeout=1)

camera = None
def ensure_camera():
    global camera
    if camera is None:
        settings = load_settings()
        width = settings.get("width", 640)
        height = settings.get("height", 480)
        fps = settings.get("fps", 15)
        camera = Camera(width=width, height=height, fps=fps)
        print("Camera initialized")

# === Pose/Gesten ===
mp_pose = mp.solutions.pose
pose = mp_pose.Pose(static_image_mode=False, model_complexity=0,
                    enable_segmentation=False, min_detection_confidence=0.5,
                    min_tracking_confidence=0.5)

def point_in_poly(pt, poly):
    x, y = pt
    n = len(poly)
    if n < 3:
        return True
    inside = False
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i+1) % n]
        if ((y1 > y) != (y2 > y)) and (x < (x2-x1)*(y-y1)/(y2-y1+1e-9)+x1):
            inside = not inside
    return inside

last_event_ts = 0

def ready_to_fire(cooldown_ms):
    global last_event_ts
    return (time.time() - last_event_ts) >= (cooldown_ms/1000.0)

def mark_fired():
    global last_event_ts
    last_event_ts = time.time()

def infer_gesture(frame_bgr, settings):
    if frame_bgr is None:
        return None, None
        
    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    res = pose.process(rgb)
    if not res.pose_landmarks:
        return None, None

    lm = res.pose_landmarks.landmark
    PL = mp_pose.PoseLandmark

    # Landmarks
    NOSE = lm[PL.NOSE.value]
    LW   = lm[PL.LEFT_WRIST.value]
    RW   = lm[PL.RIGHT_WRIST.value]
    LE   = lm[PL.LEFT_ELBOW.value]
    RE   = lm[PL.RIGHT_ELBOW.value]
    LS   = lm[PL.LEFT_SHOULDER.value]
    RS   = lm[PL.RIGHT_SHOULDER.value]

    # Sichtbarkeit prüfen
    if not (visible(LW) and visible(LE) and visible(LS) and
            visible(RW) and visible(RE) and visible(RS)):
        return None, None

    # Kopf-/Schulter-Linie
    head_y = (NOSE.y + min(LS.y, RS.y)) / 2.0
    shoulder_line = min(LS.y, RS.y)
    margin = float(settings.get("hand_over_head_margin", 0.02))
    roi = settings.get("roi_polygon", [])

    # Ellbogen-Winkel
    angle_left  = angle_deg((LS.x,LS.y), (LE.x,LE.y), (LW.x,LW.y))
    angle_right = angle_deg((RS.x,RS.y), (RE.x,RE.y), (RW.x,RW.y))
    STRAIGHT_MIN = 145.0
    MIN_HAND_OVER = 0.02

    # Teilkriterien
    left_hand_over   = (head_y - (LW.y + margin)) > MIN_HAND_OVER
    right_hand_over  = (head_y - (RW.y + margin)) > MIN_HAND_OVER
    left_elbow_high  = (LE.y + margin*0.5) < (shoulder_line + 0.03)
    right_elbow_high = (RE.y + margin*0.5) < (shoulder_line + 0.03)
    left_straight    = angle_left  >= STRAIGHT_MIN
    right_straight   = angle_right >= STRAIGHT_MIN
    left_in_roi      = point_in_poly((LW.x, LW.y), roi)
    right_in_roi     = point_in_poly((RW.x, RW.y), roi)

    left_up  = left_hand_over  and left_elbow_high  and left_straight  and left_in_roi
    right_up = right_hand_over and right_elbow_high and right_straight and right_in_roi

    if left_up and right_up:
        gesture = "UNDO"
    elif left_up:
        gesture = "TEAM_A"
    elif right_up:
        gesture = "TEAM_B"
    else:
        gesture = None

    marks = {
        "nose": (NOSE.x, NOSE.y),
        "lw": (LW.x,LW.y), "rw": (RW.x,RW.y),
        "ls": (LS.x,LS.y), "rs": (RS.x,RS.y),
        "le": (LE.x,LE.y), "re": (RE.x,RE.y),
        "head_y": head_y,
        "angle_left": angle_left, "angle_right": angle_right
    }
    return gesture, marks

# === MJPEG Stream ===
@router.get("/video.mjpeg")
def video_mjpeg():
    ensure_camera()
    def gen():
        frame_count = 0
        while True:
            frame = camera.get_frame()
            if frame is None:
                time.sleep(0.02)
                continue
            
            frame_count += 1
            # Nur jedes 2. Frame senden für bessere Performance
            if frame_count % 2 != 0:
                time.sleep(0.02)
                continue
                
            ok, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            if not ok:
                time.sleep(0.02)
                continue
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg.tobytes() + b"\r\n")
    return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame")

# === Settings Endpoints ===
settings = load_settings()

@router.get("/settings")
def get_settings():
    return settings

@router.put("/settings")
def put_settings(body: dict):
    global settings, camera
    settings.update(body or {})
    save_settings(settings)
    
    # Kamera neu starten wenn Einstellungen geändert
    if camera and any(key in body for key in ["width", "height", "fps"]):
        camera.stop()
        camera = None
        ensure_camera()
    
    return {"ok": True, "settings": settings}

# === WebSocket: Pose-Stream & Auto-Fire ===
@router.websocket("/ws/pose")
async def ws_pose(ws: WebSocket):
    await ws.accept()
    ensure_camera()
    settings = load_settings()
    
    try:
        frame_counter = 0
        while True:
            frame = camera.get_frame()
            if frame is None:
                await ws.send_json({"type": "noop"})
                await asyncio.sleep(0.05)
                continue
            
            frame_counter += 1
            # Nur jedes 3. Frame verarbeiten für Performance
            if frame_counter % 3 != 0:
                await asyncio.sleep(0.05)
                continue
            
            gesture, marks = infer_gesture(frame, settings)
            payload = {"type": "pose", "gesture": gesture, "marks": marks, "fired": False}

            if gesture and ready_to_fire(settings.get("cooldown_ms", 1500)):
                base = os.environ.get("PADEL_API_BASE", "http://127.0.0.1:8080")
                try:
                    if gesture == "UNDO":
                        requests.post(f"{base}/undo", timeout=1.5)
                    elif gesture == "TEAM_A":
                        requests.post(f"{base}/point", json={"team": "A"}, timeout=1.5)
                    elif gesture == "TEAM_B":
                        requests.post(f"{base}/point", json={"team": "B"}, timeout=1.5)
                    mark_fired()
                    payload["fired"] = True
                except Exception as e:
                    print(f"API error: {e}")
            
            await ws.send_json(payload)
            await asyncio.sleep(0.05)
    except WebSocketDisconnect:
        print("WebSocket disconnected")
    except Exception as e:
        print(f"WebSocket error: {e}")
