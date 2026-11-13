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
import hashlib
import os
import re
import signal
import uuid

import updater

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
# SHARED HELPERS
# ============================================================================

# Game-Dauern über 40 Minuten gelten als Messfehler (gleiche Grenze wie die App)
MAX_GAME_DURATION_SECONDS = 40 * 60

# Punkte kommen aus dem Event-Loop UND aus dem Gesten-Thread
match_lock = threading.RLock()

def new_match_id() -> str:
    """Stabile, eindeutige Match-ID (nie rein numerisch)"""
    return f"m_{uuid.uuid4().hex[:16]}"

def write_json_atomic(path: Path, data):
    """Schreibt JSON atomar - ein Stromausfall zerstört die Datei nicht."""
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)

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
    winner_team: Optional[int] = None  # 1/2, None = offen oder Unentschieden
    match_id: Optional[str] = None  # stabil ab dem ersten Punkt
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
    icon_key: Optional[str] = None  # Material-Codepoint oder Emoji (wie in der App)
    # Zeitpunkt der letzten Änderung in ms, von der Uhr des Geräts, das den
    # Modus bearbeitet hat (App oder Browser) - die Pi-Uhr ist ohne Internet
    # nicht verlässlich. Beim Sync gewinnt die neuere Fassung.
    updated_at: Optional[int] = None
    rules: GameModeRules

# Mitgelieferte Spielmodi: weder bearbeitbar noch löschbar (wie in der App)
FIXED_GAME_MODE_IDS = frozenset({
    "mit_vorteil_tiebreak",
    "ohne_vorteil_tiebreak",
    "mit_vorteil_ohne_tiebreak",
    "kurz_set",
})
DEFAULT_GAME_MODE_ID = "mit_vorteil_tiebreak"
# Die ID wird als Dateiname in game_modes/ verwendet
GAME_MODE_ID_PATTERN = re.compile(r"^[a-z0-9_]{1,64}$")

# ============================================================================
# GAME LOGIC
# ============================================================================

class GameModeManager:
    """Verwaltet verfügbare Spielmodi"""
    
    def __init__(self, modes_dir: Path = Path("game_modes"),
                 deleted_file: Path = Path("data") / "deleted_game_modes.json"):
        self.modes_dir = modes_dir
        self.modes_dir.mkdir(exist_ok=True)
        self.modes = self.load_modes()
        # Löschmarken {id: Zeitpunkt in ms}: ohne sie würde eine App, die einen
        # gelöschten Modus noch kennt, ihn beim nächsten Sync wieder anlegen.
        self.deleted_file = deleted_file
        self.deleted: Dict[str, int] = self._load_deleted()

    def _load_deleted(self) -> Dict[str, int]:
        try:
            with open(self.deleted_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return {str(k): int(v) for k, v in data.items()} if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_deleted(self):
        try:
            self.deleted_file.parent.mkdir(exist_ok=True)
            write_json_atomic(self.deleted_file, self.deleted)
        except Exception as e:
            logger.error(f"Löschmarken konnten nicht gespeichert werden: {e}")

    def mark_deleted(self, mode_id: str, deleted_at: int):
        self.deleted[mode_id] = max(self.deleted.get(mode_id, 0), int(deleted_at))
        self._save_deleted()

    def clear_deleted(self, mode_id: str):
        if self.deleted.pop(mode_id, None) is not None:
            self._save_deleted()
    
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
    
    def uses_advantage(self, mode_id: str) -> bool:
        """Vorteil-Regel aktiv? (Golden Point / No-Ad = nächster Punkt entscheidet)"""
        mode = self.game_mode_manager.get_mode(mode_id)
        if not mode:
            return True
        rules = mode.get("rules", {})
        return bool(rules.get("advantage", True)) and not rules.get("golden_point", False)

    def tiebreak_at(self, mode_id: str) -> List[int]:
        """Spielstand, bei dem der Tie-Break beginnt (Standard 6:6)"""
        mode = self.game_mode_manager.get_mode(mode_id)
        if not mode:
            return [6, 6]
        value = mode.get("rules", {}).get("tiebreak_at_games")
        if isinstance(value, list) and len(value) == 2:
            return value
        # Wie in der App: ohne gültigen Spielstand gibt es keinen Tie-Break
        return [-1, -1]

    def get_score_display(self, p1_points: int, p2_points: int, mode_id: str = "mit_vorteil_tiebreak") -> Tuple[str, str]:
        """
        Gibt die Anzeige-Strings für beide Spieler zurück
        Behandelt Deuce, Advantage, etc.
        """
        advantage = self.uses_advantage(mode_id)
        
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
        advantage = self.uses_advantage(mode_id)
        
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
            tiebreak_at = self.tiebreak_at(mode_id)
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
        advantage = self.uses_advantage(mode_id)
        
        if advantage:
            return p1_points >= 3 and p2_points >= 3 and p1_points == p2_points
        else:
            return False
    
    def check_advantage(self, p1_points: int, p2_points: int, mode_id: str = "mit_vorteil_tiebreak") -> Optional[int]:
        """
        Prüft, ob ein Spieler Advantage hat
        Returns: 1 für Spieler 1, 2 für Spieler 2, None wenn kein Advantage
        """
        advantage = self.uses_advantage(mode_id)

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

        tiebreak_at = self.tiebreak_at(mode_id)
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
            # Die App speichert "tiebreak_points_to_win", die Standard-Modi
            # "tiebreak_points" - beide akzeptieren.
            tiebreak_points = (rules.get("tiebreak_points_to_win")
                               or rules.get("tiebreak_points") or 7)
            min_diff = rules.get("tiebreak_minimum_difference") or 2
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
        self._history_lock = threading.RLock()
    
    def save_state(self, state: MatchState):
        """Speichert aktuellen Match-Status"""
        try:
            write_json_atomic(self.state_file, state.dict())
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

    # ------------------------------------------------------------------
    # Match-Historie (Liste von Dicts, älteste zuerst)
    # ------------------------------------------------------------------

    def load_history_records(self) -> List[Dict]:
        """Lädt die Historie und ergänzt bei älteren Einträgen fehlende Felder
        (stabile ID, Modus, Punkteverlauf). Ergänzungen werden einmalig gespeichert."""
        with self._history_lock:
            if not self.history_file.exists():
                return []
            with open(self.history_file, 'r', encoding='utf-8') as f:
                history = json.load(f)
            if not isinstance(history, list):
                return []
            history = [m for m in history if isinstance(m, dict)]

            changed = False
            for match in history:
                try:
                    changed = upgrade_history_record(match) or changed
                except Exception as e:
                    logger.warning(f"Historie-Eintrag konnte nicht ergänzt werden: {e}")
            if changed:
                self.save_history_records(history)
            return history

    def save_history_records(self, history: List[Dict]):
        with self._history_lock:
            write_json_atomic(self.history_file, history)

    def save_match_to_history(self, state: MatchState):
        """Speichert ein beendetes Match (ersetzt einen Eintrag mit gleicher ID)"""
        try:
            with self._history_lock:
                history = self.load_history_records()
                record = build_history_record(state)
                history = [m for m in history if m.get("id") != record["id"]]
                history.append(record)
                self.save_history_records(history)
            logger.info(f"Match zur Historie hinzugefügt - {state.winner} gewinnt {state.player1_sets}:{state.player2_sets}")
        except Exception as e:
            logger.error(f"Fehler beim Speichern der Historie: {e}")

    def remove_match(self, match_id: str) -> bool:
        """Entfernt ein Match per ID. False, wenn es nicht (mehr) existiert."""
        try:
            with self._history_lock:
                history = self.load_history_records()
                remaining = [m for m in history if m.get("id") != match_id]
                if len(remaining) == len(history):
                    return False
                self.save_history_records(remaining)
                return True
        except Exception as e:
            logger.error(f"Fehler beim Entfernen aus der Historie: {e}")
            return False

def _match_format(sets_to_win: int) -> str:
    """Format-ID der App: single_set / best_of_3 / best_of_5"""
    best_of = sets_to_win * 2 - 1
    return "single_set" if best_of == 1 else "best_of_5" if best_of == 5 else "best_of_3"

def _duration_seconds(match: Dict) -> int:
    start = _parse_time(match.get("match_start_time"))
    end = _parse_time(match.get("match_end_time"))
    if start is None or end is None:
        return 0
    return max(0, int((end - start).total_seconds()))

def upgrade_history_record(match: Dict) -> bool:
    """Ergänzt fehlende Felder eines Historie-Eintrags. Returns True bei Änderung."""
    before = len(match), match.get("id")
    p1 = match.get("player1_name") or match.get("team_a") or "Team A"
    p2 = match.get("player2_name") or match.get("team_b") or "Team B"
    sets_to_win = match.get("sets_to_win") or 2

    if not match.get("id"):
        # Deterministisch, damit ein Eintrag immer dieselbe ID bekommt
        seed = f"{match.get('match_start_time')}|{match.get('match_end_time')}|{p1}|{p2}"
        match["id"] = "m_" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]
    match.setdefault("team_a", p1)
    match.setdefault("team_b", p2)
    match.setdefault("team_a_name", p1)
    match.setdefault("team_b_name", p2)
    match.setdefault("best_of", sets_to_win * 2 - 1)
    match.setdefault("mode", f"{match.get('game_mode', 'mit_vorteil_tiebreak')}|{_match_format(sets_to_win)}")
    if "timestamp" not in match and match.get("match_end_time"):
        match["timestamp"] = match["match_end_time"]
    if "sets" not in match:
        match["sets"] = [{"score_a": s[0], "score_b": s[1]} for s in match.get("set_history", [])]
    if "duration_seconds" not in match:
        match["duration_seconds"] = _duration_seconds(match)
    if "winner_team" not in match:
        winner = match.get("winner")
        match["winner_team"] = 1 if winner == p1 else 2 if winner == p2 else None
    if "point_history" not in match and match.get("history"):
        match["point_history"] = build_point_history(match)
    return (len(match), match.get("id")) != before

