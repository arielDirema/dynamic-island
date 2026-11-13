"""Windows system controls: audio, brightness, radios, night light,
Do Not Disturb, camera, microphone, keyboard and power."""
import asyncio
import ctypes
import threading
import time
import winreg
from ctypes import wintypes

from PySide6.QtCore import QThread, Signal

from dynamic_island.core.localization import translate as tr
from dynamic_island.infrastructure.windows_api import activate_window

user32 = ctypes.windll.user32


class Audio:
    """Master volume, per-application volume, audio outputs and microphone (pycaw)."""

    def __init__(self):
        from pycaw.pycaw import AudioUtilities
        self.AU = AudioUtilities
        self._ep = None
        self._mic = None
        self.device_id = None
        self.device_name = ""
        self.refresh()

    def refresh(self):
        try:
            sp = self.AU.GetSpeakers()
            self._ep = sp.EndpointVolume
            self.device_id = sp.id
            self.device_name = sp.FriendlyName or ""
        except Exception:
            self._ep, self.device_id, self.device_name = None, None, ""
        try:
            self._mic = self.AU.CreateDevice(self.AU.GetMicrophone()).EndpointVolume
        except Exception:
            self._mic = None

    def default_id(self):
        try:
            return self.AU.GetDeviceEnumerator().GetDefaultAudioEndpoint(0, 1).GetId()
        except Exception:
            return None

    def volume(self):
        try:
            return self._ep.GetMasterVolumeLevelScalar()
        except Exception:
            return 0.0

    def set_volume(self, v):
        try:
            self._ep.SetMasterVolumeLevelScalar(max(0.0, min(1.0, v)), None)
            if v > 0 and self.muted():
                self._ep.SetMute(0, None)
        except Exception:
            pass

    def muted(self):
        try:
            return bool(self._ep.GetMute())
        except Exception:
            return False

    def toggle_mute(self):
        try:
            self._ep.SetMute(0 if self.muted() else 1, None)
        except Exception:
            pass

    def mic_available(self):
        return self._mic is not None

    def mic_muted(self):
        try:
            return bool(self._mic.GetMute())
        except Exception:
            return True

    def toggle_mic(self):
        try:
            self._mic.SetMute(0 if self.mic_muted() else 1, None)
        except Exception:
            pass

    def outputs(self):
        try:
            devs = self.AU.GetAllDevices(0, 1)  # eRender, DEVICE_STATE_ACTIVE
            return [(d.id, d.FriendlyName or tr("controls.bluetooth.kind.device")) for d in devs]
        except Exception:
            return []

    def set_output(self, dev_id):
        from pycaw.constants import ERole
        try:
            self.AU.SetDefaultDevice(dev_id, [ERole.eConsole, ERole.eMultimedia, ERole.eCommunications])
        except Exception:
            pass
        self.refresh()

    def apps(self):
        """List of [{name, sessions, volume, muted}] grouped by executable."""
        out = {}
        try:
            sessions = self.AU.GetAllSessions()
        except Exception:
            return []
        for s in sessions:
            try:
                if s.Process is None:
                    name = tr("system.sounds")
                else:
                    name = s.Process.name()
                    if name.lower().endswith(".exe"):
                        name = name[:-4]
                    name = {"msedge": "Edge", "msedgewebview2": "WebView", "zen": "Zen",
                            "explorer": "Explorateur"}.get(name.lower(), name[:1].upper() + name[1:])
                sv = s.SimpleAudioVolume
                if name not in out:
                    out[name] = {"name": name, "sessions": [], "volume": sv.GetMasterVolume(),
                                 "muted": bool(sv.GetMute())}
                out[name]["sessions"].append(sv)
            except Exception:
                continue
        return sorted(out.values(), key=lambda a: (a["name"] == tr("system.sounds"), a["name"].lower()))

    @staticmethod
    def set_app_volume(app, v):
        for sv in app["sessions"]:
            try:
                sv.SetMasterVolume(max(0.0, min(1.0, v)), None)
            except Exception:
                pass
        app["volume"] = v

    @staticmethod
    def toggle_app_mute(app):
        m = not app["muted"]
        for sv in app["sessions"]:
            try:
                sv.SetMute(1 if m else 0, None)
            except Exception:
                pass
        app["muted"] = m


