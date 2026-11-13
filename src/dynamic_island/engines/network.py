"""Wi-Fi and Bluetooth panels: visible networks (connect, password, disconnect, forget)
and paired Bluetooth devices (state, connect/disconnect for headsets and speakers)."""
import asyncio
import ctypes
import os
import re
import subprocess
import tempfile
import threading
import time
from ctypes import wintypes
from xml.sax.saxutils import escape

from PySide6.QtCore import QObject, Signal

from dynamic_island.core.config.settings import settings
from dynamic_island.core.localization import translate as tr

NOWIN = 0x08000000


def _netsh(*args):
    r = subprocess.run(["netsh", *args], capture_output=True, creationflags=NOWIN)
    raw = r.stdout
    for enc in ("utf-8", "cp850", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


class _GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8)]


class _WLAN_INTERFACE_INFO(ctypes.Structure):
    _fields_ = [("InterfaceGuid", _GUID), ("strInterfaceDescription", wintypes.WCHAR * 256), ("isState", wintypes.DWORD)]


class _WLAN_INTERFACE_INFO_LIST(ctypes.Structure):
    _fields_ = [("dwNumberOfItems", wintypes.DWORD), ("dwIndex", wintypes.DWORD),
                ("InterfaceInfo", _WLAN_INTERFACE_INFO * 8)]


def wlan_scan():
    """Ask the Wi-Fi adapter for a new scan (results arrive after 2-4 s)."""
    try:
        wl = ctypes.windll.wlanapi
        ver, h = wintypes.DWORD(), wintypes.HANDLE()
        if wl.WlanOpenHandle(2, None, ctypes.byref(ver), ctypes.byref(h)):
            return
        plist = ctypes.POINTER(_WLAN_INTERFACE_INFO_LIST)()
        if not wl.WlanEnumInterfaces(h, None, ctypes.byref(plist)):
            for i in range(plist.contents.dwNumberOfItems):
                g = plist.contents.InterfaceInfo[i].InterfaceGuid
                wl.WlanScan(h, ctypes.byref(g), None, None, None)
            wl.WlanFreeMemory(plist)
        wl.WlanCloseHandle(h, None)
    except Exception:
        pass


def wifi_current():
    out = _netsh("wlan", "show", "interfaces")
    ssid = re.search(r"^\s*SSID\s*:\s*(.+?)\s*$", out, re.M)
    sig = re.search(r"^\s*Signal\s*:\s*(\d+)\s*%", out, re.M)
    state = re.search(r"^\s*(?:État|Etat|State)\s*:\s*(.+?)\s*$", out, re.M)
    connected = bool(state and re.search(r"connect", state.group(1), re.I) and not re.search(r"d[ée]connect|disconnect",
                                                                                            state.group(1), re.I))
    return {"ssid": ssid.group(1) if (ssid and connected) else None, "signal": int(sig.group(1)) if sig else None}


def wifi_profiles():
    out = _netsh("wlan", "show", "profiles")
    names = set()
    for line in out.splitlines():
        if ":" in line and re.match(r"^\s+(Profil|Profile|All User Profile|User Profile)", line, re.I):
            n = line.split(":", 1)[1].strip()
            if n:
                names.add(n)
    return names


def wifi_networks():
    out = _netsh("wlan", "show", "networks", "mode=bssid")
    nets, cur = [], None
    for line in out.splitlines():
        m = re.match(r"^SSID \d+\s*:\s*(.*?)\s*$", line)
        if m:
            cur = {"ssid": m.group(1), "auth": "", "signal": 0}
            if cur["ssid"]:
                nets.append(cur)
            continue
        if cur is None:
            continue
        m = re.match(r"^\s*(?:Authentification|Authentication)\s*:\s*(.+?)\s*$", line)
        if m:
            cur["auth"] = m.group(1).replace(" ", " ")
            continue
        m = re.match(r"^\s*Signal\s*:\s*(\d+)\s*%", line)
        if m:
            cur["signal"] = max(cur["signal"], int(m.group(1)))
    for n in nets:
        a = n["auth"].lower()
        n["open"] = a.startswith(("ouvr", "open")) or a == ""
        n["wpa3"] = "wpa3" in a
    nets.sort(key=lambda n: -n["signal"])
    return nets


def _profile_xml(ssid, password, wpa3=False):
    s = escape(ssid)
    if password is None:
        sec = "<authEncryption><authentication>open</authentication><encryption>none</encryption>" \
              "<useOneX>false</useOneX></authEncryption>"
    else:
        auth = "WPA3SAE" if wpa3 else "WPA2PSK"
        sec = (f"<authEncryption><authentication>{auth}</authentication><encryption>AES</encryption>"
               f"<useOneX>false</useOneX></authEncryption><sharedKey><keyType>passPhrase</keyType>"
               f"<protected>false</protected><keyMaterial>{escape(password)}</keyMaterial></sharedKey>")
    return (f'<?xml version="1.0"?><WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">'
            f"<name>{s}</name><SSIDConfig><SSID><name>{s}</name></SSID></SSIDConfig><connectionType>ESS</connectionType>"
            f"<connectionMode>auto</connectionMode><MSM><security>{sec}</security></MSM></WLANProfile>")