def build_history_record(state: MatchState) -> Dict:
    """Historie-Eintrag eines beendeten Matches (inkl. aller App-Felder)"""
    record = state.dict()
    record["id"] = state.match_id or new_match_id()
    record["sets_a"] = state.player1_sets
    record["sets_b"] = state.player2_sets
    record["timestamp"] = state.match_end_time or datetime.now().isoformat()
    record["point_history"] = build_point_history(record)
    upgrade_history_record(record)

    player1_points, player2_points = count_points(state.history)
    record["statistics"] = {
        "total_points": player1_points + player2_points,
        "duration_minutes": record["duration_seconds"] // 60,
        "player1_points_won": player1_points,
        "player2_points_won": player2_points,
        "final_score_sets": f"{state.player1_sets}:{state.player2_sets}"
    }
    return record

def app_history_record(match: Dict) -> Dict:
    """Match im Format der App (CompletedMatch): Seite statt Name als Gewinner,
    damit auch gleichnamige Teams eindeutig sind; None = Unentschieden."""
    winner_team = match.get("winner_team")
    record = {
        "id": match["id"],
        "team_a": match.get("team_a", "Team A"),
        "team_b": match.get("team_b", "Team B"),
        "winner": "A" if winner_team == 1 else "B" if winner_team == 2 else None,
        "sets": match.get("sets", []),
        "mode": match.get("mode", "mit_vorteil_tiebreak|best_of_3"),
        "timestamp": match.get("timestamp") or match.get("match_end_time") or "",
    }
    if match.get("match_start_time"):
        record["match_start_time"] = match["match_start_time"]
    if match.get("duration_seconds"):
        record["duration_seconds"] = match["duration_seconds"]
    point_history = match.get("point_history")
    if point_history and point_history.get("sets"):
        record["point_history"] = point_history
    return record

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
        self.data_file = Path(data_dir) / "wifi_ap_settings.json"
        self.settings = self.load_settings()

    def load_settings(self) -> WiFiAPSettings:
        """Lädt WiFi AP Einstellungen: erst hostapd.conf, dann data/wifi_ap_settings.json"""
        # 1) Versuche hostapd.conf (braucht ggf. root-Rechte)
        try:
            if self.hostapd_conf.exists():
                ssid = None
                password = None
                with open(self.hostapd_conf, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        if line.startswith('ssid='):
                            ssid = line.split('=', 1)[1].strip()
                        elif line.startswith('wpa_passphrase='):
                            password = line.split('=', 1)[1].strip()
                if ssid and password:
                    logger.info(f"WiFi AP Einstellungen aus hostapd.conf geladen: SSID={ssid}")
                    return WiFiAPSettings(ssid=ssid, password=password, enabled=True)
                logger.warning("Unvollständige Daten in hostapd.conf")
        except Exception as e:
            logger.warning(f"hostapd.conf nicht lesbar ({e}), versuche wifi_ap_settings.json")

        # 2) Fallback: data/wifi_ap_settings.json (vom Install-Script geschrieben)
        try:
            if self.data_file.exists():
                import json as _json
                data = _json.loads(self.data_file.read_text())
                ssid = data.get("ssid", "").strip()
                password = data.get("password", "").strip()
                if ssid:
                    logger.info(f"WiFi AP Einstellungen aus wifi_ap_settings.json geladen: SSID={ssid}")
                    return WiFiAPSettings(ssid=ssid, password=password or "openPadel", enabled=True)
        except Exception as e:
            logger.warning(f"wifi_ap_settings.json nicht lesbar: {e}")

        logger.warning("Keine WiFi-Konfiguration gefunden, verwende Defaults")
        return WiFiAPSettings()
    
    def save_settings(self, settings: WiFiAPSettings):
        """Speichert WiFi AP Einstellungen in Speicher und wifi_ap_settings.json"""
        self.settings = settings
        try:
            import json as _json
            self.data_file.parent.mkdir(parents=True, exist_ok=True)
            self.data_file.write_text(_json.dumps(
                {"ssid": settings.ssid, "password": settings.password}, indent=2
            ))
            logger.info(f"wifi_ap_settings.json geschrieben: SSID={settings.ssid}")
        except Exception as e:
            logger.warning(f"Konnte wifi_ap_settings.json nicht schreiben: {e}")
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

def _asset_version() -> str:
    """Ändert sich, sobald sich eine Datei unter static/ ändert. Hängt als ?v=
    an CSS/JS, damit Browser nach einem Update nicht die alte Fassung zeigen."""
    digest = hashlib.sha1()
    try:
        for path in sorted(Path("static").rglob("*")):
            if path.is_file():
                stat = path.stat()
                digest.update(f"{path}:{stat.st_size}:{int(stat.st_mtime)}".encode())
    except OSError:
        pass
    return digest.hexdigest()[:10]

# Der Server startet nach jedem Update neu, einmal berechnen genügt
ASSET_VERSION = _asset_version()

def get_template_context(request: Request, **kwargs) -> dict:
    """Erstellt Template-Context mit Übersetzungen"""
    context = {
        "t": language_manager.translations,
        "current_lang": language_manager.current_language,
        "asset_version": ASSET_VERSION,
        **kwargs
    }
    return context

def calculate_statistics(state: MatchState) -> Dict:
    """Berechnet Match-Statistiken aus dem State"""
    player1_points, player2_points = count_points(state.history)
    
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

def _parse_time(value) -> Optional[datetime]:
    """Parst ISO-Zeitstempel tolerant (auch mit 'Z'); immer naive Lokalzeit."""
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed

def _entry_team(entry: Dict) -> Optional[int]:
    """Welches Team hat diesen History-Eintrag gepunktet (1/2), sonst None"""
    team = entry.get("team")
    if team in (1, 2):
        return team
    action = entry.get("action", "")
    if "Spieler 1" in action or "Team 1" in action:
        return 1
    if "Spieler 2" in action or "Team 2" in action:
        return 2
    return None

def count_points(history: List[Dict]) -> Tuple[int, int]:
    """Gewonnene Punkte pro Team aus der Punkt-Historie"""
    teams = [_entry_team(h) for h in history]
    return teams.count(1), teams.count(2)

def _score_point(state: MatchState, player: int, now: datetime,
                 legacy_tiebreak_serve: bool = False) -> Dict:
    """
    Kern der Zähllogik: wendet EINEN Punkt auf den State an.

    Ohne Seiteneffekte (kein Speichern, kein History-Eintrag), damit Live-
    Zählung, Undo-Replay und Punkteverlauf exakt dieselben Regeln benutzen.
    Returns: Infos zum Punkt (Satz-Index, Aufschläger, Tie-Break, Game-Gewinner,
    Game-Dauer) für den Punkteverlauf.
    """
    stamp = now.isoformat()

    if not state.match_started or not state.match_start_time:
        state.match_started = True
        state.match_start_time = state.match_start_time or stamp
    if not state.match_id:
        state.match_id = new_match_id()

    # Tie-Break starten (normalerweise schon nach dem letzten Game gesetzt)
    if not state.in_tiebreak and game_logic.check_tiebreak_needed(
            state.player1_games, state.player2_games, state.game_mode):
        _start_tiebreak(state)

    # Game-Dauer zählt ab dem ERSTEN Punkt des Games (Pausen zählen nicht)
    if state.current_game_start_time is None:
        state.current_game_start_time = stamp

    info = {
        "set": len(state.set_history),
        "server": state.server,
        "tb": state.in_tiebreak,
        "game_winner": None,
        "duration": None,
    }

    if player == 1:
        state.player1_points += 1
    else:
        state.player2_points += 1

    if state.in_tiebreak:
        state.tiebreak_total_points += 1
        game_winner = game_logic.check_tiebreak_won(
            state.player1_points, state.player2_points, state.game_mode)
    else:
        game_winner = game_logic.check_game_won(
            state.player1_points, state.player2_points, state.game_mode)

    if not game_winner:
        if state.in_tiebreak:
            state.server = game_logic.get_tiebreak_server(
                state.tiebreak_total_points, state.tiebreak_server_at_start)
        return info

    # ---- Game (oder Tie-Break) gewonnen ----
    info["game_winner"] = game_winner
    start = _parse_time(state.current_game_start_time)
    if start is not None:
        duration = max(0, int((now - start).total_seconds()))
        state.game_durations.append(duration)
        info["duration"] = duration
    state.current_game_start_time = None

    was_tiebreak = state.in_tiebreak
    if game_winner == 1:
        state.player1_games += 1
    else:
        state.player2_games += 1
    state.player1_points = 0
    state.player2_points = 0

    if was_tiebreak:
        set_winner = game_winner
        if legacy_tiebreak_serve:
            state.server = 2 if game_winner == 1 else 1
        else:
            # FIP: Den nächsten Satz beginnt das Paar, das im Tie-Break NICHT
            # zuerst aufgeschlagen hat.
            state.server = 2 if state.tiebreak_server_at_start == 1 else 1
        state.in_tiebreak = False
        state.tiebreak_total_points = 0
    else:
        state.server = 2 if state.server == 1 else 1
        set_winner = game_logic.check_set_won(
            state.player1_games, state.player2_games, state.game_mode)

    if not set_winner:
        if game_logic.check_tiebreak_needed(
                state.player1_games, state.player2_games, state.game_mode):
            _start_tiebreak(state)
        return info

    # ---- Satz gewonnen ----
    state.set_history.append([state.player1_games, state.player2_games])
    if set_winner == 1:
        state.player1_sets += 1
    else:
        state.player2_sets += 1
    state.player1_games = 0
    state.player2_games = 0

    match_winner = game_logic.check_match_won(
        state.player1_sets, state.player2_sets, state.sets_to_win)
    if match_winner:
        state.match_finished = True
        state.match_end_time = stamp
        state.winner_team = match_winner
        state.winner = state.player1_name if match_winner == 1 else state.player2_name

    return info

def _start_tiebreak(state: MatchState):
    state.in_tiebreak = True
    state.tiebreak_server_at_start = state.server
    state.tiebreak_total_points = 0
    state.player1_points = 0
    state.player2_points = 0

def replay_history(entries: List[Dict], *, player1_name: str, player2_name: str,
                   game_mode: str, sets_to_win: int, initial_server: int = 1,
                   match_id: Optional[str] = None, servers_known: bool = True,
                   legacy_tiebreak_serve: bool = False) -> Tuple[MatchState, Dict]:
    """
    Baut State UND Punkteverlauf aus den History-Einträgen neu auf.

    Punkteverlauf-Format (wie in der App, alle Sätze in Reihenfolge):
    {"sets":[{"games":[{"w":"A","s":"B","tb":false,"p":["A","B",...],"u":0,"d":95}],
              "unknown_games":0}]}
    """
    state = MatchState(
        player1_name=player1_name,
        player2_name=player2_name,
        game_mode=game_mode,
        sets_to_win=sets_to_win,
        server=initial_server if initial_server in (1, 2) else 1,
        match_id=match_id,
    )
    sets: List[Dict] = []
    current_game: Optional[Dict] = None
    current_set = 0

    def set_bucket(index: int) -> Dict:
        while len(sets) <= index:
            sets.append({"games": [], "unknown_games": 0})
        return sets[index]

    for entry in entries:
        team = _entry_team(entry)
        if team is None:
            continue
        if state.match_finished:
            break
        # Der beim Punkt gespeicherte Aufschläger gewinnt (deckt die Wahl vor
        # dem Match und manuelle Korrekturen während des Matches ab).
        if entry.get("server") in (1, 2):
            _set_server(state, entry["server"])

        when = _parse_time(entry.get("timestamp")) or datetime.now()
        info = _score_point(state, team, when, legacy_tiebreak_serve)
        state.history.append(entry)

        if current_game is None:
            current_set = info["set"]
            current_game = {
                "w": None,
                "s": ("A" if info["server"] == 1 else "B") if servers_known else "",
                "tb": info["tb"],
                "p": [],
                "u": 0,
            }
        current_game["p"].append("A" if team == 1 else "B")

        if info["game_winner"]:
            current_game["w"] = "A" if info["game_winner"] == 1 else "B"
            duration = info["duration"]
            if duration is not None and duration <= MAX_GAME_DURATION_SECONDS:
                current_game["d"] = duration
            set_bucket(current_set)["games"].append(current_game)
            current_game = None

    if current_game is not None:
        # Unvollendetes Game (Match manuell beendet)
        set_bucket(current_set)["games"].append(current_game)

    return state, {"sets": sets}

def build_point_history(match: Dict) -> Dict:
    """Punkteverlauf eines (laufenden oder gespeicherten) Matches als Dict"""
    entries = [e for e in match.get("history", []) if _entry_team(e)]
    args = dict(
        player1_name=match.get("player1_name", "Team A"),
        player2_name=match.get("player2_name", "Team B"),
        game_mode=match.get("game_mode", "mit_vorteil_tiebreak"),
        sets_to_win=match.get("sets_to_win", 2),
    )
    if not entries:
        return {"sets": []}

    if all(e.get("server") in (1, 2) for e in entries):
        return replay_history(entries, **args)[1]

    # Ältere Matches ohne gespeicherten Aufschläger: aus dem End-Aufschläger
    # zurückrechnen. Geht nur ohne Tie-Break (danach hing der Aufschlag früher
    # vom Tie-Break-Sieger ab) - sonst bleibt der Aufschläger unbekannt.
    state, history = replay_history(entries, initial_server=1,
                                    legacy_tiebreak_serve=True, **args)
    had_tiebreak = any(g["tb"] for s in history["sets"] for g in s["games"])
    final_server = match.get("server")
    if had_tiebreak or final_server not in (1, 2):
        return replay_history(entries, servers_known=False,
                              legacy_tiebreak_serve=True, **args)[1]
    if state.server == final_server:
        return history
    return replay_history(entries, initial_server=2,
                          legacy_tiebreak_serve=True, **args)[1]

def undo_point(state: MatchState) -> MatchState:
    """
    Macht den letzten Punkt rückgängig.

    Der State wird aus der verbleibenden History neu aufgebaut - mit denselben
    Regeln wie beim Zählen, inkl. Aufschläger, Game-Dauern und Tie-Break. Auch
    über Game-/Satz-/Match-Grenzen hinweg (ein bereits gespeichertes Match wird
    wieder aus der Historie entfernt).
    """
    with match_lock:
        if len(state.history) == 0:
            logger.warning("Keine History zum Undo vorhanden")
            return state

        was_finished = state.match_finished
        remaining = state.history[:-1]
        removed = state.history[-1]
        logger.info(f"Undo: {removed.get('action')}")

        first_server = next(
            (e["server"] for e in remaining if e.get("server") in (1, 2)),
            removed.get("server", 1))
        new_state, _ = replay_history(
            remaining,
            player1_name=state.player1_name,
            player2_name=state.player2_name,
            game_mode=state.game_mode,
            sets_to_win=state.sets_to_win,
            initial_server=first_server,
            match_id=state.match_id,
        )
        # Vor dem entfernten Punkt schlug genau dieses Team auf
        if removed.get("server") in (1, 2):
            _set_server(new_state, removed["server"])
        if remaining and state.match_start_time:
            new_state.match_start_time = state.match_start_time

        if was_finished and state.match_id:
            state_manager.remove_match(state.match_id)

        state_manager.save_state(new_state)

        tiebreak_status = "im Tiebreak" if new_state.in_tiebreak else "normales Spiel"
        logger.info(f"Undo abgeschlossen ({tiebreak_status}): Score jetzt {new_state.player1_points}-{new_state.player2_points}, Games {new_state.player1_games}-{new_state.player2_games}, Sets {new_state.player1_sets}-{new_state.player2_sets}")

        return new_state

def add_point(state: MatchState, player: int) -> MatchState:
    """
    Fügt einem Spieler einen Punkt hinzu und aktualisiert den Status
    player: 1 oder 2
    """
    with match_lock:
        if state.match_finished:
            return state

        now = datetime.now()
        server_before = state.server
        info = _score_point(state, player, now)

        state.history.append({
            "timestamp": now.isoformat(),
            "action": f"Punkt für Team {player}",
            "team": player,
            "server": server_before,
            "tb": info["tb"],
            "score": f"{state.player1_points}-{state.player2_points}"
        })

        if info["game_winner"]:
            logger.info(f"{'Tie-Break' if info['tb'] else 'Spiel'} gewonnen: Team {info['game_winner']}")
        if state.match_finished:
            logger.info(f"Match gewonnen: {state.winner}")
            state_manager.save_match_to_history(state)

        state_manager.save_state(state)
        return state

def _set_server(state: MatchState, server: int):
    """Setzt den Aufschläger manuell (gleiches Verhalten wie in der App)."""
    if state.match_finished or server == state.server:
        return
    # Im Tie-Break wird der Aufschläger bei jedem Punkt aus dem Start-
    # Aufschläger berechnet - der muss mitwechseln, sonst macht der nächste
    # Punkt die Korrektur wieder rückgängig.
    if state.in_tiebreak:
        state.tiebreak_server_at_start = 2 if state.tiebreak_server_at_start == 1 else 1
    state.server = server

def get_state_dict(state: MatchState) -> Dict:
    """State für Web-Frontend, E-Paper-Display und App.

    Die flachen Felder (team_a_name, games_a, ...) nutzen Web-UI und Display.
    Die App liest die verschachtelten Felder (team_a, sets, current_game,
    sets_won, mode, match_completed, match_winner) - nur dort stecken das
    Match-Format (Best-of) und die Sätze so, wie die App sie erwartet.
    """
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

    winner_side = None
    if state.match_finished:
        if state.winner_team in (1, 2):
            winner_side = "a" if state.winner_team == 1 else "b"
        elif state.winner == state.player1_name:
            winner_side = "a"
        elif state.winner == state.player2_name:
            winner_side = "b"

    # Abgeschlossene Sätze + der laufende Satz (bei manuell beendetem Match
    # steckt der Teilsatz schon in set_history)
    sets = [{"score_a": s[0], "score_b": s[1]} for s in state.set_history]
    if not state.match_finished and (state.player1_games > 0 or state.player2_games > 0):
        sets.append({"score_a": state.player1_games, "score_b": state.player2_games})

    serve = "a" if state.server == 1 else "b"
    current_set = state.player1_sets + state.player2_sets + 1

    return {
        "team_a_name": state.player1_name,
        "team_b_name": state.player2_name,
        "sets_a": state.player1_sets,
        "sets_b": state.player2_sets,
        "games_a": state.player1_games,
        "games_b": state.player2_games,
        "points_a": state.player1_points,  # Roh-Punkte (zählen bei Einstand weiter: 4:3, 5:4 ...)
        "points_b": state.player2_points,
        "points_a_display": score_p1,  # Formatiert (0, 15, 30, 40, AD) oder Tie-Break Punkte
        "points_b_display": score_p2,
        "serve": serve,
        "current_set": current_set,
        "set_history": state.set_history,
        "match_over": state.match_finished,
        "winner": winner_side,
        "best_of": state.sets_to_win * 2 - 1,
        "game_mode": state.game_mode,
        "in_tiebreak": state.in_tiebreak,  # Tie-Break Status für Frontend
        "match_id": state.match_id,

        # ---- App-Format ----
        "team_a": state.player1_name,
        "team_b": state.player2_name,
        "sets": sets,
        "current_game": {
            "points": {"A": state.player1_points, "B": state.player2_points},
            "server": serve.upper(),
            "tiebreak": state.in_tiebreak,
            "display_points_a": score_p1,
            "display_points_b": score_p2,
        },
        "sets_won": {"A": state.player1_sets, "B": state.player2_sets},
        "mode": f"{state.game_mode}|{_match_format(state.sets_to_win)}",
        "match_completed": state.match_finished,
        "match_winner": winner_side.upper() if winner_side else None,
        "game_durations": state.game_durations,
        "set_durations": state.set_durations,
        "current_game_start_time": state.current_game_start_time,
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
    
    # Spielmodus und Best-of bleiben erhalten (die App zeigt sie weiter an)
    current_match = MatchState(
        player1_name=current_match.player1_name,
        player2_name=current_match.player2_name,
        game_mode=current_match.game_mode,
        sets_to_win=current_match.sets_to_win,
        server=current_match.server  # Aufschläger bleibt (wie in der App)
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
    
    _set_server(current_match, player)
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
            _set_server(current_match, 2 if current_match.server == 1 else 1)
        else:
            if team == "team_a" or team == "a":
                team = 1
            elif team == "team_b" or team == "b":
                team = 2
            
            if team not in [1, 2]:
                raise HTTPException(status_code=400, detail=f"Team muss 1 oder 2 sein (erhalten: {body})")
            
            _set_server(current_match, team)
        
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
    return _game_mode_list()

@app.get("/api/game-modes/{mode_id}")
async def get_game_mode(mode_id: str):
    """Gibt einzelnen Spielmodus nach ID zurück"""
    mode = game_mode_manager.get_mode(mode_id)
    if not mode:
        raise HTTPException(status_code=404, detail=f"Spielmodus '{mode_id}' nicht gefunden")
    return {"id": mode_id, **mode, "is_custom": mode_id not in FIXED_GAME_MODE_IDS}

def _now_ms() -> int:
    return int(time.time() * 1000)

def _mode_updated_at(mode: Optional[Dict]) -> int:
    try:
        return int((mode or {}).get("updated_at") or 0)
    except (TypeError, ValueError):
        return 0

def _store_game_mode(payload: GameModePayload, updated_at: int):
    """Prüft und speichert einen eigenen Spielmodus (löscht eine Löschmarke)."""
    if payload.id in FIXED_GAME_MODE_IDS:
        raise HTTPException(status_code=403, detail="Standard-Spielmodi können nicht geändert werden")
    if not GAME_MODE_ID_PATTERN.match(payload.id):
        raise HTTPException(status_code=400, detail="Ungültige Spielmodus-ID (erlaubt: a-z, 0-9, _)")
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name erforderlich")

    rules = payload.rules.dict()
    # Ohne Vorteil und ohne Tiebreak entscheidet nur ein Golden Point das Spiel
    if not rules["advantage"] and not rules["tiebreak"]:
        rules["golden_point"] = True
    mode_data = {
        "name": name,
        "description": payload.description.strip(),
        "is_custom": True,
        "updated_at": int(updated_at),
        "rules": rules,
    }
    if payload.icon_key:
        mode_data["icon_key"] = payload.icon_key
    game_mode_manager.save_mode(payload.id, mode_data)
    game_mode_manager.clear_deleted(payload.id)

def _game_mode_in_running_match(mode_id: str) -> bool:
    return (current_match.game_mode == mode_id
            and current_match.match_started and not current_match.match_finished)

def _remove_game_mode(mode_id: str, deleted_at: int):
    """Löscht einen eigenen Modus und merkt sich die Löschung für den Sync."""
    global current_match
    if current_match.game_mode == mode_id:
        # Kein Match im Gange: zurück auf den Standardmodus
        current_match.game_mode = DEFAULT_GAME_MODE_ID
        state_manager.save_state(current_match)
    game_mode_manager.delete_mode(mode_id)
    game_mode_manager.mark_deleted(mode_id, deleted_at)

def _game_mode_list() -> List[Dict]:
    return [
        {"id": mode_id, **mode, "is_custom": mode_id not in FIXED_GAME_MODE_IDS}
        for mode_id, mode in game_mode_manager.modes.items()
    ]

@app.post("/api/game-modes")
async def create_or_update_game_mode(payload: GameModePayload):
    """Speichert benutzerdefinierten Spielmodus (Upsert)"""
    _store_game_mode(payload, payload.updated_at or _now_ms())
    return {"status": "ok", "id": payload.id}

@app.post("/api/game-modes/sync")
async def sync_game_modes(request: Request):
    """
    Gleicht die eigenen Spielmodi mit einer App ab.

    Body: {"modes": [<Modus mit updated_at>, ...], "deleted": {"<id>": <ms>, ...}}
    Je Modus gewinnt die jüngste Aktion (Bearbeiten oder Löschen), egal ob sie
    in der App, im Web-Interface oder auf einem anderen Handy passiert ist.
    Antwort: alle Modi des Servers, alle Löschmarken und in "kept" die Modi,
    deren Löschung warten muss, weil das laufende Match sie verwendet.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="JSON-Objekt erwartet")
    app_modes = body.get("modes") if isinstance(body.get("modes"), list) else []
    app_deleted = body.get("deleted") if isinstance(body.get("deleted"), dict) else {}

    kept = []
    with match_lock:
        # 1) In der App gelöschte Modi
        for mode_id, raw_ts in app_deleted.items():
            if mode_id in FIXED_GAME_MODE_IDS or not GAME_MODE_ID_PATTERN.match(str(mode_id)):
                continue
            try:
                deleted_at = int(raw_ts)
            except (TypeError, ValueError):
                continue
            existing = game_mode_manager.modes.get(mode_id)
            if existing is not None:
                if _mode_updated_at(existing) > deleted_at:
                    continue  # danach noch bearbeitet: die Bearbeitung gewinnt
                if _game_mode_in_running_match(mode_id):
                    kept.append(mode_id)
                    continue
                _remove_game_mode(mode_id, deleted_at)
            else:
                game_mode_manager.mark_deleted(mode_id, deleted_at)

        # 2) Modi der App: neu anlegen oder überschreiben, wenn sie jünger sind
        for raw in app_modes:
            try:
                payload = GameModePayload(**raw)
            except Exception:
                continue
            if payload.id in FIXED_GAME_MODE_IDS or payload.id in kept:
                continue
            updated_at = payload.updated_at or 0
            deleted_at = game_mode_manager.deleted.get(payload.id)
            if deleted_at is not None and deleted_at >= updated_at:
                continue  # hier (oder auf einem anderen Gerät) später gelöscht
            existing = game_mode_manager.modes.get(payload.id)
            if existing is not None and _mode_updated_at(existing) >= updated_at:
                continue  # Fassung des Servers ist gleich alt oder jünger
            try:
                _store_game_mode(payload, updated_at)
            except HTTPException:
                continue

    return {
        "modes": _game_mode_list(),
        "deleted": game_mode_manager.deleted,
        "kept": kept,
    }

@app.delete("/api/game-modes/{mode_id}")
async def delete_game_mode(mode_id: str, deleted_at: Optional[int] = None):
    """Löscht benutzerdefinierten Spielmodus"""
    if mode_id in FIXED_GAME_MODE_IDS:
        raise HTTPException(status_code=403, detail="Standard-Spielmodi können nicht gelöscht werden")
    if mode_id not in game_mode_manager.modes:
        raise HTTPException(status_code=404, detail=f"Spielmodus '{mode_id}' nicht gefunden")
    if _game_mode_in_running_match(mode_id):
        raise HTTPException(status_code=409, detail="Spielmodus wird im laufenden Match verwendet")

    _remove_game_mode(mode_id, deleted_at or _now_ms())
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
    # Wie in der App: im nächsten Match beginnt das andere Team
    next_server = 2 if current_match.server == 1 else 1

    # Neues Match erstellen
    current_match = MatchState(
        player1_name=player1_name,
        player2_name=player2_name,
        game_mode=game_mode,
        sets_to_win=sets_to_win,
        server=next_server
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
    - Wer mehr Sätze gewonnen hat → Gewinner
    - Bei gleicher Satzanzahl: Wer insgesamt mehr Games gewonnen hat → Gewinner
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

    # Wie in der App: erst Sätze, bei Gleichstand alle gewonnenen Games
    # (abgeschlossene Sätze + laufender Satz), sonst Unentschieden.
    games_1 = sum(s[0] for s in current_match.set_history) + current_match.player1_games
    games_2 = sum(s[1] for s in current_match.set_history) + current_match.player2_games
    if current_match.player1_sets != current_match.player2_sets:
        winner = 1 if current_match.player1_sets > current_match.player2_sets else 2
    elif games_1 != games_2:
        winner = 1 if games_1 > games_2 else 2

    if winner:
        winner_name = current_match.player1_name if winner == 1 else current_match.player2_name
    else:
        winner_name = "Unentschieden"

    # Laufenden Satz in die Satz-Historie übernehmen; ganz ohne Game bleibt
    # (wie in der App) ein 0:0-Satz stehen.
    if current_match.player1_games > 0 or current_match.player2_games > 0:
        current_match.set_history.append([current_match.player1_games, current_match.player2_games])
    elif not current_match.set_history:
        current_match.set_history.append([0, 0])

    # Match als beendet markieren
    current_match.match_finished = True
    current_match.match_end_time = datetime.now().isoformat()
    current_match.winner = winner_name
    current_match.winner_team = winner
    if not current_match.match_id:
        current_match.match_id = new_match_id()

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

def _game_duration_list(matches: List[Dict]) -> List[int]:
    """Alle aufgezeichneten Game-Dauern (Sekunden) aus den Punkteverläufen"""
    durations = []
    for match in matches:
        for set_data in (match.get("point_history") or {}).get("sets", []):
            for game in set_data.get("games", []):
                if game.get("w") and isinstance(game.get("d"), int):
                    durations.append(game["d"])
    return durations

@app.get("/api/game-stats")
async def get_game_stats():
    """Game-Dauern über alle gespeicherten Matches + das laufende Match"""
    durations = _game_duration_list(state_manager.load_history_records())
    if not current_match.match_finished:
        durations += [d for d in current_match.game_durations
                      if d <= MAX_GAME_DURATION_SECONDS]

    if not durations:
        return {"games": []}

    return {
        "total_games": len(durations),
        "games": [
            {
                "game_number": i + 1,
                "game_index": i,
                "duration_seconds": duration,
                "duration_formatted": f"{duration // 60}m {duration % 60}s"
            }
            for i, duration in enumerate(durations)
        ],
        "average_game_duration": sum(durations) // len(durations),
        "longest_game": max(durations),
        "shortest_game": min(durations)
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
    roi_points = data.get('roi') or data.get('points') or []
    
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
    """
    Match-Historie, älteste zuerst.

    - "history": Format der App (CompletedMatch) inkl. "point_history"
    - "matches": bisheriges Format für das Web-Frontend (ohne Punkt-Rohdaten)
    """
    try:
        records = state_manager.load_history_records()
        matches = [
            {k: v for k, v in match.items() if k not in ("history", "point_history")}
            for match in records
        ]
        return {
            "history": [app_history_record(match) for match in records],
            "matches": matches,
        }
    except Exception as e:
        logger.error(f"Fehler beim Laden der Historie: {e}")
        return {"history": [], "matches": []}

def _find_history_match(history: List[Dict], raw_id: str) -> Optional[int]:
    """Index des Matches zu einer ID, sonst None.

    Kennt die stabile ID sowie die früheren, von Clients erzeugten Formate
    "match_<index>_<endzeit>" und "match_<endzeit>" (Zuordnung über die Endzeit).
    """
    from urllib.parse import unquote
    candidates = {raw_id, unquote(raw_id)}

    for i, match in enumerate(history):
        if match.get("id") in candidates:
            return i

    for candidate in candidates:
        legacy = re.match(r"^match_(?:\d+_)?(.+)$", candidate)
        if not legacy:
            continue
        stamp = legacy.group(1)
        for i, match in enumerate(history):
            if stamp in (match.get("match_end_time"), match.get("timestamp")):
                return i
    return None

def _delete_history_match(match_id: str) -> Dict:
    """Löscht ein Match. Idempotent: eine unbekannte ID ist kein Fehler, damit
    in der App vorgemerkte Löschungen nicht endlos wiederholt werden."""
    try:
        with state_manager._history_lock:
            history = state_manager.load_history_records()
            index = _find_history_match(history, match_id)
            if index is None:
                logger.info(f"Match '{match_id}' nicht (mehr) in der Historie - nichts zu löschen")
                return {"status": "success", "deleted": False, "remaining_matches": len(history)}

            deleted = history.pop(index)
            state_manager.save_history_records(history)

        logger.info(f"Match gelöscht: {deleted.get('team_a')} vs {deleted.get('team_b')} ({deleted.get('id')})")
        return {
            "status": "success",
            "message": "Match gelöscht",
            "deleted": True,
            "remaining_matches": len(history)
        }
    except Exception as e:
        logger.error(f"Fehler beim Löschen: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/history/delete")
async def delete_match_post(request: Request):
    """Löscht ein Match per JSON-Body {"id": "..."} (Fallback der App)"""
    try:
        body = await request.json()
    except Exception:
        body = {}
    match_id = body.get("id") if isinstance(body, dict) else None
    if not match_id or not isinstance(match_id, str):
        raise HTTPException(status_code=400, detail="id erforderlich")
    return _delete_history_match(match_id)

@app.delete("/api/history/{match_id:path}")
async def delete_match(match_id: str):
    """Löscht ein Match aus der Historie (idempotent)"""
    return _delete_history_match(match_id)

@app.delete("/api/history")
async def clear_history():
    """Löscht KOMPLETTE Match-Historie (alle Matches, idempotent)"""
    try:
        with state_manager._history_lock:
            match_count = len(state_manager.load_history_records())
            state_manager.save_history_records([])

        logger.info(f"Komplette Match-Historie gelöscht ({match_count} Matches)")
        return {
            "status": "success",
            "message": f"Alle {match_count} Matches gelöscht",
            "deleted_count": match_count
        }
    except Exception as e:
        logger.error(f"Fehler beim Löschen der Historie: {e}")
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
            
            # Aktuelle SSID aus dem Manager (liest hostapd.conf oder wifi_ap_settings.json)
            current = wifi_ap_manager.reload_from_hostapd()
            ssid = current.ssid
            password = current.password
            
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
    """Speichert WiFi AP Einstellungen in data/wifi_ap_settings.json (kein hostapd-Apply)"""
    wifi_ap_manager.save_settings(settings)
    logger.info(f"WiFi AP Einstellungen gespeichert: SSID={settings.ssid}")
    return {"status": "saved", "message": "Einstellungen gespeichert."}


def _build_hostapd_conf(ssid: str, password: str) -> str:
    """Generiert hostapd.conf aus Template (liest data/wifi_config.json für country/channel)"""
    import json as _json
    country_code = "DE"
    channel = "1"
    try:
        cfg_path = project_dir / "data" / "wifi_config.json"
        if cfg_path.exists():
            cfg = _json.loads(cfg_path.read_text())
            country_code = cfg.get("country_code", country_code)
            channel = str(cfg.get("channel", channel))
    except Exception:
        pass
    return (
        f"interface=wlan0\n"
        f"ssid={ssid}\n"
        f"channel={channel}\n"
        f"hw_mode=g\n"
        f"ieee80211n=1\n"
        f"ieee80211d=1\n"
        f"country_code={country_code}\n"
        f"wmm_enabled=1\n"
        f"auth_algs=1\n"
        f"wpa=2\n"
        f"wpa_key_mgmt=WPA-PSK\n"
        f"rsn_pairwise=CCMP\n"
        f"wpa_passphrase={password}\n"
    )


@app.post("/api/wifi-ap/apply")
async def apply_wifi_ap():
    """Wendet gespeicherte WiFi-Einstellungen auf hostapd.conf an (sudo mv + systemctl)"""
    import platform
    settings = wifi_ap_manager.settings
    if not settings.ssid:
        return {"status": "error", "message": "Keine Einstellungen gespeichert."}

    if platform.machine() not in ['armv7l', 'aarch64']:
        return {"status": "error", "message": "Nur auf Raspberry Pi verfügbar."}

    hostapd_conf = '/etc/hostapd/hostapd.conf'
    tmp_conf = '/tmp/hostapd.conf.new'

    try:
        # Neuen Config-Inhalt aus Template generieren
        content = _build_hostapd_conf(settings.ssid, settings.password)
        with open(tmp_conf, 'w') as f:
            f.write(content)

        # Backup (falls erlaubt)
        subprocess.run(['sudo', 'cp', hostapd_conf, f'{hostapd_conf}.backup'], check=False)

        # Per sudo mv einsetzen (sudoers: NOPASSWD /bin/mv /tmp/hostapd.conf.new ...)
        r = subprocess.run(['sudo', 'mv', tmp_conf, hostapd_conf],
                           capture_output=True, text=True)
        if r.returncode != 0:
            logger.error(f"sudo mv fehlgeschlagen: {r.stderr}")
            return {"status": "no_sudo",
                    "message": "sudo mv fehlgeschlagen – sudoers-Eintrag fehlt.",
                    "ssid": settings.ssid, "password": settings.password}

        subprocess.run(['sudo', 'chmod', '600', hostapd_conf], check=False)

        # hostapd neu starten
        subprocess.run(['sudo', 'systemctl', 'stop', 'hostapd'], check=False)
        await asyncio.sleep(1)
        result = subprocess.run(['sudo', 'systemctl', 'start', 'hostapd'],
                                capture_output=True, text=True)

        if result.returncode != 0:
            logger.error(f"hostapd start fehlgeschlagen: {result.stderr}")
            return {"status": "error", "message": f"hostapd start fehlgeschlagen: {result.stderr}"}

        await asyncio.sleep(2)
        wifi_ap_manager.reload_from_hostapd()
        logger.info(f"hostapd erfolgreich auf SSID={settings.ssid} aktualisiert")
        return {"status": "success",
                "message": f"WLAN aktualisiert auf '{settings.ssid}'. Bitte neu verbinden!"}

    except Exception as e:
        logger.error(f"apply_wifi_ap Fehler: {e}")
        return {"status": "error", "message": str(e)}

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
# AUTO-UPDATE & NEUSTART
# ============================================================================

# Solange der letzte Punkt jünger ist, gilt ein Match als laufend und
# ein Update wartet (der Neustart dauert ca. 30 Sekunden)
UPDATE_MATCH_IDLE_SECONDS = 20 * 60

def match_in_progress() -> bool:
    state = current_match
    if not state.match_started or state.match_finished or not state.history:
        return False
    last_point = _parse_time(state.history[-1].get("timestamp"))
    if last_point is None:
        return True
    return (datetime.now() - last_point).total_seconds() < UPDATE_MATCH_IDLE_SECONDS

def restart_server(delay: float = 1.5):
    """Beendet den Server-Prozess; systemd (Restart=always) startet ihn neu."""
    def _terminate():
        logger.info("Server wird neu gestartet...")
        os.kill(os.getpid(), signal.SIGTERM)
        # Offene Streams (Webcam) können das saubere Beenden blockieren
        time.sleep(15)
        os._exit(0)
    timer = threading.Timer(delay, _terminate)
    timer.daemon = True
    timer.start()

auto_updater = updater.AutoUpdater(is_busy=match_in_progress, restart=restart_server)

@app.get("/api/update/status")
async def get_update_status():
    """Installierter Stand, letzter Check und Auto-Update-Einstellungen"""
    return await asyncio.to_thread(auto_updater.status)

@app.post("/api/update/check")
async def trigger_update_check(request: Request):
    """Stößt eine Prüfung an. Body (optional): {"apply": true} installiert sofort,
    auch während eines laufenden Matches."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    apply = bool(isinstance(body, dict) and body.get("apply"))
    auto_updater.request(apply=apply, force=apply)
    return {"status": "success", "apply": apply}

@app.post("/api/update/settings")
async def update_update_settings(request: Request):
    """Body: {"enabled": bool, "interval_minutes": int}"""
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="JSON-Objekt erwartet")
    changes = {}
    if "enabled" in body:
        changes["enabled"] = bool(body["enabled"])
    if "interval_minutes" in body:
        try:
            changes["interval_minutes"] = int(body["interval_minutes"])
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="interval_minutes muss eine Zahl sein")
    updater.save_settings(changes)
    return await asyncio.to_thread(auto_updater.status)

@app.post("/api/system/restart")
async def system_restart():
    """Startet den Server-Dienst neu (nur als systemd-Dienst möglich)"""
    if not updater.running_under_systemd():
        raise HTTPException(status_code=409, detail="Neustart nur als systemd-Dienst möglich")
    restart_server()
    return {"status": "success", "message": "Server wird neu gestartet..."}

# ============================================================================
# STARTUP & SHUTDOWN
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialisierung beim Start"""
    logger.info("=" * 60)
    logger.info("Tennis Scoring System startet...")
    logger.info("=" * 60)

    auto_updater.start()

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