class Brightness:
    """Brightness through WMI (laptop display), in a dedicated thread to keep the UI responsive."""

    def __init__(self):
        self.value = None  # 0-100 or None when unsupported
        self._target = None
        self._event = threading.Event()
        self._last_read = 0
        threading.Thread(target=self._run, daemon=True).start()

    def set(self, v):
        self.value = int(max(0, min(100, v)))
        self._target = self.value
        self._event.set()

    def request_refresh(self):
        self._event.set()

    def _run(self):
        try:
            import pythoncom
            pythoncom.CoInitialize()
        except Exception:
            pass
        import screen_brightness_control as sbc
        first = True
        while True:
            if not first:
                self._event.wait()   # on demand only (WMI is expensive)
                self._event.clear()
            first = False
            try:
                if self._target is not None:
                    t, self._target = self._target, None
                    sbc.set_brightness(t, display=0)
                    self._last_read = time.time()
                elif time.time() - self._last_read > 1:
                    self.value = sbc.get_brightness(display=0)[0]
                    self._last_read = time.time()
            except Exception:
                pass


class RadioWorker(QThread):
    updated = Signal(object)  # {"wifi": bool|None, "bluetooth": bool|None}

    def __init__(self):
        super().__init__()
        self.loop = None
        self.radios = {}
        self._running = True
        self._saved = None  # states before airplane mode

    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._main())

    def stop(self):
        self._running = False
        self.wait(2500)

    async def _main(self):
        from winrt.windows.devices.radios import Radio, RadioKind
        try:
            await Radio.request_access_async()
        except Exception:
            pass
        while self._running:
            try:
                radios = {}
                for r in await Radio.get_radios_async():
                    if r.kind == RadioKind.WI_FI:
                        radios["wifi"] = r
                    elif r.kind == RadioKind.BLUETOOTH:
                        radios["bluetooth"] = r
                self.radios = radios
                self.updated.emit(self.state())
            except Exception:
                pass
            await asyncio.sleep(2)

    def state(self):
        from winrt.windows.devices.radios import RadioState
        out = {"wifi": None, "bluetooth": None}
        for k, r in self.radios.items():
            try:
                out[k] = r.state == RadioState.ON
            except Exception:
                pass
        return out

    def _submit(self, coro):
        if self.loop is not None:
            asyncio.run_coroutine_threadsafe(coro, self.loop)

    async def _set(self, kind, on):
        from winrt.windows.devices.radios import RadioState
        r = self.radios.get(kind)
        if r is not None:
            try:
                await r.set_state_async(RadioState.ON if on else RadioState.OFF)
            except Exception:
                pass
        self.updated.emit(self.state())

    def set_radio(self, kind, on):
        self._submit(self._set(kind, on))

    def airplane_on(self):
        st = self.state()
        return bool(self.radios) and all(v is False for v in st.values() if v is not None)

    def set_airplane(self, on):
        async def do():
            if on:
                self._saved = self.state()
                for k in list(self.radios):
                    await self._set(k, False)
            else:
                saved = self._saved or {"wifi": True, "bluetooth": True}
                for k in list(self.radios):
                    await self._set(k, saved.get(k) is not False)
                self._saved = None
        self._submit(do())


_NL_KEY = (r"Software\Microsoft\Windows\CurrentVersion\CloudStore\Store\DefaultAccount\Current"
           r"\default$windows.data.bluelightreduction.bluelightreductionstate"
           r"\windows.data.bluelightreduction.bluelightreductionstate")


def night_light_supported():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _NL_KEY):
            return True
    except OSError:
        return False


def night_light_on():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _NL_KEY) as k:
            data = winreg.QueryValueEx(k, "Data")[0]
        return len(data) > 18 and data[18] == 0x15
    except OSError:
        return False


def set_night_light(on):
    """Toggle Night Light and return whether the registry state was written.

    Windows has used several CloudStore payload shapes. The legacy format needs
    at least 25 bytes; shorter values are left untouched and the caller can open
    Windows Settings instead of crashing or writing a corrupt payload.
    """
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _NL_KEY, 0,
                            winreg.KEY_READ | winreg.KEY_SET_VALUE) as key:
            data = bytearray(winreg.QueryValueEx(key, "Data")[0])
            if len(data) < 25:
                return False
            enabled = data[18] == 0x15
            if on == enabled:
                return True
            if on:
                data[18] = 0x15
                data[23:23] = b"\x10\x00"
            else:
                data[18] = 0x13
                del data[23:25]
            for index in range(10, 15):  # timestamp: Windows ignores a value that does not advance
                if data[index] != 0xFF:
                    data[index] += 1
                    break
            winreg.SetValueEx(key, "Data", 0, winreg.REG_BINARY, bytes(data))
            return True
    except (OSError, IndexError, TypeError, ValueError):
        return False