_bt = None


class _SYSTEMTIME(ctypes.Structure):
    _fields_ = [(n, wintypes.WORD) for n in ("y", "mo", "dow", "d", "h", "mi", "s", "ms")]


class _BT_DEVICE_INFO(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("Address", ctypes.c_ulonglong), ("ulClassofDevice", wintypes.ULONG),
                ("fConnected", wintypes.BOOL), ("fRemembered", wintypes.BOOL), ("fAuthenticated", wintypes.BOOL),
                ("stLastSeen", _SYSTEMTIME), ("stLastUsed", _SYSTEMTIME), ("szName", wintypes.WCHAR * 248)]


class _FIND_RADIO(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD)]


def _svc(short):
    g = _GUID(short, 0x0000, 0x1000)
    for i, b in enumerate((0x80, 0x00, 0x00, 0x80, 0x5F, 0x9B, 0x34, 0xFB)):
        g.Data4[i] = b
    return g


AUDIO_SERVICES = (0x110B, 0x111E)  # AudioSink (musique), Handsfree (appels)


def _bt_set_services(address, enable):
    global _bt
    if _bt is None:
        _bt = ctypes.WinDLL("bthprops.cpl")
        _bt.BluetoothFindFirstRadio.restype = wintypes.HANDLE
    p = _FIND_RADIO(ctypes.sizeof(_FIND_RADIO))
    radio = wintypes.HANDLE()
    hf = _bt.BluetoothFindFirstRadio(ctypes.byref(p), ctypes.byref(radio))
    if not hf:
        return False
    info = _BT_DEVICE_INFO()
    info.dwSize = ctypes.sizeof(info)
    info.Address = address
    if _bt.BluetoothGetDeviceInfo(radio, ctypes.byref(info)):
        return False
    ok = False
    for s in AUDIO_SERVICES:
        g = _svc(s)
        if enable:  # disable then re-enable: Windows restarts the audio connection
            _bt.BluetoothSetServiceState(radio, ctypes.byref(info), ctypes.byref(g), 0)
            time.sleep(0.4)
            ok |= _bt.BluetoothSetServiceState(radio, ctypes.byref(info), ctypes.byref(g), 1) == 0
        else:
            ok |= _bt.BluetoothSetServiceState(radio, ctypes.byref(info), ctypes.byref(g), 0) == 0
    ctypes.windll.kernel32.CloseHandle(radio)
    _bt.BluetoothFindRadioClose(wintypes.HANDLE(hf))
    return ok


def _bt_kind(major, minor):
    if major == 4:
        return "audio"
    if major == 2:
        return "phone"
    if major == 5:
        return "input"
    if major == 1:
        return "computer"
    return "other"


