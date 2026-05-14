#!/usr/bin/env python3
"""
Tennis Scoring System - FastAPI Backend
Vollständiges Backend mit Webcam-Integration, Gestensteuerung und Persistenz
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Tuple
from datetime import datetime
from pathlib import Path
import json
import logging
import sys
import cv2
import mediapipe as mp
import numpy as np
import threading
import time
import subprocess
import queue
import asyncio

# ============================================================================
# LOGGING SETUP
# ============================================================================

class ColoredFormatter(logging.Formatter):
    """Farbiger Logging-Formatter für bessere Lesbarkeit"""
    
    COLORS = {
        'DEBUG': '\033[36m',    # Cyan
        'INFO': '\033[32m',     # Green
        'WARNING': '\033[33m',  # Yellow
        'ERROR': '\033[31m',    # Red
        'CRITICAL': '\033[35m', # Magenta
    }
    RESET = '\033[0m'
    
    def format(self, record):
        log_color = self.COLORS.get(record.levelname, self.RESET)
        record.levelname = f"{log_color}{record.levelname}{self.RESET}"
        return super().format(record)

# Logger konfigurieren
logger = logging.getLogger("openPadel")
logger.setLevel(logging.DEBUG)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.DEBUG)

formatter = ColoredFormatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# File Handler für persistente Logs
log_file = Path("openpadel.log")
file_handler = logging.FileHandler(log_file, encoding='utf-8')
file_handler.setLevel(logging.DEBUG)
file_formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
file_handler.setFormatter(file_formatter)
logger.addHandler(file_handler)

# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class MatchState(BaseModel):
    """Vollständiger Match-Status"""
    player1_name: str = "Spieler 1"
    player2_name: str = "Spieler 2"
    player1_sets: int = 0
    player2_sets: int = 0
    player1_games: int = 0
    player2_games: int = 0
    player1_points: int = 0
    player2_points: int = 0
    server: int = 1
    match_started: bool = False
    match_finished: bool = False
    winner: Optional[str] = None
    match_start_time: Optional[str] = None
    match_end_time: Optional[str] = None
    history: List[Dict] = Field(default_factory=list)
    sets_to_win: int = 2
    game_mode: str = "mit_vorteil_tiebreak"
    set_history: List[List[int]] = Field(default_factory=list)

    # Tie-Break
    in_tiebreak: bool = False
    tiebreak_server_at_start: int = 1  # Welches Team hat bei Punkt 1 aufgeschlagen
    tiebreak_total_points: int = 0  # Gesamtzahl der gespielten Tie-Break Punkte

    # Game-Timing
    current_game_start_time: Optional[str] = None
    game_durations: List[int] = Field(default_factory=list)
    set_durations: List[int] = Field(default_factory=list)

class WebcamSettings(BaseModel):
    """Webcam-Konfiguration"""
    enabled: bool = True
    camera_index: int = 0
    detection_sensitivity: float = 0.7
    cooldown_seconds: float = 10.0
    width: int = 640
    height: int = 480
    fps: int = 10
    gesture_recognition_enabled: bool = True

class WiFiAPSettings(BaseModel):
    """WiFi Access Point Konfiguration"""
    ssid: str = "openPadel"
    password: str = "openpadel"
    enabled: bool = True

class MatchStatistics(BaseModel):
    """Match-Statistiken"""
    total_points: int
    duration_minutes: int
    player1_points_won: int
    player2_points_won: int
    longest_game_points: int

class GameModeRules(BaseModel):
    sets_to_win: int = 2
    games_to_win_set: int = 6
    games_minimum_difference: int = 2
    advantage: bool = True
    tiebreak: bool = True
    tiebreak_at_games: List[int] = Field(default_factory=lambda: [6, 6])
    tiebreak_points_to_win: int = 7
    tiebreak_minimum_difference: int = 2
    golden_point: bool = False

class GameModePayload(BaseModel):
    id: str
    name: str
    description: str = ""
    is_custom: bool = True
    rules: GameModeRules

# ============================================================================
# GAME LOGIC
# ============================================================================

class GameModeManager:
    """Verwaltet verfügbare Spielmodi"""
    
    def __init__(self, modes_dir: Path = Path("game_modes")):
        self.modes_dir = modes_dir
        self.modes_dir.mkdir(exist_ok=True)
        self.modes = self.load_modes()
    
    def load_modes(self) -> Dict[str, Dict]:
        """Lädt alle Spielmodi aus dem Verzeichnis"""
        modes = {}
        if not self.modes_dir.exists():
            return modes
        
        for mode_file in self.modes_dir.glob("*.json"):
            # Überspringe macOS Metadaten-Dateien
            if mode_file.name.startswith('._'):
                continue
                
            try:
                with open(mode_file, 'r', encoding='utf-8') as f:
                    mode_data = json.load(f)
                    mode_id = mode_file.stem
                    modes[mode_id] = mode_data
                    logger.info(f"Spielmodus geladen: {mode_data['name']} ({mode_id})")
            except Exception as e:
                logger.error(f"Fehler beim Laden von {mode_file}: {e}")
        
        return modes
    
    def get_mode(self, mode_id: str) -> Optional[Dict]:
        """Gibt Spielmodus nach ID zurück"""
        return self.modes.get(mode_id)
    
    def list_modes(self) -> List[Dict]:
        """Gibt Liste aller verfügbaren Modi zurück"""
        return [
            {"id": mode_id, "name": mode["name"], "description": mode["description"]}
            for mode_id, mode in self.modes.items()
        ]

    def save_mode(self, mode_id: str, mode_data: Dict):
        """Speichert Spielmodus (Upsert) auf Disk und im RAM"""
        mode_file = self.modes_dir / f"{mode_id}.json"
        with open(mode_file, 'w', encoding='utf-8') as f:
            json.dump(mode_data, f, indent=2, ensure_ascii=False)
        self.modes[mode_id] = mode_data
        logger.info(f"Spielmodus gespeichert: {mode_data.get('name')} ({mode_id})")

    def delete_mode(self, mode_id: str) -> bool:
        """Löscht Spielmodus von Disk und aus RAM. Returns False wenn nicht gefunden."""
        mode_file = self.modes_dir / f"{mode_id}.json"
        if mode_id not in self.modes:
            return False
        mode_file.unlink(missing_ok=True)
        del self.modes[mode_id]
        logger.info(f"Spielmodus gelöscht: {mode_id}")
        return True

class GameLogic:
    """Tennis-Regelwerk und Punktberechnung"""
    
    POINT_NAMES = {0: "0", 1: "15", 2: "30", 3: "40"}
    
    def __init__(self, game_mode_manager: GameModeManager):
        self.game_mode_manager = game_mode_manager
    
    def get_score_display(self, p1_points: int, p2_points: int, mode_id: str = "mit_vorteil_tiebreak") -> Tuple[str, str]:
        """
        Gibt die Anzeige-Strings für beide Spieler zurück
        Behandelt Deuce, Advantage, etc.
        """
        mode = self.game_mode_manager.get_mode(mode_id)
        advantage = mode["rules"]["advantage"] if mode else True
        
        if advantage:
            if p1_points >= 3 and p2_points >= 3:
                if p1_points == p2_points:
                    return "40", "40"  # Deuce
                elif p1_points > p2_points:
                    return "AD", "40"  # Advantage Player 1
                else:
                    return "40", "AD"  # Advantage Player 2
        else:
            # No-Ad: Bei 40:40 entscheidet der nächste Punkt
            if p1_points >= 3 and p2_points >= 3:
                return "40", "40"
        
        return (
            self.POINT_NAMES.get(p1_points, "40"),
            self.POINT_NAMES.get(p2_points, "40")
        )
    
    def check_game_won(self, p1_points: int, p2_points: int, mode_id: str = "mit_vorteil_tiebreak") -> Optional[int]:
        """
        Prüft, ob ein Spiel gewonnen wurde
        Returns: 1 für Spieler 1, 2 für Spieler 2, None wenn nicht entschieden
        """
        mode = self.game_mode_manager.get_mode(mode_id)
        advantage = mode["rules"]["advantage"] if mode else True
        
        if advantage:
            if p1_points >= 4 and p1_points - p2_points >= 2:
                return 1
            elif p2_points >= 4 and p2_points - p1_points >= 2:
                return 2
        else:
            # No-Ad: Erster auf 4 Punkte gewinnt
            if p1_points >= 4:
                return 1
            elif p2_points >= 4:
                return 2
        
        return None
    
    def check_set_won(self, p1_games: int, p2_games: int, mode_id: str = "mit_vorteil_tiebreak") -> Optional[int]:
        """
        Prüft, ob ein Satz gewonnen wurde
        Returns: 1 für Spieler 1, 2 für Spieler 2, None wenn nicht entschieden
        """
        mode = self.game_mode_manager.get_mode(mode_id)
        if not mode:
            mode = {"rules": {"games_to_win_set": 6, "games_minimum_difference": 2, "tiebreak": True}}
        
        rules = mode["rules"]
        games_to_win = rules.get("games_to_win_set", 6)
        min_diff = rules.get("games_minimum_difference", 2)
        tiebreak = rules.get("tiebreak", True)
        
        if p1_games >= games_to_win and p1_games - p2_games >= min_diff:
            return 1
        elif p2_games >= games_to_win and p2_games - p1_games >= min_diff:
            return 2
        
        # Tiebreak
        if tiebreak:
            tiebreak_at = rules.get("tiebreak_at_games", [6, 6])
            if p1_games == tiebreak_at[0] and p2_games == tiebreak_at[1]:
                # Im Tiebreak wird dieser Check nicht verwendet
                pass
            elif p1_games == tiebreak_at[0] + 1 and p2_games == tiebreak_at[1]:
                return 1
            elif p2_games == tiebreak_at[1] + 1 and p1_games == tiebreak_at[0]:
                return 2
        
        return None
    
    def check_match_won(self, p1_sets: int, p2_sets: int, sets_to_win: int = 2) -> Optional[int]:
        """
        Prüft, ob das Match gewonnen wurde
        Returns: 1 für Spieler 1, 2 für Spieler 2, None wenn nicht entschieden
        """
        if p1_sets >= sets_to_win:
            return 1
        elif p2_sets >= sets_to_win:
            return 2
        return None
    
    def check_deuce(self, p1_points: int, p2_points: int, mode_id: str = "mit_vorteil_tiebreak") -> bool:
        """
        Prüft, ob Deuce-Situation vorliegt
        Returns: True wenn beide >= 3 Punkte und gleich
        """
        mode = self.game_mode_manager.get_mode(mode_id)
        advantage = mode["rules"]["advantage"] if mode else True
        
        if advantage:
            return p1_points >= 3 and p2_points >= 3 and p1_points == p2_points
        else:
            return False
    
    def check_advantage(self, p1_points: int, p2_points: int, mode_id: str = "mit_vorteil_tiebreak") -> Optional[int]:
        """
        Prüft, ob ein Spieler Advantage hat
        Returns: 1 für Spieler 1, 2 für Spieler 2, None wenn kein Advantage
        """
        mode = self.game_mode_manager.get_mode(mode_id)
        advantage = mode["rules"]["advantage"] if mode else True

        if not advantage:
            return None

        if p1_points >= 4 and p2_points >= 3:
            if p1_points == p2_points + 1:
                return 1
        if p2_points >= 4 and p1_points >= 3:
            if p2_points == p1_points + 1:
                return 2
        return None

    def check_tiebreak_needed(self, p1_games: int, p2_games: int, mode_id: str = "mit_vorteil_tiebreak") -> bool:
        """
        Prüft, ob ein Tie-Break gespielt werden muss (bei 6:6)
        Returns: True wenn Tie-Break nötig ist
        """
        mode = self.game_mode_manager.get_mode(mode_id)
        if not mode:
            return p1_games == 6 and p2_games == 6

        rules = mode["rules"]
        tiebreak = rules.get("tiebreak", True)
        if not tiebreak:
            return False

        tiebreak_at = rules.get("tiebreak_at_games", [6, 6])
        return p1_games == tiebreak_at[0] and p2_games == tiebreak_at[1]

    def check_tiebreak_won(self, p1_points: int, p2_points: int, mode_id: str = "mit_vorteil_tiebreak") -> Optional[int]:
        """
        Prüft, ob das Tie-Break gewonnen wurde
        Verwendet tiebreak_points und tiebreak_minimum_difference aus den Spielregeln
        Returns: 1 für Team 1, 2 für Team 2, None wenn nicht entschieden
        """
        mode = self.game_mode_manager.get_mode(mode_id)
        if mode:
            rules = mode["rules"]
            tiebreak_points = rules.get("tiebreak_points", 7)
            min_diff = rules.get("tiebreak_minimum_difference", 2)
        else:
            # Fallback auf Standard-Werte
            tiebreak_points = 7
            min_diff = 2

        if p1_points >= tiebreak_points and p1_points - p2_points >= min_diff:
            return 1
        elif p2_points >= tiebreak_points and p2_points - p1_points >= min_diff:
            return 2
        return None

    def get_tiebreak_server(self, tiebreak_total_points: int, tiebreak_server_at_start: int) -> int:
        """
        Berechnet welches Team im Tie-Break aufschlagen soll
        Punkt 1: Startteam
        Punkte 2-3: anderes Team
        Punkte 4-5: Startteam
        usw.

        Args:
            tiebreak_total_points: Anzahl der bisher gespielten Tie-Break Punkte
            tiebreak_server_at_start: Welches Team bei Punkt 1 aufgeschlagen hat (1 oder 2)

        Returns: 1 oder 2 (Team-Nummer)
        """
        point_number = tiebreak_total_points + 1  # Nächster Punkt

        if point_number == 1:
            # Erster Punkt: Startteam
            return tiebreak_server_at_start
        elif point_number in [2, 3]:
            # Punkte 2-3: anderes Team
            return 2 if tiebreak_server_at_start == 1 else 1
        else:
            # Ab Punkt 4: alle 2 Punkte wechseln
            # Punkt 4-5: Startteam, 6-7: anderes Team, 8-9: Startteam, ...
            cycle_position = (point_number - 4) // 2
            if cycle_position % 2 == 0:
                return tiebreak_server_at_start
            else:
                return 2 if tiebreak_server_at_start == 1 else 1

# ============================================================================
# STATE MANAGER
# ============================================================================

class StateManager:
    """JSON-basierte Persistenz für Match-Daten"""
    
    def __init__(self, data_dir: Path = Path("data")):
        self.data_dir = data_dir
        self.data_dir.mkdir(exist_ok=True)
        self.state_file = self.data_dir / "match_state.json"
        self.history_file = self.data_dir / "match_history.json"
    
    def save_state(self, state: MatchState):
        """Speichert aktuellen Match-Status"""
        try:
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(state.dict(), f, indent=2, ensure_ascii=False)
            logger.debug(f"Status gespeichert: {state.player1_points}-{state.player2_points}")
        except Exception as e:
            logger.error(f"Fehler beim Speichern: {e}")
    
    def load_state(self) -> MatchState:
        """Lädt gespeicherten Match-Status"""
        try:
            if self.state_file.exists():
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                logger.info("Status geladen")
                return MatchState(**data)
        except Exception as e:
            logger.warning(f"Fehler beim Laden: {e}")
        
        return MatchState()
    
    def save_match_to_history(self, state: MatchState):
        """Speichert abgeschlossenes Match in Historie mit Statistiken"""
        try:
            history = []
            if self.history_file.exists():
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    history = json.load(f)
            
            # Match-Daten mit Statistiken
            match_data = state.dict()
            
            # iOS-Kompatibilität: Explizit benötigte Felder hinzufügen
            match_data['team_a'] = state.player1_name
            match_data['team_b'] = state.player2_name
            match_data['team_a_name'] = state.player1_name
            match_data['team_b_name'] = state.player2_name
            match_data['sets_a'] = state.player1_sets
            match_data['sets_b'] = state.player2_sets
            
            # Berechne Dauer in Sekunden für iOS
            duration_seconds = 0
            duration_minutes = 0
            if state.match_start_time and state.match_end_time:
                try:
                    start = datetime.fromisoformat(state.match_start_time)
                    end = datetime.fromisoformat(state.match_end_time)
                    duration_seconds = int((end - start).total_seconds())
                    duration_minutes = int(duration_seconds / 60)
                except:
                    pass
            
            # iOS erwartet duration_seconds
            match_data['duration_seconds'] = duration_seconds
            
            # Konvertiere set_history zu sets-Format für iOS
            if state.set_history:
                match_data['sets'] = [
                    {"score_a": s[0], "score_b": s[1]} 
                    for s in state.set_history
                ]
            
            # Berechne Statistiken
            player1_points = sum(1 for h in state.history if "Punkt für Spieler 1" in h.get("action", ""))
            player2_points = sum(1 for h in state.history if "Punkt für Spieler 2" in h.get("action", ""))
            
            match_data['statistics'] = {
                "total_points": player1_points + player2_points,
                "duration_minutes": duration_minutes,
                "player1_points_won": player1_points,
                "player2_points_won": player2_points,
                "final_score_sets": f"{state.player1_sets}:{state.player2_sets}"
            }
            
            history.append(match_data)
            
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(history, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Match zur Historie hinzugefügt - {state.winner} gewinnt {state.player1_sets}:{state.player2_sets}")
        except Exception as e:
            logger.error(f"Fehler beim Speichern der Historie: {e}")
    
    def load_history(self) -> List[MatchState]:
        """Lädt Match-Historie"""
        try:
            if self.history_file.exists():
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return [MatchState(**match) for match in data]
        except Exception as e:
            logger.error(f"Fehler beim Laden der Historie: {e}")
        
        return []

# ============================================================================
# WEBCAM SETTINGS MANAGER
# ============================================================================

class WebcamSettingsManager:
    """Verwaltet Webcam-Einstellungen"""
    
    def __init__(self, data_dir: Path = Path("data")):
        self.settings_file = data_dir / "webcam_settings.json"
        self.settings = self.load_settings()
    
    def load_settings(self) -> WebcamSettings:
        """Lädt Webcam-Einstellungen"""
        try:
            if self.settings_file.exists():
                with open(self.settings_file, 'r') as f:
                    data = json.load(f)
                logger.info("Webcam-Einstellungen geladen")
                return WebcamSettings(**data)
        except Exception as e:
            logger.warning(f"Fehler beim Laden der Webcam-Einstellungen: {e}")
        
        return WebcamSettings()
    
    def save_settings(self, settings: WebcamSettings):
        """Speichert Webcam-Einstellungen"""
        try:
            with open(self.settings_file, 'w') as f:
                json.dump(settings.dict(), f, indent=2)
            self.settings = settings
            logger.info("Webcam-Einstellungen gespeichert")
        except Exception as e:
            logger.error(f"Fehler beim Speichern der Webcam-Einstellungen: {e}")

class WiFiAPManager:
    """Verwaltet WiFi Access Point Einstellungen"""
    
    def __init__(self, data_dir: Path = Path("data")):
        self.hostapd_conf = Path("/etc/hostapd/hostapd.conf")
        self.settings = self.load_settings()
    
    def load_settings(self) -> WiFiAPSettings:
        """Lädt WiFi AP Einstellungen direkt aus hostapd.conf"""
        try:
            # Lese aus hostapd.conf
            if self.hostapd_conf.exists():
                ssid = None
                password = None
                
                with open(self.hostapd_conf, 'r') as f:
                    for line in f:
                        line = line.strip()
                        # Ignoriere Kommentare und leere Zeilen
                        if not line or line.startswith('#'):
                            continue
                        if line.startswith('ssid='):
                            ssid = line.split('=', 1)[1].strip()
                            logger.debug(f"SSID aus hostapd.conf: {ssid}")
                        elif line.startswith('wpa_passphrase='):
                            password = line.split('=', 1)[1].strip()
                            logger.debug(f"Passwort aus hostapd.conf gelesen")
                
                if ssid and password:
                    logger.info(f"WiFi AP Einstellungen aus hostapd.conf geladen: SSID={ssid}")
                    return WiFiAPSettings(ssid=ssid, password=password, enabled=True)
                else:
                    logger.warning(f"Unvollständige Daten in hostapd.conf: ssid={'gesetzt' if ssid else 'fehlt'}, password={'gesetzt' if password else 'fehlt'}")
        except Exception as e:
            logger.warning(f"Fehler beim Laden aus hostapd.conf: {e}")
        
        logger.warning("hostapd.conf nicht gefunden oder fehlerhaft, verwende Defaults")
        return WiFiAPSettings()
    
    def save_settings(self, settings: WiFiAPSettings):
        """Speichert WiFi AP Einstellungen (nur für interne Synchronisation)"""
        self.settings = settings
        logger.info(f"WiFi AP Einstellungen aktualisiert: SSID={settings.ssid}")
    
    def reload_from_hostapd(self):
        """Lädt Einstellungen neu aus hostapd.conf"""
        self.settings = self.load_settings()
        return self.settings

# ============================================================================
# LANGUAGE MANAGER
# ============================================================================

class LanguageManager:
    """Verwaltet Mehrsprachigkeit"""
    
    AVAILABLE_LANGUAGES = {
        "en": "English",
        "de": "Deutsch",
        "es": "Español"
    }
    
    def __init__(self, data_dir: Path = Path("data")):
        self.settings_file = data_dir / "language_settings.json"
        self.translations_dir = Path("translations")
        self.current_language = self.load_language()
        self.translations = self.load_translations()
    
    def load_language(self) -> str:
        """Lädt gespeicherte Sprache oder Standard (Englisch)"""
        try:
            if self.settings_file.exists():
                with open(self.settings_file, 'r') as f:
                    data = json.load(f)
                return data.get('language', 'en')
        except Exception as e:
            logger.warning(f"Fehler beim Laden der Sprache: {e}")
        return 'en'  # Standard: Englisch
    
    def save_language(self, language: str):
        """Speichert Spracheinstellung"""
        if language not in self.AVAILABLE_LANGUAGES:
            logger.error(f"Ungültige Sprache: {language}")
            return False
        
        try:
            with open(self.settings_file, 'w') as f:
                json.dump({'language': language}, f, indent=2)
            self.current_language = language
            self.translations = self.load_translations()
            logger.info(f"Sprache gespeichert: {language}")
            return True
        except Exception as e:
            logger.error(f"Fehler beim Speichern der Sprache: {e}")
            return False
    
    def load_translations(self) -> dict:
        """Lädt Übersetzungen für aktuelle Sprache"""
        try:
            translation_file = self.translations_dir / f"{self.current_language}.json"
            if translation_file.exists():
                with open(translation_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Fehler beim Laden der Übersetzungen: {e}")
        
        # Fallback auf Englisch
        try:
            with open(self.translations_dir / "en.json", 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    
    def get(self, key: str, default: str = "") -> str:
        """Holt Übersetzung für Schlüssel (unterstützt verschachtelte Schlüssel mit Punktnotation)"""
        keys = key.split('.')
        value = self.translations
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value if isinstance(value, str) else default

# ============================================================================
# CAMERA (RASPBERRY PI)
# ============================================================================

class Camera:
    """Kamera-Klasse für Raspberry Pi mit rpicam-vid"""
    
    def __init__(self, width=640, height=480, fps=15):
        self.width = width
        self.height = height
        self.lock = threading.Lock()
        self.frame = None
        self.running = True
        self.frame_count = 0
        
        logger.info(f"[Camera] Starting camera: {width}x{height} @ {fps}fps")
        
        # Start rpicam-vid process mit optimierten Parametern
        self.process = subprocess.Popen([
            'rpicam-vid', '-t', '0',
            '--width', str(width),
            '--height', str(height),
            '--framerate', str(fps),
            '--codec', 'mjpeg',
            '--nopreview',
            '--inline',  # Inline headers für besseres Streaming
            '--flush',    # Sofortiges Flushing für weniger Latenz
            '-o', '-'
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)  # Kein Buffering
        
        logger.info(f"[Camera] rpicam-vid process started, PID: {self.process.pid}")
        
        # Thread für stdout (frames)
        self.thread = threading.Thread(target=self._read_stream, daemon=True)
        self.thread.start()
        
        # Thread für stderr (errors/debug)
        self.error_thread = threading.Thread(target=self._read_errors, daemon=True)
        self.error_thread.start()
        
        time.sleep(2)
        
        # Prüfe ob Prozess noch läuft
        if self.process.poll() is not None:
            logger.error(f"[Camera] rpicam-vid process died immediately with code {self.process.poll()}")
        else:
            logger.info(f"[Camera] Initialization complete")
    
    def _read_errors(self):
        """Liest stderr vom rpicam-vid Prozess"""
        try:
            for line in iter(self.process.stderr.readline, b''):
                if line:
                    logger.warning(f"[Camera stderr] {line.decode().strip()}")
        except Exception as e:
            logger.error(f"[Camera] Error reading stderr: {e}")
    
    def _read_stream(self):
        bytes_buffer = b''
        data_received = 0
        frames_decoded = 0
        
        logger.info(f"[Camera] Stream reader thread started")
        
        while self.running and self.process.poll() is None:
            try:
                # Read from process (kleinerer Buffer für weniger Latenz)
                data = self.process.stdout.read(32768)
                if not data:
                    if self.process.poll() is not None:
                        logger.warning(f"[Camera] Process ended, poll={self.process.poll()}")
                        break
                    time.sleep(0.01)
                    continue
                
                data_received += len(data)
                if data_received % 1000000 < 32768:
                    logger.info(f"[Camera] Received {data_received} bytes, {frames_decoded} frames decoded")
                
                bytes_buffer += data
                
                # Buffer-Größe begrenzen (Memory-Optimierung)
                if len(bytes_buffer) > 500000:
                    bytes_buffer = bytes_buffer[-500000:]
                
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
                        if frames_decoded == 1:
                            logger.info(f"[Camera] First frame decoded successfully!")
                        if frames_decoded % 30 == 0:
                            logger.info(f"[Camera] Decoded {frames_decoded} frames")
                    
                    # Find next JPEG
                    a = bytes_buffer.find(b'\xff\xd8')
                    b = bytes_buffer.find(b'\xff\xd9')
            except Exception as e:
                logger.error(f"[Camera] Error in stream: {e}")
                time.sleep(0.1)
                continue
        
        logger.warning(f"[Camera] Stream reader thread ended")
    
    def get_frame(self):
        with self.lock:
            return None if self.frame is None else self.frame.copy()
    
    def stop(self):
        self.running = False
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except:
                self.process.kill()
        if self.thread:
            self.thread.join(timeout=1)
        logger.info("[Camera] Stopped")

# ============================================================================
# GESTURE RECOGNIZER
# ============================================================================

class GestureRecognizer:
    """MediaPipe-basierte Gestenerkennung für Webcam-Steuerung"""
    
    def __init__(self, settings_manager: WebcamSettingsManager):
        self.settings_manager = settings_manager
        self.mp_hands = mp.solutions.hands
        self.hands = None
        self.camera = None
        self.is_running = False
        self.last_gesture_time = 0
        self.frame_lock = threading.Lock()
        self.latest_frame = None
        self.on_gesture_callback = None
        self.last_gesture = None
        self.last_gesture_timestamp = None
    
    def start(self):
        """Startet Webcam und Gestenerkennung"""
        if self.is_running:
            return
        
        settings = self.settings_manager.settings
        if not settings.enabled:
            logger.info("Webcam ist deaktiviert")
            return
        
        try:
            # Verwende Camera-Klasse mit Einstellungen
            self.camera = Camera(
                width=settings.width, 
                height=settings.height, 
                fps=settings.fps
            )
            
            self.hands = self.mp_hands.Hands(
                static_image_mode=False,
                max_num_hands=2,  # Bis zu 2 Hände erkennen
                min_detection_confidence=settings.detection_sensitivity,
                min_tracking_confidence=0.5
            )
            
            self.is_running = True
            threading.Thread(target=self._capture_loop, daemon=True).start()
            logger.info("Webcam gestartet mit rpicam-vid")
        
        except Exception as e:
            logger.error(f"Fehler beim Starten der Webcam: {e}")
    
    def stop(self):
        """Stoppt Webcam und Gestenerkennung"""
        self.is_running = False
        if self.camera:
            self.camera.stop()
        if self.hands:
            self.hands.close()
        logger.info("Webcam gestoppt")
    
    def _restart_camera(self):
        """Startet nur die Kamera neu (ohne capture loop neu zu starten)"""
        try:
            if self.camera:
                self.camera.stop()
            settings = self.settings_manager.settings
            self.camera = Camera(width=settings.width, height=settings.height, fps=settings.fps)
            logger.info("[GestureRecognizer] Camera restarted by watchdog")
        except Exception as e:
            logger.error(f"[GestureRecognizer] Camera restart failed: {e}")

    def _capture_loop(self):
        """Haupt-Capture-Loop (läuft in separatem Thread)"""
        frame_counter = 0
        gesture_cooldown_until = 0
        last_frame_time = time.time()
        logger.info("[GestureRecognizer] Capture loop started")

        while self.is_running:
            frame = self.camera.get_frame()
            if frame is None:
                if time.time() - last_frame_time > 15:
                    logger.warning("[GestureRecognizer] No frame for 15s – restarting camera")
                    self._restart_camera()
                    last_frame_time = time.time()
                time.sleep(1.0)
                continue
            last_frame_time = time.time()
            
            frame_counter += 1

            if frame_counter == 1:
                logger.info("[GestureRecognizer] First frame received from camera")

            # Prüfe ob Gestenerkennung aktiviert ist
            if not self.settings_manager.settings.gesture_recognition_enabled:
                # Frame horizontal spiegeln für Anzeige
                flipped_frame = cv2.flip(frame, 1)
                with self.frame_lock:
                    self.latest_frame = flipped_frame
                time.sleep(0.015)
                continue

            # Nur jedes 6. Frame für Gestenerkennung verarbeiten (noch weniger CPU)
            # UND nur wenn kein Cooldown aktiv ist
            current_time = time.time()
            if frame_counter % 6 != 0 or current_time < gesture_cooldown_until:
                # Frame horizontal spiegeln für Anzeige
                flipped_frame = cv2.flip(frame, 1)
                with self.frame_lock:
                    self.latest_frame = flipped_frame
                time.sleep(0.015)
                continue

            # Gestenerkennung auf UNGESPIEGELTEM Bild (für korrekte Hand-Labels)
            small_frame = cv2.resize(frame, (240, 180))  # Original-Frame ohne Spiegelung
            rgb_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
            
            try:
                results = self.hands.process(rgb_frame)

                # Gesten-Erkennung
                if results.multi_hand_landmarks and results.multi_handedness:
                    # Sammle alle Hände mit ihren Informationen
                    hands_info = []
                    for hand_landmarks, handedness in zip(results.multi_hand_landmarks, results.multi_handedness):
                        hand_label = handedness.classification[0].label
                        wrist = hand_landmarks.landmark[0]
                        hands_info.append({
                            'landmarks': hand_landmarks,
                            'label': hand_label,
                            'wrist': wrist
                        })

                    # Prüfe zuerst auf T-Pose (2 Hände erkannt)
                    if len(hands_info) >= 2:
                        crossed = self._check_t_pose(hands_info)
                        if crossed:
                            logger.info("[Gesture] T-Pose erkannt → Undo")
                            self._handle_gesture("undo")
                            gesture_cooldown_until = current_time + 1.0
                        else:
                            # Keine verkreuzten Arme → prüfe einzelne Hände über Kopf
                            for hand_info in hands_info:
                                if hand_info['wrist'].y < 0.3:  # Hand über Kopf
                                    gesture = self._recognize_hand_above_head(hand_info['label'])
                                    if gesture:
                                        self._handle_gesture(gesture)
                                        gesture_cooldown_until = current_time + 1.0
                                        break  # Nur erste Hand über Kopf zählt
                    # Nur eine Hand → prüfe ob über Kopf
                    elif len(hands_info) == 1:
                        hand_info = hands_info[0]
                        if hand_info['wrist'].y < 0.3:  # Hand über Kopf
                            gesture = self._recognize_hand_above_head(hand_info['label'])
                            if gesture:
                                self._handle_gesture(gesture)
                                gesture_cooldown_until = current_time + 1.0
            except Exception as e:
                logger.error(f"[GestureRecognizer] Error in gesture recognition: {e}")

            # Frame horizontal spiegeln für Anzeige
            flipped_frame = cv2.flip(frame, 1)
            with self.frame_lock:
                self.latest_frame = flipped_frame

            time.sleep(0.015)
    
    def _check_t_pose(self, hands_info: list) -> bool:
        """
        Prüft ob beide Arme auf Schulterhöhe ausgestreckt sind (T-Pose = Undo)

        Bedingungen:
        - Beide Hände sichtbar
        - Beide Handgelenke auf Schulterhöhe (y zwischen 0.2 und 0.65)
        - Hände weit auseinander horizontal (Abstand > 0.5)
        - Hände auf ähnlicher Höhe (vertikale Differenz < 0.15)
        """
        if len(hands_info) < 2:
            return False

        left_hand = None
        right_hand = None

        for hand_info in hands_info:
            if hand_info['label'] == 'Left':
                left_hand = hand_info
            elif hand_info['label'] == 'Right':
                right_hand = hand_info

        if not left_hand or not right_hand:
            return False

        left_wrist = left_hand['wrist']
        right_wrist = right_hand['wrist']

        # Beide Handgelenke auf Schulterhöhe (nicht über Kopf, nicht zu tief)
        if not (0.2 < left_wrist.y < 0.65 and 0.2 < right_wrist.y < 0.65):
            logger.debug(f"[Gesture] T-Pose: Hände nicht auf Schulterhöhe: Left y={left_wrist.y:.2f}, Right y={right_wrist.y:.2f}")
            return False

        # Hände müssen weit ausgestreckt sein (mindestens 50% der Bildbreite Abstand)
        horizontal_distance = abs(left_wrist.x - right_wrist.x)
        if horizontal_distance < 0.5:
            logger.debug(f"[Gesture] T-Pose: Hände nicht weit genug ausgestreckt: Abstand={horizontal_distance:.2f}")
            return False

        # Hände müssen auf ähnlicher Höhe sein (max. 15% Unterschied)
        vertical_difference = abs(left_wrist.y - right_wrist.y)
        if vertical_difference > 0.15:
            logger.debug(f"[Gesture] T-Pose: Hände nicht auf gleicher Höhe: Diff={vertical_difference:.2f}")
            return False

        logger.info(f"[Gesture] T-Pose erkannt → Undo (Left: x={left_wrist.x:.2f}, y={left_wrist.y:.2f} | Right: x={right_wrist.x:.2f}, y={right_wrist.y:.2f})")
        return True

    def _recognize_hand_above_head(self, hand_label: str) -> Optional[str]:
        """
        Erkennt welche Hand über dem Kopf ist
        NEUE ZUORDNUNG:
        - Linke Hand über Kopf → Team A
        - Rechte Hand über Kopf → Team B
        """
        # WICHTIG: MediaPipe verarbeitet das UNGESPIEGELTE Bild
        # "Left" = Linke Hand der Person → Team A
        # "Right" = Rechte Hand der Person → Team B
        if hand_label == "Left":
            logger.info(f"[Gesture] Linke Hand über Kopf erkannt → Team A (label={hand_label})")
            return "team_a"
        elif hand_label == "Right":
            logger.info(f"[Gesture] Rechte Hand über Kopf erkannt → Team B (label={hand_label})")
            return "team_b"

        return None
    
    def _handle_gesture(self, gesture: str):
        """Verarbeitet erkannte Geste mit Cooldown (außer Undo)"""
        current_time = time.time()
        cooldown = self.settings_manager.settings.cooldown_seconds

        # Undo hat KEIN Cooldown - kann jederzeit ausgeführt werden
        if gesture != "undo":
            if current_time - self.last_gesture_time < cooldown:
                return

        self.last_gesture_time = current_time
        self.last_gesture = gesture
        self.last_gesture_timestamp = datetime.now().isoformat()

        if self.on_gesture_callback:
            self.on_gesture_callback(gesture)
            logger.info(f"Geste erkannt: {gesture}")
    
    def get_latest_frame(self) -> Optional[np.ndarray]:
        """Gibt aktuellen Frame zurück (thread-safe)"""
        with self.frame_lock:
            return self.latest_frame.copy() if self.latest_frame is not None else None

# ============================================================================
# FASTAPI APPLICATION
# ============================================================================

app = FastAPI(
    title="Tennis Scoring System",
    description="Professionelles Tennis-Scoring mit Webcam-Gestensteuerung",
    version="1.0.0"
)

# Static Files und Templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
templates.env.cache = None  # Workaround: Jinja2 3.1.4 unhashable dict in cache key

# Globale Instanzen
state_manager = StateManager()
webcam_settings_manager = WebcamSettingsManager()
wifi_ap_manager = WiFiAPManager()
language_manager = LanguageManager()
gesture_recognizer = GestureRecognizer(webcam_settings_manager)
game_mode_manager = GameModeManager()
game_logic = GameLogic(game_mode_manager)

# Aktueller Match-Status (im RAM)
current_match = state_manager.load_state()

# Server-Start-Zeit für Uptime
server_start_time = datetime.now()

# Prüfe und starte hostapd beim Server-Start (nur auf Raspberry Pi)
try:
    import platform
    if platform.machine() in ['armv7l', 'aarch64']:
        logger.info("Prüfe hostapd Status beim Server-Start...")
        result = subprocess.run(['systemctl', 'is-active', 'hostapd'],
                              capture_output=True, text=True, check=False)
        
        if result.stdout.strip() != 'active':
            logger.warning("hostapd läuft nicht, starte es...")
            subprocess.run(['sudo', 'systemctl', 'start', 'hostapd'], check=False)
            time.sleep(2)
            
            # Prüfe erneut
            result = subprocess.run(['systemctl', 'is-active', 'hostapd'],
                                  capture_output=True, text=True, check=False)
            if result.stdout.strip() == 'active':
                logger.info("hostapd erfolgreich gestartet")
            else:
                logger.error("hostapd konnte nicht gestartet werden")
        else:
            logger.info("hostapd läuft bereits")
except Exception as e:
    logger.debug(f"hostapd-Check übersprungen: {e}")

# Gesture-Callback
def handle_gesture(gesture: str):
    """Callback für Gestenerkennung"""
    global current_match
    
    if gesture == "team_a":
        current_match = add_point(current_match, 1)  # Team A = Spieler 1
    elif gesture == "team_b":
        current_match = add_point(current_match, 2)  # Team B = Spieler 2
    elif gesture == "undo":
        # Undo letzter Punkt
        current_match = undo_point(current_match)
        logger.info("Geste: Undo letzter Punkt")

gesture_recognizer.on_gesture_callback = handle_gesture

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_template_context(request: Request, **kwargs) -> dict:
    """Erstellt Template-Context mit Übersetzungen"""
    context = {
        "t": language_manager.translations,
        "current_lang": language_manager.current_language,
        **kwargs
    }
    return context

def calculate_statistics(state: MatchState) -> Dict:
    """Berechnet Match-Statistiken aus dem State"""
    player1_points = sum(1 for h in state.history if "Punkt für Spieler 1" in h.get("action", ""))
    player2_points = sum(1 for h in state.history if "Punkt für Spieler 2" in h.get("action", ""))
    
    duration_minutes = 0
    if state.match_start_time and state.match_end_time:
        try:
            start = datetime.fromisoformat(state.match_start_time)
            end = datetime.fromisoformat(state.match_end_time)
            duration_minutes = int((end - start).total_seconds() / 60)
        except:
            pass
    
    return {
        "total_points": player1_points + player2_points,
        "duration_minutes": duration_minutes,
        "player1_points_won": player1_points,
        "player2_points_won": player2_points,
        "player1_name": state.player1_name,
        "player2_name": state.player2_name,
        "winner": state.winner,
        "sets": f"{state.player1_sets}:{state.player2_sets}",
        "set_history": state.set_history,
        "match_end_time": state.match_end_time
    }

def undo_point(state: MatchState) -> MatchState:
    """
    Macht letzten Punkt rückgängig - VOLLSTÄNDIGE IMPLEMENTIERUNG MIT TIEBREAK

    Rekonstruiert den kompletten State aus der History neu, inkl. Tiebreak-Logik
    """
    if len(state.history) == 0:
        logger.warning("Keine History zum Undo vorhanden")
        return state

    # Entferne letzten History-Eintrag
    removed_action = state.history.pop()
    logger.info(f"Undo: {removed_action.get('action')}")

    # Speichere wichtige Einstellungen
    player1_name = state.player1_name
    player2_name = state.player2_name
    game_mode = state.game_mode
    sets_to_win = state.sets_to_win
    match_start_time = state.match_start_time

    # Erstelle neuen State
    new_state = MatchState(
        player1_name=player1_name,
        player2_name=player2_name,
        game_mode=game_mode,
        sets_to_win=sets_to_win,
        match_start_time=match_start_time,
        match_started=True if match_start_time else False,
        server=1  # Startet bei 1, wird beim Replay korrekt gesetzt
    )

    # Replay alle verbleibenden History-Einträge
    temp_history = state.history.copy()
    new_state.history = []

    for action in temp_history:
        # Extrahiere Spieler aus Action
        if "Punkt für Spieler 1" in action.get("action", "") or "Punkt für Team 1" in action.get("action", ""):
            player = 1
        elif "Punkt für Spieler 2" in action.get("action", "") or "Punkt für Team 2" in action.get("action", ""):
            player = 2
        else:
            continue

        # Prüfen ob Tie-Break gestartet werden muss
        if not new_state.in_tiebreak and game_logic.check_tiebreak_needed(
            new_state.player1_games,
            new_state.player2_games,
            new_state.game_mode
        ):
            new_state.in_tiebreak = True
            new_state.tiebreak_server_at_start = new_state.server
            new_state.tiebreak_total_points = 0
            new_state.player1_points = 0
            new_state.player2_points = 0
            logger.info(f"Tie-Break gestartet beim Replay! Team {new_state.tiebreak_server_at_start} beginnt.")

        # Punkt hinzufügen
        if player == 1:
            new_state.player1_points += 1
        else:
            new_state.player2_points += 1

        # Im Tie-Break: Punktzähler erhöhen
        if new_state.in_tiebreak:
            new_state.tiebreak_total_points += 1

        # History-Eintrag hinzufügen
        new_state.history.append(action)

        # Tie-Break Logik
        if new_state.in_tiebreak:
            tiebreak_winner = game_logic.check_tiebreak_won(
                new_state.player1_points,
                new_state.player2_points,
                new_state.game_mode
            )

            if tiebreak_winner:
                # Tie-Break gewonnen = Satz gewonnen
                logger.info(f"Tie-Break gewonnen beim Replay: Team {tiebreak_winner}")

                # Satz-Historie mit Tie-Break speichern
                mode = game_logic.game_mode_manager.get_mode(new_state.game_mode)
                if mode:
                    tiebreak_at = mode["rules"].get("tiebreak_at_games", [6, 6])
                else:
                    tiebreak_at = [6, 6]

                if tiebreak_winner == 1:
                    new_state.set_history.append([tiebreak_at[0] + 1, tiebreak_at[1]])
                    new_state.player1_sets += 1
                else:
                    new_state.set_history.append([tiebreak_at[0], tiebreak_at[1] + 1])
                    new_state.player2_sets += 1

                # Tie-Break beenden und zurücksetzen
                new_state.in_tiebreak = False
                new_state.tiebreak_total_points = 0
                new_state.player1_games = 0
                new_state.player2_games = 0
                new_state.player1_points = 0
                new_state.player2_points = 0

                # Aufschlag wechselt zum anderen Team für den nächsten Satz
                new_state.server = 2 if tiebreak_winner == 1 else 1

                # Match gewonnen?
                match_winner = game_logic.check_match_won(
                    new_state.player1_sets,
                    new_state.player2_sets,
                    new_state.sets_to_win
                )

                if match_winner:
                    new_state.match_finished = True
                    new_state.winner = player1_name if match_winner == 1 else player2_name
            else:
                # Tie-Break läuft weiter - Aufschlagwechsel nach Tie-Break Regeln
                new_state.server = game_logic.get_tiebreak_server(
                    new_state.tiebreak_total_points,
                    new_state.tiebreak_server_at_start
                )
        else:
            # Normales Spiel (kein Tie-Break)
            game_winner = game_logic.check_game_won(
                new_state.player1_points,
                new_state.player2_points,
                new_state.game_mode
            )

            if game_winner:
                if game_winner == 1:
                    new_state.player1_games += 1
                else:
                    new_state.player2_games += 1

                # Punkte zurücksetzen
                new_state.player1_points = 0
                new_state.player2_points = 0

                # Aufschlagwechsel
                new_state.server = 2 if new_state.server == 1 else 1

                # Prüfe ob Satz gewonnen
                set_winner = game_logic.check_set_won(
                    new_state.player1_games,
                    new_state.player2_games,
                    new_state.game_mode
                )

                if set_winner:
                    # Satz-Historie speichern
                    new_state.set_history.append([new_state.player1_games, new_state.player2_games])

                    if set_winner == 1:
                        new_state.player1_sets += 1
                    else:
                        new_state.player2_sets += 1

                    # Games zurücksetzen
                    new_state.player1_games = 0
                    new_state.player2_games = 0

                    # Prüfe ob Match gewonnen
                    match_winner = game_logic.check_match_won(
                        new_state.player1_sets,
                        new_state.player2_sets,
                        new_state.sets_to_win
                    )

                    if match_winner:
                        new_state.match_finished = True
                        new_state.winner = player1_name if match_winner == 1 else player2_name

    # Status speichern
    state_manager.save_state(new_state)

    tiebreak_status = "im Tiebreak" if new_state.in_tiebreak else "normales Spiel"
    logger.info(f"Undo abgeschlossen ({tiebreak_status}): Score jetzt {new_state.player1_points}-{new_state.player2_points}, Games {new_state.player1_games}-{new_state.player2_games}, Sets {new_state.player1_sets}-{new_state.player2_sets}")

    return new_state

def add_point(state: MatchState, player: int) -> MatchState:
    """
    Fügt einem Spieler einen Punkt hinzu und aktualisiert den Status
    player: 1 oder 2
    """
    if state.match_finished:
        return state

    # Match starten, falls noch nicht geschehen
    if not state.match_started:
        state.match_started = True
        state.match_start_time = datetime.now().isoformat()
        state.current_game_start_time = datetime.now().isoformat()

    # Game-Timer starten beim ersten Punkt
    if state.current_game_start_time is None:
        state.current_game_start_time = datetime.now().isoformat()

    # Prüfen ob Tie-Break gestartet werden muss
    if not state.in_tiebreak and game_logic.check_tiebreak_needed(state.player1_games, state.player2_games, state.game_mode):
        state.in_tiebreak = True
        state.tiebreak_server_at_start = state.server
        state.tiebreak_total_points = 0
        state.player1_points = 0
        state.player2_points = 0
        logger.info(f"Tie-Break gestartet! Team {state.tiebreak_server_at_start} beginnt.")

    # Punkt hinzufügen
    if player == 1:
        state.player1_points += 1
    else:
        state.player2_points += 1

    # Im Tie-Break: Punktzähler erhöhen
    if state.in_tiebreak:
        state.tiebreak_total_points += 1

    # History-Eintrag
    state.history.append({
        "timestamp": datetime.now().isoformat(),
        "action": f"Punkt für {'Team ' + str(player)}",
        "score": f"{state.player1_points}-{state.player2_points}"
    })

    # Tie-Break Logik
    if state.in_tiebreak:
        tiebreak_winner = game_logic.check_tiebreak_won(state.player1_points, state.player2_points, state.game_mode)
        if tiebreak_winner:
            # Tie-Break gewonnen = Satz gewonnen
            logger.info(f"Tie-Break gewonnen: Team {tiebreak_winner} ({state.player1_points}:{state.player2_points})")

            # Berechne Game-Dauer
            if state.current_game_start_time:
                try:
                    game_start = datetime.fromisoformat(state.current_game_start_time)
                    game_end = datetime.now()
                    game_duration = int((game_end - game_start).total_seconds())
                    state.game_durations.append(game_duration)
                    logger.info(f"Tie-Break Dauer: {game_duration}s ({game_duration // 60}m {game_duration % 60}s)")
                except:
                    pass

            # Satz-Historie mit Tie-Break speichern
            # Hole die tiebreak_at_games Werte aus den Spielregeln
            mode = game_logic.game_mode_manager.get_mode(state.game_mode)
            if mode:
                tiebreak_at = mode["rules"].get("tiebreak_at_games", [6, 6])
            else:
                tiebreak_at = [6, 6]

            if tiebreak_winner == 1:
                state.set_history.append([tiebreak_at[0] + 1, tiebreak_at[1]])
                state.player1_sets += 1
            else:
                state.set_history.append([tiebreak_at[0], tiebreak_at[1] + 1])
                state.player2_sets += 1

            # Tie-Break beenden und zurücksetzen
            state.in_tiebreak = False
            state.tiebreak_total_points = 0
            state.player1_games = 0
            state.player2_games = 0
            state.player1_points = 0
            state.player2_points = 0

            # Aufschlag wechselt zum anderen Team für den nächsten Satz
            state.server = 2 if tiebreak_winner == 1 else 1

            # Reset Game-Timer
            state.current_game_start_time = datetime.now().isoformat()

            logger.info(f"Satz gewonnen durch Tie-Break: Team {tiebreak_winner}")

            # Match gewonnen?
            match_winner = game_logic.check_match_won(state.player1_sets, state.player2_sets, state.sets_to_win)
            if match_winner:
                state.match_finished = True
                state.match_end_time = datetime.now().isoformat()
                state.winner = state.player1_name if match_winner == 1 else state.player2_name

                # Berechne Match-Dauer
                if state.match_start_time:
                    try:
                        start = datetime.fromisoformat(state.match_start_time)
                        end = datetime.fromisoformat(state.match_end_time)
                        duration_seconds = int((end - start).total_seconds())
                        logger.info(f"Match-Dauer: {duration_seconds}s ({duration_seconds // 60} Minuten)")
                    except:
                        pass

                logger.info(f"Match gewonnen: {state.winner}")

                # Match in Historie speichern
                state_manager.save_match_to_history(state)
        else:
            # Tie-Break läuft weiter - Aufschlagwechsel nach Tie-Break Regeln
            state.server = game_logic.get_tiebreak_server(state.tiebreak_total_points, state.tiebreak_server_at_start)

    else:
        # Normales Spiel (kein Tie-Break)
        game_winner = game_logic.check_game_won(state.player1_points, state.player2_points, state.game_mode)
        if game_winner:
            # Berechne Game-Dauer
            if state.current_game_start_time:
                try:
                    game_start = datetime.fromisoformat(state.current_game_start_time)
                    game_end = datetime.now()
                    game_duration = int((game_end - game_start).total_seconds())
                    state.game_durations.append(game_duration)
                    logger.info(f"Game-Dauer: {game_duration}s ({game_duration // 60}m {game_duration % 60}s)")
                except:
                    pass

            # Reset Game-Timer
            state.current_game_start_time = datetime.now().isoformat()

            if game_winner == 1:
                state.player1_games += 1
            else:
                state.player2_games += 1

            # Punkte zurücksetzen
            state.player1_points = 0
            state.player2_points = 0

            # Aufschlagwechsel
            state.server = 2 if state.server == 1 else 1

            logger.info(f"Spiel gewonnen: Team {game_winner}")

            # Satz gewonnen?
            set_winner = game_logic.check_set_won(state.player1_games, state.player2_games, state.game_mode)
            if set_winner:
                # Satz-Historie speichern
                state.set_history.append([state.player1_games, state.player2_games])

                if set_winner == 1:
                    state.player1_sets += 1
                else:
                    state.player2_sets += 1

                # Games zurücksetzen
                state.player1_games = 0
                state.player2_games = 0

                logger.info(f"Satz gewonnen: Team {set_winner}")

                # Match gewonnen?
                match_winner = game_logic.check_match_won(state.player1_sets, state.player2_sets, state.sets_to_win)
                if match_winner:
                    state.match_finished = True
                    state.match_end_time = datetime.now().isoformat()
                    state.winner = state.player1_name if match_winner == 1 else state.player2_name

                    # Berechne Match-Dauer
                    if state.match_start_time:
                        try:
                            start = datetime.fromisoformat(state.match_start_time)
                            end = datetime.fromisoformat(state.match_end_time)
                            duration_seconds = int((end - start).total_seconds())
                            logger.info(f"Match-Dauer: {duration_seconds}s ({duration_seconds // 60} Minuten)")
                        except:
                            pass

                    logger.info(f"Match gewonnen: {state.winner}")

                    # Match in Historie speichern
                    state_manager.save_match_to_history(state)

    # Status speichern
    state_manager.save_state(state)

    return state

def get_state_dict(state: MatchState) -> Dict:
    """Erstellt State-Dict mit formatierten Punkteanzeigen für Frontend"""
    # Im Tie-Break: Punkte direkt anzeigen, sonst normale Anzeige
    if state.in_tiebreak:
        score_p1 = str(state.player1_points)
        score_p2 = str(state.player2_points)
    else:
        score_p1, score_p2 = game_logic.get_score_display(
            state.player1_points,
            state.player2_points,
            state.game_mode
        )

    return {
        "team_a_name": state.player1_name,
        "team_b_name": state.player2_name,
        "sets_a": state.player1_sets,
        "sets_b": state.player2_sets,
        "games_a": state.player1_games,
        "games_b": state.player2_games,
        "points_a": state.player1_points,  # Roh-Punkte für Kompatibilität
        "points_b": state.player2_points,  # Roh-Punkte für Kompatibilität
        "points_a_display": score_p1,  # Formatiert (0, 15, 30, 40, AD) oder Tie-Break Punkte
        "points_b_display": score_p2,  # Formatiert (0, 15, 30, 40, AD) oder Tie-Break Punkte
        "serve": "a" if state.server == 1 else "b",
        "current_set": state.player1_sets + state.player2_sets + 1,
        "set_history": state.set_history,
        "match_over": state.match_finished,
        "winner": "a" if state.winner == state.player1_name else "b" if state.match_finished else None,
        "best_of": state.sets_to_win * 2 - 1,
        "game_mode": state.game_mode,
        "in_tiebreak": state.in_tiebreak  # Tie-Break Status für Frontend
    }

# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.get("/", response_class=HTMLResponse)
async def scoreboard(request: Request):
    """Haupt-Scoreboard-Ansicht"""
    state = get_state_dict(current_match)
    return templates.TemplateResponse(request, "index.html", get_template_context(
        request,
        title="Tennis Scoreboard",
        state=state,
        team_a_display=current_match.player1_name,
        team_b_display=current_match.player2_name
    ))

@app.get("/api/match-status")
async def get_match_status():
    """Gibt aktuellen Match-Status zurück"""
    score_p1, score_p2 = game_logic.get_score_display(
        current_match.player1_points,
        current_match.player2_points,
        current_match.game_mode
    )
    
    return {
        "player1": {
            "name": current_match.player1_name,
            "sets": current_match.player1_sets,
            "games": current_match.player1_games,
            "points": score_p1,
            "serving": current_match.server == 1
        },
        "player2": {
            "name": current_match.player2_name,
            "sets": current_match.player2_sets,
            "games": current_match.player2_games,
            "points": score_p2,
            "serving": current_match.server == 2
        },
        "match_finished": current_match.match_finished,
        "winner": current_match.winner
    }

@app.get("/api/stats")
async def get_stats():
    """Gibt detaillierte Match-Statistiken zurück"""
    score_p1, score_p2 = game_logic.get_score_display(
        current_match.player1_points,
        current_match.player2_points,
        current_match.game_mode
    )
    
    statistics = calculate_statistics(current_match) if current_match.match_finished else None
    
    return {
        "current_match": {
            "player1_name": current_match.player1_name,
            "player2_name": current_match.player2_name,
            "player1_sets": current_match.player1_sets,
            "player2_sets": current_match.player2_sets,
            "player1_games": current_match.player1_games,
            "player2_games": current_match.player2_games,
            "player1_points": score_p1,
            "player2_points": score_p2,
            "server": current_match.server,
            "match_finished": current_match.match_finished,
            "winner": current_match.winner,
            "history": current_match.history,
            "set_history": current_match.set_history,
            "game_mode": current_match.game_mode,
            "best_of": current_match.sets_to_win * 2 - 1,
            "game_durations": current_match.game_durations,
            "set_durations": current_match.set_durations,
            "current_game_start_time": current_match.current_game_start_time
        },
        "statistics": statistics,
        "is_deuce": game_logic.check_deuce(current_match.player1_points, current_match.player2_points, current_match.game_mode),
        "advantage": game_logic.check_advantage(current_match.player1_points, current_match.player2_points, current_match.game_mode)
    }

@app.post("/api/point/{player}")
async def add_point_endpoint(player: int):
    """Fügt Punkt für Spieler 1 oder 2 hinzu"""
    global current_match
    
    if player not in [1, 2]:
        raise HTTPException(status_code=400, detail="Player muss 1 oder 2 sein")
    
    current_match = add_point(current_match, player)
    return {"status": "success"}

@app.post("/api/point")
async def add_point_json(request: Request):
    """Fügt Punkt hinzu (JSON Body mit player, team, oder team_a/team_b)"""
    global current_match
    
    try:
        body = await request.json()
        logger.debug(f"/api/point Body: {body}")
        
        # Verschiedene Formate unterstützen
        player = body.get("player") or body.get("team")
        
        if player == "team_a" or player == "a":
            player = 1
        elif player == "team_b" or player == "b":
            player = 2
        
        if player not in [1, 2]:
            raise HTTPException(status_code=400, detail=f"Player muss 1 oder 2 sein (erhalten: {body})")
        
        # Timer beim ersten Punkt starten
        if not current_match.match_started:
            current_match.match_start_time = datetime.now().isoformat()
        
        current_match = add_point(current_match, player)
        
        # State zurückgeben
        return {
            "status": "success",
            "state": get_state_dict(current_match)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Fehler bei /api/point: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/undo")
async def undo_point_endpoint():
    """Macht letzten Punkt rückgängig"""
    global current_match

    # Verwende die vollständige undo_point Funktion
    current_match = undo_point(current_match)

    return {
        "status": "success",
        "state": get_state_dict(current_match)
    }

@app.post("/api/reset")
async def reset_match():
    """Setzt Match zurück"""
    global current_match
    
    current_match = MatchState(
        player1_name=current_match.player1_name,
        player2_name=current_match.player2_name
    )
    state_manager.save_state(current_match)
    
    logger.info("Match zurückgesetzt")
    return {"status": "success"}

@app.post("/api/names")
async def update_names(player1: str, player2: str):
    """Aktualisiert Spielernamen"""
    global current_match
    
    current_match.player1_name = player1
    current_match.player2_name = player2
    state_manager.save_state(current_match)
    
    logger.info(f"Namen aktualisiert: {player1} vs {player2}")
    return {"status": "success"}

@app.post("/api/settings/teams")
async def update_teams(request: Request):
    """Aktualisiert Team-Namen (JSON Body mit team_a und team_b)"""
    global current_match
    
    try:
        body = await request.json()
        team_a = body.get("team_a_name", body.get("team_a", body.get("player1")))
        team_b = body.get("team_b_name", body.get("team_b", body.get("player2")))
        
        if team_a:
            current_match.player1_name = team_a
        if team_b:
            current_match.player2_name = team_b
        
        state_manager.save_state(current_match)
        
        logger.info(f"Teams aktualisiert: {current_match.player1_name} vs {current_match.player2_name}")
        
        return {
            "status": "success",
            "state": get_state_dict(current_match)
        }
    except Exception as e:
        logger.error(f"Fehler bei /api/settings/teams: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/serve/{player}")
async def set_server(player: int):
    """Setzt den Aufschläger"""
    global current_match
    
    if player not in [1, 2]:
        raise HTTPException(status_code=400, detail="Player muss 1 oder 2 sein")
    
    current_match.server = player
    state_manager.save_state(current_match)
    
    return {"status": "success"}

@app.post("/api/settings/serve")
async def set_server_json(request: Request):
    """Setzt den Aufschläger (JSON Body mit team) oder togglet bei leerem Body"""
    global current_match
    
    try:
        body = await request.json() if request.headers.get("content-length") and int(request.headers.get("content-length")) > 0 else {}
        logger.debug(f"/api/settings/serve Body: {body}")
        
        team = body.get("team") or body.get("player")
        
        # Wenn kein team angegeben, toggle
        if not team:
            current_match.server = 2 if current_match.server == 1 else 1
        else:
            if team == "team_a" or team == "a":
                team = 1
            elif team == "team_b" or team == "b":
                team = 2
            
            if team not in [1, 2]:
                raise HTTPException(status_code=400, detail=f"Team muss 1 oder 2 sein (erhalten: {body})")
            
            current_match.server = team
        
        state_manager.save_state(current_match)
        
        logger.info(f"Aufschläger gesetzt: Team {current_match.server}")
        
        return {
            "status": "success",
            "state": get_state_dict(current_match)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Fehler bei /api/settings/serve: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/state")
async def get_state():
    """Gibt vollständigen Match-State zurück"""
    return {
        "state": get_state_dict(current_match)
    }

@app.get("/api/game-modes")
async def get_game_modes():
    """Gibt Liste verfügbarer Spielmodi mit vollständigen Regeln zurück"""
    return [
        {"id": mode_id, **mode}
        for mode_id, mode in game_mode_manager.modes.items()
    ]

@app.get("/api/game-modes/{mode_id}")
async def get_game_mode(mode_id: str):
    """Gibt einzelnen Spielmodus nach ID zurück"""
    mode = game_mode_manager.get_mode(mode_id)
    if not mode:
        raise HTTPException(status_code=404, detail=f"Spielmodus '{mode_id}' nicht gefunden")
    return {"id": mode_id, **mode}

@app.post("/api/game-modes")
async def create_or_update_game_mode(payload: GameModePayload):
    """Speichert benutzerdefinierten Spielmodus (Upsert)"""
    mode_data = {
        "name": payload.name,
        "description": payload.description,
        "is_custom": payload.is_custom,
        "rules": payload.rules.dict(),
    }
    game_mode_manager.save_mode(payload.id, mode_data)
    return {"status": "ok", "id": payload.id}

@app.delete("/api/game-modes/{mode_id}")
async def delete_game_mode(mode_id: str):
    """Löscht benutzerdefinierten Spielmodus"""
    if not game_mode_manager.delete_mode(mode_id):
        raise HTTPException(status_code=404, detail=f"Spielmodus '{mode_id}' nicht gefunden")
    return {"status": "ok", "id": mode_id}

@app.post("/api/settings/game-mode")
async def update_game_mode(request: Request):
    """Aktualisiert Spielmodus"""
    global current_match
    
    try:
        body = await request.json()
        game_mode = body.get("game_mode")
        
        if not game_mode:
            raise HTTPException(status_code=400, detail="game_mode erforderlich")
        
        # Prüfen ob Spielmodus existiert
        if not game_mode_manager.get_mode(game_mode):
            raise HTTPException(status_code=400, detail=f"Spielmodus '{game_mode}' nicht gefunden")
        
        current_match.game_mode = game_mode
        state_manager.save_state(current_match)
        
        logger.info(f"Spielmodus aktualisiert: {game_mode}")
        
        return {
            "status": "success",
            "state": get_state_dict(current_match)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Fehler bei /api/settings/game-mode: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/settings/best-of")
async def update_best_of(request: Request):
    """Aktualisiert Best-of-Einstellung"""
    global current_match
    
    try:
        body = await request.json()
        best_of = body.get("best_of")
        
        if best_of not in [1, 3, 5]:
            raise HTTPException(status_code=400, detail="best_of muss 1, 3 oder 5 sein")
        
        # Berechne sets_to_win
        sets_to_win = (best_of + 1) // 2
        current_match.sets_to_win = sets_to_win
        state_manager.save_state(current_match)
        
        logger.info(f"Best-of aktualisiert: {best_of} (sets_to_win: {sets_to_win})")
        
        return {
            "status": "success",
            "state": get_state_dict(current_match)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Fehler bei /api/settings/best-of: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/new-match")
async def new_match():
    """Erstellt neues Match mit gleichen Einstellungen"""
    global current_match

    # Speichere Einstellungen
    player1_name = current_match.player1_name
    player2_name = current_match.player2_name
    game_mode = current_match.game_mode
    sets_to_win = current_match.sets_to_win

    # Neues Match erstellen
    current_match = MatchState(
        player1_name=player1_name,
        player2_name=player2_name,
        game_mode=game_mode,
        sets_to_win=sets_to_win
    )
    state_manager.save_state(current_match)

    logger.info(f"Neues Match erstellt: {player1_name} vs {player2_name} (Modus: {game_mode}, Best-of: {sets_to_win*2-1})")

    return {
        "status": "success",
        "state": get_state_dict(current_match)
    }

@app.post("/api/match/save-to-history")
async def save_running_match_to_history():
    """
    Speichert ein laufendes Match in die Historie und beendet es.

    Ermittelt den Gewinner anhand der aktuellen Punktestände:
    - Wenn ein Spieler mehr Sätze gewonnen hat → Gewinner
    - Bei gleicher Satzanzahl: Wer mehr Games hat → Gewinner
    - Bei gleicher Game-Anzahl: Wer mehr Punkte im aktuellen Game hat → Gewinner
    - Ansonsten: Unentschieden
    """
    global current_match

    # Prüfe ob Match bereits beendet ist
    if current_match.match_finished:
        logger.warning("Match ist bereits beendet")
        return {
            "status": "error",
            "message": "Match ist bereits beendet"
        }

    # Prüfe ob Match überhaupt gestartet wurde
    if not current_match.match_started:
        logger.warning("Match wurde noch nicht gestartet")
        return {
            "status": "error",
            "message": "Match wurde noch nicht gestartet"
        }

    # Ermittle Gewinner oder Unentschieden
    winner = None
    winner_name = None

    # 1. Vergleiche Sätze
    if current_match.player1_sets > current_match.player2_sets:
        winner = 1
        winner_name = current_match.player1_name
    elif current_match.player2_sets > current_match.player1_sets:
        winner = 2
        winner_name = current_match.player2_name
    # 2. Bei gleichen Sätzen: Vergleiche Games
    elif current_match.player1_games > current_match.player2_games:
        winner = 1
        winner_name = current_match.player1_name
    elif current_match.player2_games > current_match.player1_games:
        winner = 2
        winner_name = current_match.player2_name
    # 3. Bei gleichen Games: Vergleiche Punkte im aktuellen Game
    elif current_match.player1_points > current_match.player2_points:
        winner = 1
        winner_name = current_match.player1_name
    elif current_match.player2_points > current_match.player1_points:
        winner = 2
        winner_name = current_match.player2_name
    else:
        # Unentschieden
        winner_name = "Unentschieden"

    # Speichere aktuellen Satzstand in set_history falls noch nicht vorhanden
    # (bei laufendem Satz)
    if current_match.player1_games > 0 or current_match.player2_games > 0:
        # Füge aktuellen Satzstand hinzu
        current_match.set_history.append([current_match.player1_games, current_match.player2_games])

    # Match als beendet markieren
    current_match.match_finished = True
    current_match.match_end_time = datetime.now().isoformat()
    current_match.winner = winner_name

    # In Historie speichern
    state_manager.save_match_to_history(current_match)

    # Status speichern
    state_manager.save_state(current_match)

    logger.info(f"Laufendes Match in Historie gespeichert - Gewinner: {winner_name} ({current_match.player1_sets}:{current_match.player2_sets} Sätze, {current_match.player1_games}:{current_match.player2_games} Games)")

    return {
        "status": "success",
        "message": f"Match in Historie gespeichert",
        "winner": winner_name,
        "final_score": {
            "sets": f"{current_match.player1_sets}:{current_match.player2_sets}",
            "games": f"{current_match.player1_games}:{current_match.player2_games}",
            "points": f"{current_match.player1_points}:{current_match.player2_points}"
        },
        "state": get_state_dict(current_match)
    }

@app.post("/api/match/duration")
async def update_match_duration(request: Request):
    """
    Speichert die Match-Dauer wenn ein Match beendet wurde.
    
    Body: {
        "duration_seconds": 1234,
        "match_start_time": "2025-12-25T10:00:00Z",
        "match_end_time": "2025-12-25T10:20:34Z"
    }
    """
    global current_match
    
    try:
        body = await request.json()
        
        duration_seconds = body.get("duration_seconds", 0)
        match_start_time = body.get("match_start_time")
        match_end_time = body.get("match_end_time")
        
        # Speichere Timing-Infos im aktuellen Match
        if match_start_time:
            current_match.match_start_time = match_start_time
        if match_end_time:
            current_match.match_end_time = match_end_time
        
        state_manager.save_state(current_match)
        
        logger.info(f"Match-Dauer gespeichert: {duration_seconds}s")
        
        return {
            "status": "ok",
            "message": "Match-Dauer gespeichert",
            "duration_seconds": duration_seconds
        }
    except Exception as e:
        logger.error(f"Fehler bei /api/match/duration: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/game-stats")
async def get_game_stats():
    """Gibt detaillierte Game-by-Game Statistiken zurück"""
    if not current_match.game_durations:
        return {"games": []}
    
    games = []
    for i, duration in enumerate(current_match.game_durations):
        games.append({
            "game_number": i + 1,
            "duration_seconds": duration,
            "duration_formatted": f"{duration // 60}m {duration % 60}s"
        })
    
    return {
        "total_games": len(current_match.game_durations),
        "games": games,
        "average_game_duration": sum(current_match.game_durations) // len(current_match.game_durations) if current_match.game_durations else 0,
        "longest_game": max(current_match.game_durations) if current_match.game_durations else 0,
        "shortest_game": min(current_match.game_durations) if current_match.game_durations else 0
    }

# ============================================================================
# WEBCAM ENDPOINTS
# ============================================================================

@app.get("/webcam", response_class=HTMLResponse)
async def webcam_page(request: Request):
    """Webcam-Steuerungs-Seite"""
    return templates.TemplateResponse(request, "webcam.html", get_template_context(
        request,
        title="Webcam Steuerung"
    ))

@app.get("/webcam/stream")
async def webcam_stream():
    """MJPEG-Stream für Webcam"""
    async def generate():
        frame_count = 0
        logger.info("[Stream] Client connected to webcam stream")
        
        while True:
            frame = gesture_recognizer.get_latest_frame()
            if frame is not None:
                # JPEG-Qualität stark reduzieren für bessere Performance
                _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 50])
                frame_count += 1
                if frame_count == 1:
                    logger.info("[Stream] First frame sent to client")
                if frame_count % 100 == 0:
                    logger.info(f"[Stream] Sent {frame_count} frames")
                
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n'
                       b'Content-Length: ' + str(len(buffer)).encode() + b'\r\n\r\n' + 
                       buffer.tobytes() + b'\r\n')
                
                # Kurze Pause zwischen Frames (wichtig für Buffer-Control)
                await asyncio.sleep(0.1)  # 10 FPS
            else:
                await asyncio.sleep(0.05)
    
    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0',
            'Connection': 'close'
        }
    )

@app.get("/api/webcam/settings")
async def get_webcam_settings():
    """Gibt Webcam-Einstellungen zurück"""
    return webcam_settings_manager.settings

@app.get("/api/webcam/last-gesture")
async def get_last_gesture():
    """Gibt letzte erkannte Geste zurück"""
    return {
        "gesture": gesture_recognizer.last_gesture,
        "timestamp": gesture_recognizer.last_gesture_timestamp
    }

@app.post("/api/webcam/settings")
async def update_webcam_settings(settings: WebcamSettings):
    """Aktualisiert Webcam-Einstellungen"""
    old = webcam_settings_manager.settings
    webcam_settings_manager.save_settings(settings)

    # Kamera nur neu starten wenn sich kamera-relevante Parameter geändert haben
    camera_changed = (
        old.enabled != settings.enabled or
        old.width != settings.width or
        old.height != settings.height or
        old.fps != settings.fps or
        old.camera_index != settings.camera_index
    )
    if camera_changed:
        gesture_recognizer.stop()
        if settings.enabled:
            gesture_recognizer.start()

    return {"status": "success"}

@app.post("/api/webcam/roi")
async def save_webcam_roi(data: dict):
    """Speichert ROI (Region of Interest) für Webcam"""
    roi_points = data.get('roi', [])
    
    # Lade aktuelle Einstellungen
    settings = webcam_settings_manager.settings
    
    # ROI in Settings speichern (falls WebcamSettings roi_polygon hat)
    # Für jetzt speichern wir es separat in der JSON
    settings_dict = settings.dict()
    settings_dict['roi_polygon'] = roi_points
    
    # Speichern
    try:
        with open(webcam_settings_manager.settings_file, 'w') as f:
            json.dump(settings_dict, f, indent=2)
        logger.info(f"ROI gespeichert: {len(roi_points)} Punkte")
        return {"status": "success", "message": "ROI gespeichert"}
    except Exception as e:
        logger.error(f"Fehler beim Speichern der ROI: {e}")
        return {"status": "error", "message": str(e)}

# ============================================================================
# STATISTICS & HISTORY
# ============================================================================

@app.get("/stats", response_class=HTMLResponse)
async def stats_page(request: Request):
    """Statistik-Seite"""
    return templates.TemplateResponse(request, "stats.html", get_template_context(
        request,
        title="Statistiken"
    ))

@app.get("/api/history")
async def get_history():
    """Gibt Match-Historie zurück (iOS-optimiert: ohne Point-Historie)"""
    try:
        history = []
        if state_manager.history_file.exists():
            with open(state_manager.history_file, 'r', encoding='utf-8') as f:
                history = json.load(f)
        
        # iOS-OPTIMIERUNG: Entferne riesige history-Arrays
        for match in history:
            if 'history' in match:
                history_length = len(match.get('history', []))
                del match['history']
                logger.info(f"📱 Entfernt history-Array mit {history_length} Einträgen")
        
        # Füge IDs hinzu falls nicht vorhanden
        for i, match in enumerate(history):
            if 'id' not in match:
                match['id'] = f"match_{i}_{match.get('match_end_time', '')}"
        
        logger.info(f"📱 Sende {len(history)} Matches an iOS (ohne Point-Historie)")
        return {"matches": history}
    except Exception as e:
        logger.error(f"Fehler beim Laden der Historie: {e}")
        return {"matches": []}

@app.delete("/api/history/{match_id:path}")
async def delete_match(match_id: str):
    """
    Löscht ein Match aus der Historie (flexibles Matching)

    Unterstützt verschiedene ID-Formate:
    - match_0_2026-01-27T20:32:53.116362
    - match_0_2026-01-27T20%3A32%3A53.116362 (URL-encoded)
    - Numerischer Index (0, 1, 2, ...)
    """
    try:
        if not state_manager.history_file.exists():
            raise HTTPException(status_code=404, detail="Keine Historie gefunden")

        with open(state_manager.history_file, 'r', encoding='utf-8') as f:
            history = json.load(f)

        if len(history) == 0:
            raise HTTPException(status_code=404, detail="Historie ist leer")

        # URL-Decode der match_id (für %3A → : etc.)
        from urllib.parse import unquote
        decoded_match_id = unquote(match_id)

        logger.info(f"🔍 Versuche Match zu löschen:")
        logger.info(f"   Original ID: '{match_id}'")
        logger.info(f"   Decoded ID:  '{decoded_match_id}'")
        logger.info(f"   Historie hat {len(history)} Matches")

        # Strategie 1: Versuche numerischen Index
        try:
            index = int(match_id)
            if 0 <= index < len(history):
                deleted_match = history.pop(index)
                logger.info(f"✅ Match gelöscht via Index {index}: {deleted_match.get('player1_name', 'Team A')} vs {deleted_match.get('player2_name', 'Team B')}")

                with open(state_manager.history_file, 'w', encoding='utf-8') as f:
                    json.dump(history, f, indent=2, ensure_ascii=False)

                return {
                    "status": "success",
                    "message": f"Match {index} gelöscht",
                    "deleted_match": deleted_match
                }
        except ValueError:
            # Keine Nummer, weitermachen mit anderen Strategien
            pass

        # Strategie 2: Matche gegen generierte IDs oder explizite 'id' Felder
        new_history = []
        found = False
        deleted_match = None

        for i, match in enumerate(history):
            # Generiere ID wie iOS es macht
            timestamp = match.get('match_end_time') or match.get('timestamp', '')
            generated_id = f"match_{i}_{timestamp}"

            # Hole explizite ID falls vorhanden
            explicit_id = match.get('id', '')

            logger.debug(f"   Match {i}:")
            logger.debug(f"      Generated ID: '{generated_id}'")
            logger.debug(f"      Explicit ID:  '{explicit_id}'")
            logger.debug(f"      Timestamp:    '{timestamp}'")

            # Matche gegen verschiedene Varianten
            if (decoded_match_id == generated_id or
                decoded_match_id == explicit_id or
                match_id == generated_id or
                match_id == explicit_id or
                # Fallback: Nur Timestamp-Teil matchen
                timestamp in decoded_match_id):

                found = True
                deleted_match = match
                logger.info(f"✅ Match gefunden via ID-Match!")
                logger.info(f"   {match.get('player1_name', 'Team A')} vs {match.get('player2_name', 'Team B')}")
                continue  # Überspringe dieses Match (= lösche es)

            new_history.append(match)

        if not found:
            logger.warning(f"❌ Match nicht gefunden: '{decoded_match_id}'")
            raise HTTPException(status_code=404, detail="Match nicht gefunden")

        # Speichere aktualisierte Historie
        with open(state_manager.history_file, 'w', encoding='utf-8') as f:
            json.dump(new_history, f, indent=2, ensure_ascii=False)

        logger.info(f"✅ Match erfolgreich gelöscht. Verbleibende Matches: {len(new_history)}")

        return {
            "status": "success",
            "message": "Match gelöscht",
            "deleted_match": deleted_match,
            "remaining_matches": len(new_history)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Fehler beim Löschen: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/history")
async def clear_history():
    """Löscht KOMPLETTE Match-Historie (alle Matches)"""
    try:
        if not state_manager.history_file.exists():
            logger.warning("Historie-Datei existiert nicht")
            return {
                "status": "success",
                "message": "Historie war bereits leer",
                "deleted_count": 0
            }

        # Zähle Matches vor dem Löschen
        with open(state_manager.history_file, 'r', encoding='utf-8') as f:
            history = json.load(f)

        match_count = len(history)

        # Lösche Historie-Datei
        state_manager.history_file.unlink()

        logger.info(f"✅ Komplette Match-Historie gelöscht ({match_count} Matches)")

        return {
            "status": "success",
            "message": f"Alle {match_count} Matches gelöscht",
            "deleted_count": match_count
        }

    except Exception as e:
        logger.error(f"❌ Fehler beim Löschen der Historie: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# SETTINGS & ADMIN
# ============================================================================

@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    """Einstellungs-Seite"""
    return templates.TemplateResponse(request, "settings.html", get_template_context(
        request,
        title="Einstellungen"
    ))

@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    """Admin-Panel"""
    return templates.TemplateResponse(request, "admin.html", get_template_context(
        request,
        title="Admin Panel"
    ))

@app.get("/poweroff.jpg")
async def get_poweroff_image():
    """Liefert poweroff.jpg aus"""
    from fastapi.responses import FileResponse
    project_dir = Path(__file__).resolve().parent
    image_path = project_dir / "poweroff.jpg"
    
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="poweroff.jpg nicht gefunden")
    
    return FileResponse(image_path, media_type="image/jpeg")

@app.post("/api/system/shutdown")
async def system_shutdown():
    """Fährt das System herunter - ruft shutdown_helper.py auf"""
    try:
        project_dir = Path(__file__).resolve().parent
        shutdown_script = project_dir / "shutdown_helper.py"
        
        if not shutdown_script.exists():
            raise HTTPException(status_code=500, detail="shutdown_helper.py nicht gefunden")
        
        logger.info("System-Shutdown wurde angefordert...")
        
        # shutdown_helper.py im Hintergrund starten
        subprocess.Popen(
            ["python3", str(shutdown_script)],
            cwd=str(project_dir),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        
        return {"status": "shutdown_initiated", "message": "System wird heruntergefahren..."}
        
    except Exception as e:
        logger.error(f"Fehler beim Herunterfahren: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/wifi-status")
async def get_wifi_status():
    """Gibt WLAN Access Point Status zurück"""
    try:
        import platform
        
        # Lade gespeicherte Einstellungen
        settings = wifi_ap_manager.settings
        
        # Prüfe ob wir auf Raspberry Pi sind
        is_raspberry_pi = platform.machine() in ['armv7l', 'aarch64']
        
        if is_raspberry_pi:
            # Prüfe hostapd Status
            try:
                result = subprocess.run(
                    ["systemctl", "is-active", "hostapd"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                hostapd_active = result.stdout.strip() == "active"
            except:
                hostapd_active = False
            
            # Hole SSID und Passwort aus hostapd config falls vorhanden
            ssid = settings.ssid
            password = settings.password
            try:
                with open('/etc/hostapd/hostapd.conf', 'r') as f:
                    config = f.read()
                    for line in config.split('\n'):
                        if line.startswith('ssid='):
                            ssid = line.split('=', 1)[1].strip()
                        elif line.startswith('wpa_passphrase='):
                            password = line.split('=', 1)[1].strip()
            except:
                pass
            
            return {
                "active": hostapd_active,
                "ssid": ssid,
                "password": password,
                "ip": "10.20.1.1",
                "enabled": settings.enabled,
                "config_exists": True,
                "hostapd_status": "active" if hostapd_active else "inactive"
            }
        else:
            # Nicht auf Raspberry Pi - gebe gespeicherte Einstellungen zurück
            return {
                "active": False,
                "ssid": settings.ssid,
                "password": settings.password,
                "ip": "10.20.1.1",
                "enabled": settings.enabled,
                "config_exists": True,
                "hostapd_status": "not-available (not on Raspberry Pi)"
            }
    except Exception as e:
        logger.error(f"Fehler beim Abrufen des WiFi AP Status: {e}")
        return {
            "active": False,
            "ssid": "openPadel",
            "password": "openPadel",
            "ip": "10.20.1.1",
            "enabled": False,
            "config_exists": False,
            "error": str(e)
        }

@app.get("/api/system-uptime")
async def get_system_uptime():
    """Gibt Server-Uptime zurück"""
    uptime_seconds = int((datetime.now() - server_start_time).total_seconds())
    hours = uptime_seconds // 3600
    minutes = (uptime_seconds % 3600) // 60
    seconds = uptime_seconds % 60

    return {
        "uptime_seconds": uptime_seconds,
        "uptime_formatted": f"{hours}h {minutes}m {seconds}s"
    }

@app.get("/api/logs")
async def get_logs(lines: int = 100):
    """Gibt die letzten N Zeilen der Log-Datei zurück"""
    try:
        log_file = Path("openpadel.log")
        if not log_file.exists():
            return {
                "status": "error",
                "message": "Log-Datei existiert nicht",
                "logs": []
            }

        with open(log_file, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()
            last_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines

        return {
            "status": "success",
            "logs": [line.rstrip('\n') for line in last_lines],
            "total_lines": len(all_lines),
            "returned_lines": len(last_lines)
        }
    except Exception as e:
        logger.error(f"Fehler beim Lesen der Log-Datei: {e}")
        return {
            "status": "error",
            "message": str(e),
            "logs": []
        }

@app.get("/api/wifi-ap/settings")
async def get_wifi_ap_settings():
    """Gibt WiFi AP Einstellungen zurück"""
    return wifi_ap_manager.settings

@app.get("/api/wifi-ap/clients")
async def get_wifi_ap_clients():
    """Gibt die Anzahl der verbundenen WiFi-Clients zurück"""
    try:
        import platform
        if platform.machine() in ['armv7l', 'aarch64']:  # Raspberry Pi
            # Versuche die verbundenen Clients über iw zu ermitteln
            result = subprocess.run(['sudo', 'iw', 'dev', 'wlan0', 'station', 'dump'],
                                  capture_output=True, text=True, check=False)

            if result.returncode == 0:
                # Zähle die Anzahl der "Station" Einträge
                client_count = result.stdout.count('Station ')
                return {
                    "count": client_count,
                    "clients": client_count
                }
            else:
                logger.warning(f"Fehler beim Abrufen der Client-Informationen: {result.stderr}")
                return {"count": 0, "clients": 0, "error": "Could not retrieve client information"}
        else:
            # Auf Nicht-Raspberry Pi Systemen
            return {"count": 0, "clients": 0, "note": "Not running on Raspberry Pi"}
    except Exception as e:
        logger.error(f"Fehler beim Abrufen der WiFi-Clients: {e}")
        return {"count": 0, "clients": 0, "error": str(e)}

@app.post("/api/wifi-ap/settings")
async def update_wifi_ap_settings(settings: WiFiAPSettings):
    """Aktualisiert WiFi AP Einstellungen in bestehender hostapd.conf"""
    wifi_ap_manager.save_settings(settings)
    logger.info(f"WiFi AP Einstellungen aktualisiert: SSID={settings.ssid}")
    
    # Aktualisiere bestehende hostapd.conf (nur auf Raspberry Pi)
    try:
        import platform
        if platform.machine() in ['armv7l', 'aarch64']:  # Raspberry Pi
            hostapd_conf_path = '/etc/hostapd/hostapd.conf'
            
            # Prüfe ob Config existiert
            if not Path(hostapd_conf_path).exists():
                logger.warning(f"{hostapd_conf_path} existiert nicht. Bitte zuerst install_ap.sh ausführen.")
                return {"status": "error", "message": "hostapd.conf nicht gefunden. Bitte zuerst install_ap.sh ausführen."}
            
            try:
                # Lese bestehende Config
                with open(hostapd_conf_path, 'r') as f:
                    lines = f.readlines()
                
                # Aktualisiere nur ssid und wpa_passphrase Zeilen
                updated_lines = []
                for line in lines:
                    stripped = line.strip()
                    if stripped.startswith('ssid='):
                        updated_lines.append(f'ssid={settings.ssid}\n')
                        logger.debug(f"SSID aktualisiert: {settings.ssid}")
                    elif stripped.startswith('wpa_passphrase='):
                        updated_lines.append(f'wpa_passphrase={settings.password}\n')
                        logger.debug("Passwort aktualisiert")
                    else:
                        updated_lines.append(line)
                
                # Backup erstellen
                subprocess.run(['sudo', 'cp', hostapd_conf_path, f'{hostapd_conf_path}.backup'], check=False)
                
                # Neue Config schreiben
                with open('/tmp/hostapd.conf.new', 'w') as f:
                    f.writelines(updated_lines)
                
                subprocess.run(['sudo', 'mv', '/tmp/hostapd.conf.new', hostapd_conf_path], check=True)
                subprocess.run(['sudo', 'chmod', '600', hostapd_conf_path], check=True)
                
                logger.info("hostapd.conf wurde aktualisiert (bestehende Config beibehalten)")
                
                # Stoppe hostapd sauber
                subprocess.run(['sudo', 'systemctl', 'stop', 'hostapd'], check=False)
                await asyncio.sleep(1)
                
                # Starte hostapd neu (mit start statt restart für sauberen Neustart)
                result = subprocess.run(['sudo', 'systemctl', 'start', 'hostapd'], 
                                      capture_output=True, text=True, check=False)
                
                if result.returncode == 0:
                    logger.info("hostapd erfolgreich gestartet")
                else:
                    logger.error(f"hostapd start fehlgeschlagen: {result.stderr}")
                
                # Warte kurz und prüfe Status
                await asyncio.sleep(2)
                status_result = subprocess.run(['sudo', 'systemctl', 'is-active', 'hostapd'],
                                             capture_output=True, text=True, check=False)
                
                if status_result.stdout.strip() == 'active':
                    logger.info("hostapd läuft")
                else:
                    logger.warning(f"hostapd läuft nicht! Status: {status_result.stdout.strip()}")
                
                # Lade Einstellungen neu aus hostapd.conf
                wifi_ap_manager.reload_from_hostapd()
                
                return {"status": "success", "message": f"WiFi AP auf '{settings.ssid}' aktualisiert. Bitte neu verbinden!"}
            except PermissionError:
                logger.warning("Keine Berechtigung zum Aktualisieren von hostapd.conf")
                return {"status": "error", "message": "Keine Berechtigung. Server muss als root laufen oder sudo erlauben."}
            except Exception as e:
                logger.warning(f"Fehler beim Aktualisieren von hostapd: {e}")
                return {"status": "error", "message": f"Fehler: {str(e)}"}
    except Exception as e:
        logger.debug(f"Nicht auf Raspberry Pi oder Fehler: {e}")
    
    return {"status": "success", "message": "WiFi AP Einstellungen gespeichert."}

@app.post("/api/wifi-ap/restart")
async def restart_wifi_ap():
    """Startet WiFi Access Point neu"""
    try:
        import platform
        if platform.machine() in ['armv7l', 'aarch64']:  # Raspberry Pi
            logger.info("Starte WiFi Access Point neu...")
            
            # Stoppe Services
            subprocess.run(['sudo', 'systemctl', 'stop', 'hostapd'], check=False)
            subprocess.run(['sudo', 'systemctl', 'stop', 'dnsmasq'], check=False)
            
            # Warte kurz
            await asyncio.sleep(2)
            
            # Starte Services neu
            subprocess.run(['sudo', 'systemctl', 'start', 'dnsmasq'], check=False)
            await asyncio.sleep(1)
            subprocess.run(['sudo', 'systemctl', 'start', 'hostapd'], check=False)
            
            logger.info("WiFi Access Point wurde neu gestartet")
            return {"status": "success", "message": "WiFi Access Point wurde neu gestartet"}
        else:
            return {"status": "info", "message": "Nur auf Raspberry Pi verfügbar"}
    except Exception as e:
        logger.error(f"Fehler beim Neustart des Access Points: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/api/language")
async def get_language():
    """Gibt aktuelle Sprache und verfügbare Sprachen zurück"""
    return {
        "current": language_manager.current_language,
        "available": language_manager.AVAILABLE_LANGUAGES
    }

@app.post("/api/language")
async def set_language(data: dict):
    """Setzt aktuelle Sprache"""
    language = data.get('language', 'en')
    success = language_manager.save_language(language)
    
    if success:
        return {"status": "success", "language": language}
    else:
        raise HTTPException(status_code=400, detail="Invalid language")

@app.get("/api/translations")
async def get_translations():
    """Gibt alle Übersetzungen für aktuelle Sprache zurück"""
    return language_manager.load_translations()

@app.post("/api/poweroff")
async def poweroff():
    """Fährt System herunter (nur auf Raspberry Pi)"""
    try:
        logger.warning("System-Shutdown initiiert!")
        subprocess.Popen(["sudo", "shutdown", "-h", "now"])
        return {"status": "shutting down"}
    except Exception as e:
        logger.error(f"Fehler beim Herunterfahren: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# STARTUP & SHUTDOWN
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialisierung beim Start"""
    logger.info("=" * 60)
    logger.info("Tennis Scoring System startet...")
    logger.info("=" * 60)
    
    # Webcam starten, falls aktiviert
    if webcam_settings_manager.settings.enabled:
        gesture_recognizer.start()

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup beim Beenden"""
    logger.info("System wird heruntergefahren...")
    gesture_recognizer.stop()

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info"
    )