class DoNotDisturb:
    """Read state from the taskbar notification icon and toggle through the
    Do Not Disturb button in the notification center (UI Automation)."""

    def __init__(self):
        self.on = False
        self._toggle = threading.Event()
        threading.Thread(target=self._run, daemon=True).start()

    def toggle(self):
        self.on = not self.on  # immediate visual feedback
        self._toggle.set()

    def _run(self):
        import comtypes
        import comtypes.client
        comtypes.CoInitialize()
        comtypes.client.GetModule("UIAutomationCore.dll")
        from comtypes.gen import UIAutomationClient as U
        uia = comtypes.client.CreateObject(U.CUIAutomation, interface=U.IUIAutomation)

        def read():
            try:
                tb = user32.FindWindowW("Shell_TrayWnd", None)
                el = uia.ElementFromHandle(tb)
                c = uia.CreatePropertyCondition(U.UIA_ClassNamePropertyId, "SystemTray.OmniButtonRight")
                e = el.FindFirst(U.TreeScope_Descendants, c)
                name = (e.CurrentName or "").lower() if e else ""
                return "déranger" in name or "disturb" in name  # localized Windows control name
            except Exception:
                return self.on

        def key(*vks):
            for vk in vks:
                user32.keybd_event(vk, 0, 0, 0)
            for vk in reversed(vks):
                user32.keybd_event(vk, 0, 2, 0)

        def do_toggle():
            key(0x5B, 0x4E)  # Win+N
            btn = None
            cond = uia.CreatePropertyCondition(U.UIA_AutomationIdPropertyId, "DoNotDisturbButton")
            for _ in range(30):
                time.sleep(0.08)
                try:
                    btn = uia.GetRootElement().FindFirst(U.TreeScope_Descendants, cond)
                except Exception:
                    btn = None
                if btn:
                    break
            if btn:
                try:
                    btn.GetCurrentPattern(U.UIA_TogglePatternId).QueryInterface(
                        U.IUIAutomationTogglePattern).Toggle()
                except Exception:
                    pass
            time.sleep(0.15)
            key(0x1B)  # Escape
            time.sleep(0.6)

        self.on = read()
        while True:
            if self._toggle.wait(3):
                self._toggle.clear()
                do_toggle()
            self.on = read()


_CONSENT = r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore"


def camera_allowed():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _CONSENT + r"\webcam") as k:
            return winreg.QueryValueEx(k, "Value")[0] != "Deny"
    except OSError:
        return True


def set_camera_allowed(on):
    try:
        for sub in (r"\webcam", r"\webcam\NonPackaged"):  # Store apps + desktop apps
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, _CONSENT + sub, 0, winreg.KEY_SET_VALUE) as k:
                winreg.SetValueEx(k, "Value", 0, winreg.REG_SZ, "Allow" if on else "Deny")
    except OSError:
        pass


def _in_use(cap):
    """True when an application currently uses the capability ('webcam' or 'microphone')."""
    def scan(path, depth):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as k:
                try:
                    stop = winreg.QueryValueEx(k, "LastUsedTimeStop")[0]
                    start = winreg.QueryValueEx(k, "LastUsedTimeStart")[0]
                    if stop == 0 and start != 0:
                        return True
                except OSError:
                    pass
                if depth == 0:
                    return False
                i = 0
                while True:
                    try:
                        sub = winreg.EnumKey(k, i)
                    except OSError:
                        return False
                    if scan(path + "\\" + sub, depth - 1):
                        return True
                    i += 1
        except OSError:
            return False
    return scan(_CONSENT + "\\" + cap, 2)


def camera_in_use():
    return _in_use("webcam")


def mic_in_use():
    return _in_use("microphone")


def caps_lock():
    return bool(user32.GetKeyState(0x14) & 1)


def num_lock():
    return bool(user32.GetKeyState(0x90) & 1)


def lock_pc():
    user32.LockWorkStation()


def sleep_pc():
    ctypes.windll.powrprof.SetSuspendState(False, False, False)


GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x20
WS_EX_LAYERED = 0x80000
WS_EX_NOACTIVATE = 0x08000000

user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]


def set_exstyle(hwnd, flag, on):
    cur = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
    new = (cur | flag) if on else (cur & ~flag)
    if new != cur:
        user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, new)


def send_ctrl_v():
    KEYUP = 2
    user32.keybd_event(0x11, 0, 0, 0)
    user32.keybd_event(0x56, 0, 0, 0)
    user32.keybd_event(0x56, 0, KEYUP, 0)
    user32.keybd_event(0x11, 0, KEYUP, 0)


def force_foreground(hwnd):
    if hwnd:
        user32.SetForegroundWindow(hwnd)


