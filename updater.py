#!/usr/bin/env python3
"""
openPadel Auto-Updater

Prüft regelmäßig, ob auf GitHub ein neuerer Stand liegt, holt ihn über die
LAN-Verbindung und startet den Server danach neu. Nur Standardbibliothek,
damit `start_server.sh` das Skript vor dem venv aufrufen kann:

    python3 updater.py --boot-check   # Rollback, wenn ein Update nicht bootet
    python3 updater.py --check        # einmal prüfen (ohne zu installieren)
    python3 updater.py --apply        # einmal prüfen und installieren

Ablauf eines Updates:
  1. `git ls-remote` vergleicht den Remote-Stand mit HEAD.
  2. `git fetch`, lokal geänderte Dateien werden nach data/update_backup kopiert.
  3. `git reset --hard` auf den neuen Stand; Benutzerdaten (data/, game_modes/)
     werden zurückkopiert.
  4. Syntax-Check des neuen Codes, sonst sofortiger Rollback.
  5. Neustart des Dienstes (systemd `Restart=always`). `start_server.sh`
     installiert dabei neue Python-Pakete.
  6. Startet der neue Stand zweimal nicht sauber, setzt `--boot-check`
     auf den vorherigen Stand zurück.
"""

import json
import logging
import os
import shutil
import socket
import struct
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional
from urllib.parse import urlparse

logger = logging.getLogger("openPadel.updater")

REPO_DIR = Path(__file__).resolve().parent
DATA_DIR = REPO_DIR / "data"
SETTINGS_FILE = DATA_DIR / "update_settings.json"
STATUS_FILE = DATA_DIR / "update_status.json"
PENDING_FILE = DATA_DIR / "update_pending.json"
BACKUP_DIR = DATA_DIR / "update_backup"

# Verzeichnisse mit Benutzerdaten: lokale Änderungen überleben jedes Update
USER_PATHS = ("data", "game_modes")
# Änderungen an diesen Dateien brauchen root und werden nicht automatisch angewandt
INSTALLER_FILES = ("install_complete.sh", "install_serveronly.sh", "presetup.sh")
SYNTAX_CHECK_FILES = ("main.py", "display_worker.py", "updater.py", "shutdown_helper.py")

DEFAULT_SETTINGS = {"enabled": True, "interval_minutes": 30, "branch": "main"}
MIN_INTERVAL_MINUTES = 5
BOOT_CONFIRM_SECONDS = 90      # so lange muss der Server laufen, bis ein Update als gelungen gilt
DEFERRED_RETRY_SECONDS = 300   # erneuter Versuch, wenn gerade ein Match läuft
MAX_BOOT_ATTEMPTS = 2
PUBLIC_DNS = ("1.1.1.1", "8.8.8.8", "9.9.9.9")


class UpdateError(Exception):
    pass


# ============================================================================
# Kleine Helfer
# ============================================================================

def _now() -> str:
    # naive Ortszeit, wie überall im Server
    return datetime.now().isoformat(timespec="seconds")


def _read_json(path: Path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, type(default)) else default
    except Exception:
        return default