class Networks(QObject):
    changed = Signal()
    alert = Signal(str, str, str, bool)  # kind, title, subtitle, success

    def __init__(self):
        super().__init__()
        self.wifi = []
        self.wifi_cur = {"ssid": None, "signal": None}
        self.profiles = set()
        self.wifi_busy = None      # SSID currently connecting
        self.wifi_scanning = False
        self.bt = []
        self.bt_busy = None
        self.bt_loading = False

    def scan_wifi(self, active=True):
        if self.wifi_scanning:
            return

        def work():
            self.wifi_scanning = True
            self.changed.emit()
            try:
                self.wifi_cur = wifi_current()
                self.profiles = wifi_profiles()
                self.wifi = wifi_networks()
                self.changed.emit()
                if active:
                    wlan_scan()
                    time.sleep(3)
                    self.wifi = wifi_networks()
                    self.wifi_cur = wifi_current()
            except Exception:
                pass
            self.wifi_scanning = False
            self.changed.emit()
        threading.Thread(target=work, daemon=True).start()

    def known(self, ssid):
        return ssid in self.profiles

    def connect_wifi(self, net, password=None):
        ssid = net["ssid"]

        def work():
            self.wifi_busy = ssid
            self.changed.emit()
            try:
                if password is not None or (net["open"] and not self.known(ssid)):
                    xml = _profile_xml(ssid, None if net["open"] else password, net.get("wpa3"))
                    fd, path = tempfile.mkstemp(suffix=".xml")
                    try:
                        with os.fdopen(fd, "w", encoding="utf-8") as f:
                            f.write(xml)
                        _netsh("wlan", "add", "profile", f"filename={path}", "user=current")
                    finally:
                        os.remove(path)  # the file contains the password
                _netsh("wlan", "connect", f"name={ssid}", f"ssid={ssid}")
                ok = False
                for _ in range(20):
                    time.sleep(0.75)
                    cur = wifi_current()
                    if cur["ssid"] == ssid:
                        ok = True
                        break
                self.wifi_cur = wifi_current()
                self.profiles = wifi_profiles()
                if ok:
                    self.alert.emit("wifi", tr("network.wifi.connected"), ssid, True)
                else:
                    message = ssid + (" · " + tr("network.wifi.bad_password") if password else "")
                    self.alert.emit("wifi", tr("network.wifi.connect_failed"), message, False)
                    if password is not None:  # profile created with a wrong password: remove it
                        _netsh("wlan", "delete", "profile", f"name={ssid}")
                        self.profiles.discard(ssid)
            except Exception as e:
                self.alert.emit("wifi", tr("network.wifi.error"), str(e)[:60], False)
            self.wifi_busy = None
            self.changed.emit()
        threading.Thread(target=work, daemon=True).start()

    def disconnect_wifi(self):
        def work():
            _netsh("wlan", "disconnect")
            time.sleep(1)
            self.wifi_cur = wifi_current()
            self.changed.emit()
        threading.Thread(target=work, daemon=True).start()

    def forget_wifi(self, ssid):
        def work():
            _netsh("wlan", "delete", "profile", f"name={ssid}")
            self.profiles = wifi_profiles()
            self.changed.emit()
        threading.Thread(target=work, daemon=True).start()

    def refresh_bt(self):
        if self.bt_loading:
            return

        def work():
            self.bt_loading = True
            self.changed.emit()
            try:
                self.bt = asyncio.run(self._bt_list())
            except Exception:
                pass
            self.bt_loading = False
            self.changed.emit()
        threading.Thread(target=work, daemon=True).start()

    async def _bt_list(self):
        from winrt.windows.devices.bluetooth import BluetoothDevice, BluetoothLEDevice
        from winrt.windows.devices.enumeration import DeviceInformation
        out, seen = [], set()
        off = set(settings.get("bt_off", []))
        for le, cls in ((False, BluetoothDevice), (True, BluetoothLEDevice)):
            infos = await DeviceInformation.find_all_async_aqs_filter(cls.get_device_selector_from_pairing_state(True))
            for i in infos:
                try:
                    d = await cls.from_id_async(i.id)
                    if d is None:
                        continue
                    name = i.name or d.name
                    if le and name in seen:
                        continue  # already listed through classic Bluetooth
                    seen.add(name)
                    if le:
                        kind = "input" if d.appearance.category in (15, 16) else "other"
                    else:
                        kind = _bt_kind(d.class_of_device.major_class, d.class_of_device.minor_class)
                    out.append({"name": name, "address": d.bluetooth_address, "kind": kind, "le": le,
                                "connected": int(d.connection_status) == 1,
                                "off": d.bluetooth_address in off})
                except Exception:
                    # radio off or device unreachable: still list it, without actions
                    if i.name and i.name not in seen and not le:
                        seen.add(i.name)
                        out.append({"name": i.name, "address": None, "kind": "other", "le": le,
                                    "connected": False, "off": False})
        out.sort(key=lambda x: (not x["connected"], x["kind"] != "audio", x["name"].lower()))
        return out

    @staticmethod
    async def _bt_connected(address):
        from winrt.windows.devices.bluetooth import BluetoothDevice
        try:
            d = await BluetoothDevice.from_bluetooth_address_async(address)
            return d is not None and int(d.connection_status) == 1
        except Exception:
            return False

    def bt_toggle(self, dev):
        connect = not dev["connected"]

        def work():
            self.bt_busy = dev["address"]
            self.changed.emit()
            ok = _bt_set_services(dev["address"], connect)
            off = [a for a in settings.get("bt_off", []) if a != dev["address"]]
            if not connect and ok:
                off.append(dev["address"])
            settings.set("bt_off", off)
            done = False
            for _ in range(14 if connect else 6):  # ~10 s connection timeout
                time.sleep(0.7)
                if asyncio.run(self._bt_connected(dev["address"])) == connect:
                    done = True
                    break
            self.bt = asyncio.run(self._bt_list())
            if connect:
                self.alert.emit("bt", tr("network.bt.connected") if done else tr("network.bt.connect_failed"),
                                dev["name"] + ("" if done else " · " + tr("network.bt.check_hint")), done)
            else:
                self.alert.emit("bt", tr("network.bt.disconnected") if done or ok
                                else tr("network.bt.disconnect_failed"), dev["name"], done or ok)
            self.bt_busy = None
            self.changed.emit()
        threading.Thread(target=work, daemon=True).start()