def _window_aumid(hwnd):
    """AppUserModelID of a window (the one Windows associates with playing media)."""
    try:
        from win32com.propsys import propsys, pscon
        store = propsys.SHGetPropertyStoreForWindow(hwnd, propsys.IID_IPropertyStore)
        v = store.GetValue(pscon.PKEY_AppUserModel_ID).GetValue()
        return v or ""
    except Exception:
        return ""


def find_app_window(aumid, title=""):
    """Window of the media application: (hwnd, exe path) or (None, exe or None)."""
    import psutil
    aum = (aumid or "").lower()
    stem = aum.rsplit("\\", 1)[-1].replace(".exe", "")
    known = {"308046b0af4a39cb": ("firefox", "zen", "librewolf", "floorp", "waterfox")}.get(stem, (stem,))
    t_low = (title or "").lower()
    best, best_score, exe_any = None, 0, None
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd) or user32.GetWindow(hwnd, 4):  # ignore owned windows
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if not n:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        found.append((hwnd, buf.value))
        return True

    user32.EnumWindows(cb, 0)
    wins = []
    for hwnd, wtitle in found:
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        try:
            proc = psutil.Process(pid.value)
            wins.append((hwnd, wtitle, proc, proc.name().lower().replace(".exe", "")))
        except Exception:
            continue
    # fast first pass by executable name; exact identifier is read only when needed (slow)
    for full_scan in (False, True):
        for hwnd, wtitle, proc, exe_name in wins:
            by_exe = exe_name in known or (stem and (exe_name == stem or stem in exe_name))
            if not by_exe and not full_scan:
                continue
            score = (2 if (exe_name in known or exe_name == stem) else 1) if by_exe else 0
            if aum and (by_exe or full_scan) and _window_aumid(hwnd).lower() == aum:
                score = 4
            if score and t_low and t_low[:40] in wtitle.lower():
                score += 2  # this is the tab / window that is playing
            if score > best_score:
                try:
                    exe_any = proc.exe()
                except Exception:
                    exe_any = None
                best, best_score = hwnd, score
        if best:
            break
    return best, exe_any


def open_media_app(aumid, title=""):
    """Show the media application; fall back to launching it through its identifier."""
    hwnd, _exe = find_app_window(aumid, title)
    if hwnd and activate_window(hwnd):
        return True
    if aumid:
        import subprocess
        subprocess.Popen(["explorer.exe", "shell:AppsFolder\\" + aumid])
        return True
    return False


def keep_topmost(hwnd):
    """Keep the island above all always-on-top windows without activating it."""
    HWND_TOPMOST = wintypes.HWND(-1)
    user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)  # NOSIZE|NOMOVE|NOACTIVATE


class APPBARDATA(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND), ("uCallbackMessage", wintypes.UINT),
                ("uEdge", wintypes.UINT), ("rc", wintypes.RECT), ("lParam", wintypes.LPARAM)]


ABM_GETSTATE, ABM_SETSTATE = 0x4, 0xA
ABS_AUTOHIDE, ABS_ALWAYSONTOP = 0x1, 0x2


def _appbar(msg, lparam=0):
    abd = APPBARDATA()
    abd.cbSize = ctypes.sizeof(abd)
    abd.hWnd = user32.FindWindowW("Shell_TrayWnd", None)
    abd.lParam = lparam
    return ctypes.windll.shell32.SHAppBarMessage(msg, ctypes.byref(abd))


def taskbar_autohide():
    return bool(_appbar(ABM_GETSTATE) & ABS_AUTOHIDE)


def set_taskbar_autohide(on):
    """Windows auto-hide: frees the full screen height for application windows."""
    _appbar(ABM_SETSTATE, ABS_AUTOHIDE if on else ABS_ALWAYSONTOP)


def taskbar_windows():
    """Primary taskbar plus secondary-display taskbars."""
    out = []
    h = user32.FindWindowW("Shell_TrayWnd", None)
    if h:
        out.append(h)
    h2 = 0
    while True:
        h2 = user32.FindWindowExW(None, h2, "Shell_SecondaryTrayWnd", None)
        if not h2:
            break
        out.append(h2)
    return out


def hide_taskbar():
    """Hide the taskbar; return True when it was visible (Windows had shown it again)."""
    shown = False
    for h in taskbar_windows():
        if user32.IsWindowVisible(h):
            user32.ShowWindow(h, 0)  # SW_HIDE
            shown = True
    return shown


def show_taskbar():
    for h in taskbar_windows():
        user32.ShowWindow(h, 5)  # SW_SHOW