def _write_json(path: Path, data):
    path.parent.mkdir(exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def running_under_systemd() -> bool:
    """systemd setzt INVOCATION_ID für alle Prozesse eines Dienstes."""
    return bool(os.environ.get("INVOCATION_ID"))


def load_settings() -> Dict:
    settings = dict(DEFAULT_SETTINGS)
    settings.update(_read_json(SETTINGS_FILE, {}))
    try:
        settings["interval_minutes"] = max(MIN_INTERVAL_MINUTES, int(settings["interval_minutes"]))
    except (TypeError, ValueError):
        settings["interval_minutes"] = DEFAULT_SETTINGS["interval_minutes"]
    settings["enabled"] = bool(settings["enabled"])
    settings["branch"] = str(settings["branch"] or "main")
    return settings


def save_settings(changes: Dict) -> Dict:
    settings = load_settings()
    for key in DEFAULT_SETTINGS:
        if changes.get(key) is not None:
            settings[key] = changes[key]
    _write_json(SETTINGS_FILE, settings)
    return load_settings()


def load_status() -> Dict:
    return _read_json(STATUS_FILE, {})


def _set_status(**changes) -> Dict:
    status = load_status()
    status.update(changes)
    _write_json(STATUS_FILE, status)
    return status


# ============================================================================
# DNS-Fallback
# ============================================================================
# Nach der Access-Point-Einrichtung hat der Pi über LAN oft keinen DNS-Server
# mehr (/etc/resolv.conf). Statt root-Rechte zu brauchen, fragen wir einen
# öffentlichen DNS-Server direkt und geben git die Adresse mit.

def _dns_query(host: str, server: str, timeout: float = 3.0) -> Optional[str]:
    tid = os.urandom(2)
    question = b"".join(bytes([len(p)]) + p.encode("ascii") for p in host.split(".")) + b"\x00\x00\x01\x00\x01"
    packet = tid + b"\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00" + question
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        sock.sendto(packet, (server, 53))
        data, _ = sock.recvfrom(1024)
    if data[:2] != tid:
        return None
    answers = struct.unpack("!H", data[6:8])[0]
    pos = len(packet)
    for _ in range(answers):
        while True:  # Name überspringen (Labels oder Kompressionszeiger)
            length = data[pos]
            if length & 0xC0 == 0xC0:
                pos += 2
                break
            pos += 1 + length
            if length == 0:
                break
        rtype, _rclass, _ttl, rdlen = struct.unpack("!HHIH", data[pos:pos + 10])
        pos += 10
        if rtype == 1 and rdlen == 4:
            return socket.inet_ntoa(data[pos:pos + 4])
        pos += rdlen
    return None


def _resolve_override(url: str) -> Optional[str]:
    """Liefert `host:port:ip` für git, wenn der System-DNS den Host nicht auflöst."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return None
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        socket.getaddrinfo(host, port)
        return None
    except OSError:
        pass
    for server in PUBLIC_DNS:
        try:
            ip = _dns_query(host, server)
        except (OSError, struct.error, IndexError):
            continue
        if ip:
            logger.info(f"System-DNS löst {host} nicht auf - nutze {ip} (von {server})")
            return f"{host}:{port}:{ip}"
    return None


# ============================================================================
# Git
# ============================================================================

def _git(*args: str, timeout: int = 60, config: Optional[List[str]] = None) -> str:
    cmd = ["git"]
    for entry in config or []:
        cmd += ["-c", entry]
    cmd += list(args)
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", LC_ALL="C")
    try:
        result = subprocess.run(cmd, cwd=str(REPO_DIR), env=env, capture_output=True,
                                text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    except FileNotFoundError:
        raise UpdateError("git ist nicht installiert")
    except subprocess.TimeoutExpired:
        raise UpdateError(f"git {args[0]}: Zeitüberschreitung")
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        raise UpdateError(f"git {args[0]}: {detail[-1] if detail else result.returncode}")
    return result.stdout.strip()


def _is_ancestor(older: str, newer: str) -> bool:
    try:
        _git("merge-base", "--is-ancestor", older, newer)
        return True
    except UpdateError:
        return False


def is_git_repo() -> bool:
    return (REPO_DIR / ".git").exists()


def current_version() -> Dict:
    """Installierter Stand (Commit, Datum, Titel)."""
    try:
        sha, date, subject = _git("log", "-1", "--format=%H%n%cI%n%s").split("\n", 2)
        return {"commit": sha, "commit_short": sha[:7], "date": date, "subject": subject}
    except (UpdateError, ValueError):
        return {"commit": None, "commit_short": None, "date": None, "subject": None}


def _local_changes(*paths: str) -> Dict[str, str]:
    """Lokal geänderte, von git verwaltete Dateien: {pfad: 'M' | 'D'}.
    Reine Rechte-Änderungen (chmod durch den Installer) zählen nicht."""
    out = _git("-c", "core.fileMode=false", "diff", "--name-status", "--no-renames", "HEAD", "--", *paths)
    changes = {}
    for line in out.splitlines():
        status, _, path = line.partition("\t")
        if path:
            changes[path] = "D" if status.startswith("D") else "M"
    return changes


def _is_user_path(path: str) -> bool:
    return path.split("/", 1)[0] in USER_PATHS


def _reset_keeping_user_files(target: str):
    """`git reset --hard target`, ohne Benutzerdaten zu verlieren.

    Alle lokal geänderten Dateien landen als Kopie in data/update_backup.
    Dateien unter data/ und game_modes/ werden danach wiederhergestellt,
    lokal geänderter Code wird durch den GitHub-Stand ersetzt."""
    changes = _local_changes()
    shutil.rmtree(BACKUP_DIR, ignore_errors=True)
    for path, kind in changes.items():
        if kind == "M" and (REPO_DIR / path).is_file():
            dest = BACKUP_DIR / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO_DIR / path, dest)

    _git("reset", "--hard", target, timeout=120)

    for path, kind in changes.items():
        if not _is_user_path(path):
            continue
        if kind == "D":
            (REPO_DIR / path).unlink(missing_ok=True)
        elif (BACKUP_DIR / path).is_file():
            (REPO_DIR / path).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(BACKUP_DIR / path, REPO_DIR / path)

    # Start-Skripte müssen ausführbar bleiben, egal was im Repo steht
    for script in REPO_DIR.glob("*.sh"):
        try:
            script.chmod(script.stat().st_mode | 0o755)
        except OSError:
            pass


def _syntax_check():
    for name in SYNTAX_CHECK_FILES:
        path = REPO_DIR / name
        if not path.exists():
            continue
        result = subprocess.run([sys.executable, "-m", "py_compile", str(path)],
                                capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            detail = result.stderr.strip().splitlines()
            raise UpdateError(f"{name} ist fehlerhaft: {detail[-1] if detail else 'Syntaxfehler'}")


# ============================================================================
# Prüfen & Installieren
# ============================================================================

_run_lock = threading.Lock()


def check_and_update(apply: bool, is_busy: Callable[[], bool] = lambda: False,
                     force: bool = False) -> Dict:
    """Prüft auf ein Update und installiert es, wenn `apply` gesetzt ist.

    Rückgabe ist der gespeicherte Status; `state` ist eines von: up_to_date,
    offline, update_available, deferred, local_changes, diverged, skipped,
    restart_pending, failed, no_git."""
    if not _run_lock.acquire(blocking=False):
        return load_status()
    try:
        return _check_and_update(apply, is_busy, force)
    except UpdateError as e:
        logger.error(f"Update fehlgeschlagen: {e}")
        return _set_status(state="failed", message=str(e), last_check=_now())
    except Exception as e:
        logger.exception("Unerwarteter Fehler im Updater")
        return _set_status(state="failed", message=str(e), last_check=_now())
    finally:
        _run_lock.release()


def _check_and_update(apply: bool, is_busy: Callable[[], bool], force: bool) -> Dict:
    if not is_git_repo():
        return _set_status(state="no_git", last_check=_now(),
                           message="Kein git-Repository - Installation per 'git clone' nötig")

    branch = load_settings()["branch"]
    local = _git("rev-parse", "HEAD")
    url = _git("remote", "get-url", "origin")
    override = _resolve_override(url)
    net_config = [f"http.curloptResolve={override}"] if override else []

    try:
        out = _git("ls-remote", "origin", f"refs/heads/{branch}", timeout=45, config=net_config)
    except UpdateError as e:
        logger.debug(f"GitHub nicht erreichbar: {e}")
        return _set_status(state="offline", message=str(e), last_check=_now())
    remote = out.split()[0] if out else ""
    if not remote:
        raise UpdateError(f"Branch '{branch}' existiert auf GitHub nicht")

    checked = {"last_check": _now(), "remote_commit": remote}
    if remote == local:
        return _set_status(state="up_to_date", message="", **checked)

    if remote == load_status().get("bad_commit") and not force:
        return _set_status(state="skipped", **checked,
                           message="Dieser Stand ist beim letzten Versuch nicht gestartet und wird übersprungen")

    if not apply:
        return _set_status(state="update_available", message="", **checked)

    if not force and is_busy():
        logger.info("Update verfügbar, aber ein Match läuft - wird später installiert")
        return _set_status(state="deferred", message="", **checked)

    _git("fetch", "--quiet", "origin", branch, timeout=600, config=net_config)
    remote = _git("rev-parse", "FETCH_HEAD")
    checked["remote_commit"] = remote

    if _is_ancestor(remote, local):
        # lokal ist bereits neuer (Entwicklungsstand)
        return _set_status(state="up_to_date", message="", **checked)
    if not _is_ancestor(local, remote):
        return _set_status(state="diverged", **checked,
                           message="Lokaler Stand weicht von GitHub ab - bitte manuell aktualisieren")

    dirty_code = [p for p in _local_changes() if not _is_user_path(p)]
    if dirty_code and not running_under_systemd():
        # Entwicklungsrechner: niemals ungesicherte Arbeit überschreiben
        return _set_status(state="local_changes", **checked,
                           message="Lokale Code-Änderungen vorhanden: " + ", ".join(dirty_code[:5]))

    changed = _git("diff", "--name-only", local, remote).splitlines()
    logger.info(f"Installiere Update {local[:7]} -> {remote[:7]} ({len(changed)} Dateien)")

    _write_json(PENDING_FILE, {"previous": local, "target": remote, "attempts": 0, "started": _now()})
    try:
        _reset_keeping_user_files(remote)
        _syntax_check()
    except Exception as e:
        logger.error(f"Update defekt, stelle {local[:7]} wieder her: {e}")
        try:
            _reset_keeping_user_files(local)
        finally:
            PENDING_FILE.unlink(missing_ok=True)
        return _set_status(state="failed", bad_commit=remote, message=str(e), **checked)

    return _set_status(
        state="restart_pending", message="", **checked,
        last_update=_now(), previous_commit=local, bad_commit=None,
        installer_changed=any(f in INSTALLER_FILES for f in changed),
        requirements_changed="requirements.txt" in changed,
        overwritten_files=dirty_code,
    )


def confirm_boot():
    """Der Server läuft stabil - ein gerade installiertes Update gilt als gelungen."""
    if PENDING_FILE.exists():
        PENDING_FILE.unlink(missing_ok=True)
        logger.info("Update erfolgreich gestartet")
    if load_status().get("state") == "restart_pending":
        _set_status(state="up_to_date", message="")


def boot_check() -> int:
    """Wird von start_server.sh vor jedem Start aufgerufen. Bootet ein frisch
    installiertes Update wiederholt nicht, wird der vorherige Stand wiederhergestellt."""
    pending = _read_json(PENDING_FILE, {})
    if not pending.get("previous"):
        return 0
    attempts = int(pending.get("attempts", 0)) + 1
    if attempts <= MAX_BOOT_ATTEMPTS:
        pending["attempts"] = attempts
        _write_json(PENDING_FILE, pending)
        return 0

    target = str(pending.get("target", ""))
    print(f"⚠️  Update {target[:7]} startet nicht - stelle {pending['previous'][:7]} wieder her")
    try:
        _reset_keeping_user_files(pending["previous"])
        _set_status(state="failed", bad_commit=target, last_check=_now(),
                    message="Update startete nicht und wurde zurückgenommen")
    except Exception as e:
        print(f"❌ Rollback fehlgeschlagen: {e}")
        _set_status(state="failed", message=f"Rollback fehlgeschlagen: {e}")
    finally:
        PENDING_FILE.unlink(missing_ok=True)
    return 0


# ============================================================================
# Hintergrund-Dienst (läuft im Server-Prozess)
# ============================================================================

class AutoUpdater:
    """Prüft im Hintergrund auf Updates und stößt nach der Installation den Neustart an."""

    def __init__(self, is_busy: Callable[[], bool], restart: Callable[[], None]):
        self._is_busy = is_busy
        self._restart = restart
        self._wake = threading.Event()
        self._manual: Optional[Dict] = None
        self._thread: Optional[threading.Thread] = None
        self.checking = False

    @property
    def auto_install(self) -> bool:
        """Automatisch installiert wird nur auf dem Pi (systemd-Dienst), nie auf
        einem Entwicklungsrechner. OPENPADEL_AUTOUPDATE=1 erzwingt es."""
        if os.environ.get("OPENPADEL_AUTOUPDATE") == "0":
            return False
        return load_settings()["enabled"] and (
            running_under_systemd() or os.environ.get("OPENPADEL_AUTOUPDATE") == "1")

    def start(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, name="auto-updater", daemon=True)
            self._thread.start()

    def request(self, apply: bool, force: bool = False):
        """Manuelle Prüfung/Installation aus dem Admin-Panel."""
        self._manual = {"apply": apply, "force": force}
        self._wake.set()

    def status(self) -> Dict:
        settings = load_settings()
        status = load_status()
        return {
            **settings,
            "auto_install": self.auto_install,
            "checking": self.checking,
            "match_running": self._is_busy(),
            "current": current_version(),
            "state": status.get("state", "unknown"),
            "message": status.get("message", ""),
            "remote_commit": status.get("remote_commit"),
            "last_check": status.get("last_check"),
            "last_update": status.get("last_update"),
            "previous_commit": status.get("previous_commit"),
            "installer_changed": bool(status.get("installer_changed")),
        }

    def _loop(self):
        # Erst abwarten, ob der (evtl. frisch aktualisierte) Server stabil läuft
        time.sleep(BOOT_CONFIRM_SECONDS)
        try:
            confirm_boot()
        except Exception as e:
            logger.warning(f"Update-Bestätigung fehlgeschlagen: {e}")

        while True:
            manual, self._manual = self._manual, None
            self._wake.clear()
            apply = manual["apply"] if manual else self.auto_install
            force = bool(manual and manual["force"])

            self.checking = True
            try:
                result = check_and_update(apply, self._is_busy, force)
            finally:
                self.checking = False

            state = result.get("state")
            if state == "restart_pending":
                if running_under_systemd():
                    logger.info("Update installiert - Server startet neu")
                    self._restart()
                    return
                logger.warning("Update installiert - bitte den Server neu starten")

            wait = DEFERRED_RETRY_SECONDS if state == "deferred" else load_settings()["interval_minutes"] * 60
            self._wake.wait(wait)


# ============================================================================
# Kommandozeile
# ============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    arg = sys.argv[1] if len(sys.argv) > 1 else "--check"
    if arg == "--boot-check":
        sys.exit(boot_check())
    if arg in ("--check", "--apply"):
        outcome = check_and_update(apply=(arg == "--apply"), force=(arg == "--apply"))
        print(json.dumps(outcome, indent=2, ensure_ascii=False))
        if outcome.get("state") == "restart_pending":
            print("Neustart nötig: sudo systemctl restart padel-server padel-display")
        sys.exit(0 if outcome.get("state") != "failed" else 1)
    print(__doc__)
    sys.exit(2)
