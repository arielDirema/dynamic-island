"""Windows mobile hotspot (connection sharing) and local-network devices.

- Hotspot: on/off, name, password, band, connected devices (name, IP, MAC).
- Blocking: Windows cannot eject a single hotspot client. Blocking a device therefore changes
  the password and restarts the hotspot: the blocked device loses access, others reconnect
  with the new password (shown as a QR code). If it comes back anyway, it is reported.
- Local network: devices on the current Wi-Fi (IP, MAC, name). Read-only: blocking on a
  network where this PC is only a client is done in the router administration."""
import asyncio
import ipaddress
import re
import secrets
import socket
import string
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import psutil
from PySide6.QtCore import QObject, Signal

from dynamic_island.core.config.settings import settings
from dynamic_island.core.localization import translate as tr

NOWIN = 0x08000000
STATUS_KEYS = {
    1: "hotspot.status.unknown_error",
    2: "hotspot.status.no_mobile_network",
    3: "hotspot.status.adapter_unavailable",
    4: "hotspot.status.timeout",
    5: "hotspot.status.provider_refused",
    6: "hotspot.status.busy",
    7: "hotspot.status.bluetooth_off",
    8: "hotspot.status.no_internet",
}
def _run(*args):
    r = subprocess.run(list(args), capture_output=True, creationflags=NOWIN)
    for enc in ("utf-8", "cp850", "cp1252"):
        try:
            return r.stdout.decode(enc)
        except UnicodeDecodeError:
            continue
    return r.stdout.decode("utf-8", "replace")


def arp_table():
    """{ip: mac} for dynamic entries in the ARP table."""
    out = {}
    for line in _run("arp", "-a").splitlines():
        m = re.match(r"\s*(\d+\.\d+\.\d+\.\d+)\s+([0-9a-f]{2}(?:-[0-9a-f]{2}){5})\s+(\w+)", line, re.I)
        if m and m.group(2).lower() != "ff-ff-ff-ff-ff-ff" and not m.group(1).startswith(("224.", "239.", "255.")):
            out[m.group(1)] = m.group(2).lower().replace("-", ":")
    return out


def _mac_norm(mac):
    return mac.lower().replace("-", ":")


def random_password(n=12):
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(n))


