#!/usr/bin/env python3
"""
WiFi Access Point Setup für Raspberry Pi
Startet automatisch beim Booten und erstellt einen WiFi Access Point
"""

import os
import subprocess
import sys
import time
import logging
from typing import Optional

# Logging konfigurieren
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/wifi_ap.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


def get_serial_number() -> str:
    """Holt die letzten 8 Stellen der Raspberry Pi Seriennummer"""
    try:
        with open('/proc/cpuinfo', 'r') as f:
            for line in f:
                if line.startswith('Serial'):
                    serial = line.split(':')[1].strip()
                    # Nimm die letzten 8 Zeichen
                    return serial[-8:]
    except Exception as e:
        logger.warning(f"Konnte Seriennummer nicht auslesen: {e}")
        # Fallback: Verwende MAC-Adresse
        try:
            result = subprocess.run(['cat', '/sys/class/net/wlan0/address'],
                                  capture_output=True, text=True)
            if result.returncode == 0:
                mac = result.stdout.strip().replace(':', '')
                return mac[-8:]
        except Exception:
            pass

    # Letzter Fallback
    return "00000000"


class WiFiAccessPoint:
    def __init__(self, ssid: str = None, password: str = "openpadel", interface: str = "wlan0"):
        """
        Initialisiert den WiFi Access Point

        Args:
            ssid: Name des WiFi-Netzwerks (None = automatisch mit Seriennummer)
            password: Passwort (mindestens 8 Zeichen)
            interface: WiFi Interface (normalerweise wlan0)
        """
        # Wenn kein SSID angegeben, generiere aus Seriennummer
        if ssid is None:
            serial_suffix = get_serial_number()
            ssid = f"openPadel_{serial_suffix}"

        self.ssid = ssid
        self.password = password
        self.interface = interface
        self.ip_address = "10.20.1.1"
        self.subnet = "10.20"

        if len(password) < 8:
            raise ValueError("Passwort muss mindestens 8 Zeichen lang sein")

    def run_command(self, cmd: list, check: bool = True) -> subprocess.CompletedProcess:
        """Führt einen Systembefehl aus"""
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=check)
            if result.stdout:
                logger.debug(f"Command output: {result.stdout}")
            return result
        except subprocess.CalledProcessError as e:
            logger.error(f"Command failed: {' '.join(cmd)}")
            logger.error(f"Error: {e.stderr}")
            raise

    def check_requirements(self) -> bool:
        """Prüft ob alle notwendigen Pakete installiert sind"""
        required_packages = ['hostapd', 'dnsmasq']
        missing_packages = []

        for package in required_packages:
            result = self.run_command(['which', package], check=False)
            if result.returncode != 0:
                missing_packages.append(package)

        if missing_packages:
            logger.error(f"Fehlende Pakete: {', '.join(missing_packages)}")
            logger.error("Installiere mit: sudo apt-get install hostapd dnsmasq")
            return False
        return True

    def create_hostapd_config(self) -> None:
        """Erstellt die hostapd Konfigurationsdatei"""
        config = f"""interface={self.interface}
#driver=nl80211
ssid={self.ssid}
hw_mode=g
channel=1
ieee80211n=1
ieee80211d=1
wmm_enabled=1
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase={self.password}
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
"""

        config_path = "/etc/hostapd/hostapd.conf"
        logger.info(f"Erstelle hostapd Konfiguration in {config_path}")

        try:
            # Backup erstellen falls Datei existiert
            if os.path.exists(config_path):
                backup_path = f"{config_path}.old"
                self.run_command(['cp', config_path, backup_path], check=False)
                logger.info(f"Backup erstellt: {backup_path}")

            with open(config_path, 'w') as f:
                f.write(config)

            # Setze Berechtigungen
            os.chmod(config_path, 0o600)

            # Setze hostapd config path in /etc/default/hostapd
            default_hostapd = '/etc/default/hostapd'
            if os.path.exists(default_hostapd):
                with open(default_hostapd, 'r') as f:
                    content = f.read()

                if 'DAEMON_CONF' not in content or '#DAEMON_CONF' in content:
                    with open(default_hostapd, 'a') as f:
                        f.write(f'\nDAEMON_CONF="{config_path}"\n')

            logger.info("hostapd Konfiguration erstellt")
        except PermissionError:
            logger.error("FEHLER: Benötige Root-Rechte. Bitte mit 'sudo' ausführen")
            sys.exit(1)

    def create_dnsmasq_config(self) -> None:
        """Erstellt die dnsmasq Konfigurationsdatei"""
        config = f"""# DHCP-Server aktiv für WLAN-Interface
interface={self.interface}

# DHCP-Server nicht aktiv für bestehendes Netzwerk
no-dhcp-interface=eth0

# IPv4-Adressbereich und Lease-Time
dhcp-range={self.subnet}.1.100,{self.subnet}.1.200,255.255.255.0,24h

# DNS
dhcp-option=option:dns-server,{self.ip_address}
"""

        # Backup der Original-Konfiguration
        original_config = "/etc/dnsmasq.conf"
        backup_config = "/etc/dnsmasq.conf.old"

        if os.path.exists(original_config) and not os.path.exists(backup_config):
            self.run_command(['cp', original_config, backup_config])
            logger.info(f"Backup erstellt: {backup_config}")

        logger.info(f"Erstelle dnsmasq Konfiguration in {original_config}")

        with open(original_config, 'w') as f:
            f.write(config)
        logger.info("dnsmasq Konfiguration erstellt")

    def configure_dhcpcd(self) -> None:
        """Konfiguriert dhcpcd für statische IP"""
        dhcpcd_config = "/etc/dhcpcd.conf"

        # Backup erstellen
        if os.path.exists(dhcpcd_config):
            backup_path = f"{dhcpcd_config}.old"
            if not os.path.exists(backup_path):
                self.run_command(['cp', dhcpcd_config, backup_path])
                logger.info(f"Backup erstellt: {backup_path}")

        # Neue Konfiguration erstellen
        config_block = f"""interface {self.interface}
    static ip_address={self.ip_address}/24
    nohook wpa_supplicant
"""

        with open(dhcpcd_config, 'w') as f:
            f.write(config_block)
        logger.info(f"dhcpcd konfiguriert mit statischer IP {self.ip_address}")

        # dhcpcd neu starten
        self.run_command(['systemctl', 'restart', 'dhcpcd'], check=False)

    def configure_network_interface(self) -> None:
        """Konfiguriert das Netzwerk-Interface"""
        logger.info(f"Konfiguriere {self.interface}...")

        # Stoppe NetworkManager falls aktiv
        self.run_command(['systemctl', 'stop', 'NetworkManager'], check=False)
        self.run_command(['systemctl', 'disable', 'NetworkManager'], check=False)

        # Aktiviere dhcpcd
        self.run_command(['systemctl', 'enable', 'dhcpcd'], check=False)
        self.run_command(['systemctl', 'start', 'dhcpcd'], check=False)

        # Stoppe eventuell laufende Services
        self.run_command(['systemctl', 'stop', 'hostapd'], check=False)
        self.run_command(['systemctl', 'stop', 'dnsmasq'], check=False)

        # Unmask hostapd falls es masked ist
        self.run_command(['systemctl', 'unmask', 'hostapd'], check=False)

        # Setze statische IP
        self.run_command(['ip', 'addr', 'flush', 'dev', self.interface], check=False)
        self.run_command(['ip', 'addr', 'add', f'{self.ip_address}/24', 'dev', self.interface])
        self.run_command(['ip', 'link', 'set', self.interface, 'up'])

        logger.info(f"Interface {self.interface} konfiguriert mit IP {self.ip_address}")

    def enable_ip_forwarding(self) -> None:
        """Aktiviert IP-Forwarding und NAT dauerhaft"""
        # Temporär aktivieren
        with open('/proc/sys/net/ipv4/ip_forward', 'w') as f:
            f.write('1\n')

        # Dauerhaft in sysctl.conf aktivieren
        sysctl_conf = '/etc/sysctl.conf'
        with open(sysctl_conf, 'r') as f:
            content = f.read()

        if 'net.ipv4.ip_forward=1' not in content:
            with open(sysctl_conf, 'a') as f:
                f.write('\n# Enable IP Forwarding for WiFi AP\nnet.ipv4.ip_forward=1\n')

        # NAT konfigurieren
        self.run_command(['iptables', '-t', 'nat', '-F'], check=False)  # Lösche alte Regeln
        self.run_command(['iptables', '-t', 'nat', '-A', 'POSTROUTING', '-o', 'eth0', '-j', 'MASQUERADE'])
        
        # Speichere iptables Regeln
        self.run_command(['sh', '-c', 'iptables-save > /etc/iptables.ipv4.nat'])

        logger.info("IP-Forwarding und NAT aktiviert")

    def start_services(self) -> None:
        """Startet hostapd und dnsmasq Services"""
        logger.info("Starte Services...")

        # Warte kurz
        time.sleep(2)

        # Starte dnsmasq
        result = self.run_command(['systemctl', 'restart', 'dnsmasq'], check=False)
        if result.returncode != 0:
            logger.warning(f"dnsmasq konnte nicht gestartet werden: {result.stderr}")
        else:
            logger.info("dnsmasq gestartet")

        # Warte kurz
        time.sleep(1)

        # Starte hostapd
        result = self.run_command(['systemctl', 'restart', 'hostapd'], check=False)
        if result.returncode != 0:
            logger.warning(f"hostapd konnte nicht gestartet werden: {result.stderr}")
        else:
            logger.info("hostapd gestartet")

        # Warte und prüfe Status
        time.sleep(3)
        self.check_services_status()

    def check_services_status(self) -> None:
        """Prüft den Status der Services"""
        logger.info("Prüfe Service-Status...")

        for service in ['hostapd', 'dnsmasq']:
            result = self.run_command(['systemctl', 'is-active', service], check=False)
            if result.stdout.strip() == 'active':
                logger.info(f"{service} läuft")
            else:
                logger.error(f"{service} läuft NICHT")
                # Zeige detaillierte Fehler
                result = self.run_command(['systemctl', 'status', service], check=False)
                logger.error(f"{service} Status: {result.stdout}")

    def enable_services_on_boot(self) -> None:
        """Aktiviert Services für automatischen Start beim Booten"""
        logger.info("Aktiviere Services für automatischen Start...")
        self.run_command(['systemctl', 'enable', 'hostapd'])
        self.run_command(['systemctl', 'enable', 'dnsmasq'])
        logger.info("Services für automatischen Start konfiguriert")

    def setup(self, enable_on_boot: bool = True) -> None:
        """Richtet den Access Point ein"""
        logger.info("=" * 60)
        logger.info("WiFi Access Point Setup")
        logger.info("=" * 60)
        logger.info(f"SSID: {self.ssid}")
        logger.info(f"Passwort: {self.password}")
        logger.info(f"IP-Adresse: {self.ip_address}")
        logger.info("=" * 60)

        # Prüfe Root-Rechte
        if os.geteuid() != 0:
            logger.error("FEHLER: Dieses Script muss als root ausgeführt werden")
            logger.error("Bitte verwende: sudo python3 wifi_access_point.py")
            sys.exit(1)

        # Prüfe Anforderungen
        if not self.check_requirements():
            sys.exit(1)

        # Setup durchführen
        self.create_hostapd_config()
        self.create_dnsmasq_config()
        self.configure_dhcpcd()
        self.configure_network_interface()
        self.enable_ip_forwarding()

        if enable_on_boot:
            self.enable_services_on_boot()

        self.start_services()

        logger.info("\n" + "=" * 60)
        logger.info("Setup abgeschlossen!")
        logger.info("=" * 60)
        logger.info(f"Nutzer können sich jetzt verbinden mit:")
        logger.info(f"  SSID: {self.ssid}")
        logger.info(f"  Passwort: {self.password}")
        logger.info(f"  Raspberry Pi erreichbar unter: {self.ip_address}")
        logger.info(f"  Deine App sollte auf http://{self.ip_address}:PORT laufen")
        logger.info("=" * 60)

    def start_on_boot(self) -> None:
        """Wird beim Systemstart aufgerufen"""
        logger.info("Starte WiFi Access Point beim Systemstart...")

        # Warte auf Netzwerk-Interface
        max_wait = 30
        wait_count = 0
        while wait_count < max_wait:
            result = self.run_command(['ip', 'link', 'show', self.interface], check=False)
            if result.returncode == 0:
                logger.info(f"Interface {self.interface} gefunden")
                break
            logger.info(f"Warte auf Interface {self.interface}... ({wait_count}/{max_wait})")
            time.sleep(1)
            wait_count += 1

        if wait_count >= max_wait:
            logger.error(f"Interface {self.interface} nicht gefunden!")
            sys.exit(1)

        # Konfiguriere und starte
        self.configure_network_interface()
        self.start_services()

        logger.info("WiFi Access Point erfolgreich gestartet")

    def stop(self) -> None:
        """Stoppt den Access Point"""
        logger.info("Stoppe Access Point...")
        self.run_command(['systemctl', 'stop', 'hostapd'])
        self.run_command(['systemctl', 'stop', 'dnsmasq'])
        logger.info("Access Point gestoppt")


def main():
    """Hauptfunktion"""
    import argparse

    parser = argparse.ArgumentParser(description='WiFi Access Point für Raspberry Pi')
    parser.add_argument('--ssid', default=None, help='SSID des Access Points (None = openPadel_XXXXXXXX)')
    parser.add_argument('--password', default='openpadel', help='Passwort (min. 8 Zeichen)')
    parser.add_argument('--interface', default='wlan0', help='WiFi Interface')
    parser.add_argument('--setup', action='store_true', help='Führt komplettes Setup durch')
    parser.add_argument('--start', action='store_true', help='Startet den Access Point')
    parser.add_argument('--stop', action='store_true', help='Stoppt den Access Point')

    args = parser.parse_args()

    ap = WiFiAccessPoint(
        ssid=args.ssid,
        password=args.password,
        interface=args.interface
    )

    if args.setup:
        ap.setup(enable_on_boot=True)
    elif args.start:
        ap.start_on_boot()
    elif args.stop:
        ap.stop()
    else:
        # Standard: Setup durchführen
        ap.setup(enable_on_boot=True)


if __name__ == "__main__":
    main()