class Hotspot(QObject):
    changed = Signal()
    alert = Signal(str, str, bool)

    def __init__(self):
        super().__init__()
        self.state = None          # "on" | "off" | "transition" | None (unavailable)
        self.ssid = ""
        self.password = ""
        self.band = 0
        self.max_clients = 8
        self.clients = []          # [{mac, name, ip, blocked}]
        self.error = None
        self.busy = False
        self.visible = False
        self.lan = []              # local-network devices
        self.lan_scanning = False
        self.lan_info = {}
        self._wake = threading.Event()
        threading.Thread(target=self._loop, daemon=True).start()

    @staticmethod
    def _manager():
        from winrt.windows.networking.connectivity import NetworkInformation
        from winrt.windows.networking.networkoperators import NetworkOperatorTetheringManager as M
        prof = NetworkInformation.get_internet_connection_profile()
        if prof is None:
            return None
        return M.create_from_connection_profile(prof)

    def _read(self):
        m = self._manager()
        if m is None:
            self.state, self.error = None, tr("hotspot.no_internet_to_share")
            return
        st = int(m.tethering_operational_state)
        self.state = {1: "on", 2: "off", 3: "transition"}.get(st)
        cfg = m.get_current_access_point_configuration()
        self.ssid, self.password, self.band = cfg.ssid, cfg.passphrase, int(cfg.band)
        self.max_clients = m.max_client_count
        blocked = set(settings.get("hotspot_blocked", []))
        clients = []
        if self.state == "on":
            arp = {_mac_norm(mac): ip for ip, mac in arp_table().items() if ip.startswith("192.168.137.")}
            for c in m.get_tethering_clients():
                mac = _mac_norm(c.mac_address)
                names = [h.display_name for h in c.host_names]
                ip = next((n for n in names if re.match(r"\d+\.\d+\.\d+\.\d+$", n)), None) or arp.get(mac)
                name = next((n for n in names if not re.match(r"[\d.:a-f]+$", n, re.I)), None)
                clients.append({"mac": mac, "name": name or tr("controls.bluetooth.kind.device"),
                                "ip": ip, "blocked": mac in blocked})
            for c in clients:
                if c["blocked"]:
                    self.alert.emit(tr("hotspot.blocked_reconnected"),
                                    f"{c['name']} · {c['mac']}", False)
        self.clients = clients

    def _loop(self):
        while True:
            try:
                self._read()
            except Exception as e:
                self.state, self.error = None, tr("hotspot.unavailable", error=type(e).__name__)
            self.changed.emit()
            self._wake.wait(2 if self.visible else 20)
            self._wake.clear()

    def refresh(self):
        self._wake.set()

    def _async(self, coro_fn, done_msg=None):
        def work():
            self.busy = True
            self.changed.emit()
            try:
                asyncio.run(coro_fn())
                if done_msg:
                    self.alert.emit(done_msg[0], done_msg[1], True)
            except Exception as e:
                self.error = str(e)[:120]
                self.alert.emit(tr("hotspot.title"), self.error, False)
            self.busy = False
            try:
                self._read()
            except Exception:
                pass
            self.changed.emit()
        threading.Thread(target=work, daemon=True).start()

    async def _start(self):
        m = self._manager()
        r = await m.start_tethering_async()
        st = int(r.status)
        if st != 0:
            self.error = tr(STATUS_KEYS.get(st, "hotspot.status.failed"), code=st)
            self.alert.emit(tr("hotspot.start_failed"), self.error.split(" (")[0], False)
        else:
            self.error = None
            self.alert.emit(tr("hotspot.started"), self.ssid, True)

    async def _stop(self):
        m = self._manager()
        await m.stop_tethering_async()
        self.error = None

    def toggle(self):
        self._async(self._stop if self.state == "on" else self._start)

    def configure(self, ssid=None, password=None, band=None, restart=None):
        """Change name, password or band (8 characters minimum); restart if the hotspot was on."""
        async def run():
            m = self._manager()
            cfg = m.get_current_access_point_configuration()
            if ssid:
                cfg.ssid = ssid
            if password:
                cfg.passphrase = password
            if band is not None:
                cfg.band = band
            was_on = int(m.tethering_operational_state) == 1
            await m.configure_access_point_async(cfg)
            if (restart if restart is not None else was_on) and was_on:
                await m.stop_tethering_async()
                await asyncio.sleep(1)
                await m.start_tethering_async()
        self._async(run, (tr("hotspot.updated"), ssid or self.ssid))

    def block(self, client):
        """Block a device: new password + restart (Windows cannot eject a single device)."""
        blocked = set(settings.get("hotspot_blocked", []))
        blocked.add(client["mac"])
        names = dict(settings.get("hotspot_blocked_names", {}))
        names[client["mac"]] = client["name"]
        settings.set("hotspot_blocked", sorted(blocked))
        settings.set("hotspot_blocked_names", names)
        self.configure(password=random_password(), restart=True)
        self.alert.emit(tr("hotspot.device_blocked"),
                        tr("hotspot.new_password_hint", name=client["name"]), True)

    def unblock(self, mac):
        settings.set("hotspot_blocked", [m for m in settings.get("hotspot_blocked", []) if m != mac])
        self.changed.emit()

    @property
    def blocked(self):
        names = settings.get("hotspot_blocked_names", {})
        return [{"mac": m, "name": names.get(m, tr("controls.bluetooth.kind.device"))}
                for m in settings.get("hotspot_blocked", [])]

    def scan_lan(self):
        if self.lan_scanning:
            return

        def work():
            self.lan_scanning = True
            self.changed.emit()
            try:
                self.lan = self._scan_lan()
            except Exception as e:
                self.lan_info["error"] = str(e)[:80]
            self.lan_scanning = False
            self.changed.emit()
        threading.Thread(target=work, daemon=True).start()

    def _scan_lan(self):
        # current interface: the one routing to the Internet
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            my_ip = s.getsockname()[0]
        finally:
            s.close()
        mask = "255.255.255.0"
        my_mac = None
        for name, addrs in psutil.net_if_addrs().items():
            if any(a.address == my_ip for a in addrs):
                mask = next((a.netmask for a in addrs if a.address == my_ip), mask)
                my_mac = next((a.address for a in addrs if a.family == psutil.AF_LINK), None)
        net = ipaddress.ip_network(f"{my_ip}/{mask}", strict=False)
        if net.num_addresses > 1024:  # large networks: limit to the /24 around us
            net = ipaddress.ip_network(f"{my_ip}/24", strict=False)
        gw = None
        for line in _run("route", "print", "-4", "0.0.0.0").splitlines():
            m = re.match(r"\s*0\.0\.0\.0\s+0\.0\.0\.0\s+(\d+\.\d+\.\d+\.\d+)\s+(\d+\.\d+\.\d+\.\d+)", line)
            if m and m.group(2) == my_ip:
                gw = m.group(1)
                break
        self.lan_info = {"ip": my_ip, "net": str(net), "gateway": gw}
        # wake the ARP table: a small UDP packet to every address
        u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        for host in net.hosts():
            try:
                u.sendto(b"\x00", (str(host), 9))
            except OSError:
                pass
        u.close()
        time.sleep(2.0)
        arp = {ip: mac for ip, mac in arp_table().items() if ipaddress.ip_address(ip) in net}
        arp[my_ip] = _mac_norm(my_mac) if my_mac else ""

        def name_of(ip):
            if ip == my_ip:
                return socket.gethostname()
            try:
                return socket.gethostbyaddr(ip)[0].split(".")[0]
            except OSError:
                return None
        with ThreadPoolExecutor(32) as ex:
            names = dict(zip(arp, ex.map(name_of, arp)))
        devices = []
        for ip, mac in arp.items():
            kind = "self" if ip == my_ip else ("router" if ip == gw else "device")
            devices.append({"ip": ip, "mac": mac, "name": names.get(ip), "kind": kind})
        devices.sort(key=lambda d: ({"router": 0, "self": 1}.get(d["kind"], 2), tuple(int(x) for x in d["ip"].split("."))))
        return devices
