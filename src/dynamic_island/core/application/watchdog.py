"""Dynamic Island watchdog: restart the island after an abnormal exit (crash or killed process).
- “Quit” from the menu (exit code 0) stops the watchdog.
- After 5 crashes within one minute it gives up and restores the taskbar so the screen is never
  left without either a taskbar or an island.
Works from source (`pythonw src/main.py`) and from the installed application
(DynamicIsland.exe --island)."""
import ctypes
import json
import os
import subprocess
import sys
import time

from dynamic_island.core.config.paths import APPDATA, WATCHDOG_LOG, app_dir, frozen

SETTINGS = os.path.join(APPDATA, "settings.json")
LOG = WATCHDOG_LOG


def island_command():
    if frozen():
        return [sys.executable, "--island"]
    return [sys.executable, os.path.join(app_dir(), "src", "main.py"), "--island"]


def log(msg):
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")
    except OSError:
        pass


def restore_taskbar():
    user32 = ctypes.windll.user32
    h = user32.FindWindowW("Shell_TrayWnd", None)
    if h:
        user32.ShowWindow(h, 5)
    h = 0
    while True:
        h = user32.FindWindowExW(None, h, "Shell_SecondaryTrayWnd", None)
        if not h:
            break
        user32.ShowWindow(h, 5)
    try:
        with open(SETTINGS, encoding="utf-8") as f:
            prev = json.load(f).get("taskbar_prev_autohide")
    except Exception:
        prev = None
    if prev is not None:
        from ctypes import wintypes as w

        class APPBARDATA(ctypes.Structure):
            _fields_ = [("cbSize", w.DWORD), ("hWnd", w.HWND), ("uCallbackMessage", w.UINT),
                        ("uEdge", w.UINT), ("rc", w.RECT), ("lParam", w.LPARAM)]
        abd = APPBARDATA()
        abd.cbSize = ctypes.sizeof(abd)
        abd.hWnd = user32.FindWindowW("Shell_TrayWnd", None)
        abd.lParam = 1 if prev else 2
        ctypes.windll.shell32.SHAppBarMessage(0xA, ctypes.byref(abd))


def main():
    ctypes.windll.kernel32.CreateMutexW(None, False, "DynamicIsland_Watchdog")
    if ctypes.windll.kernel32.GetLastError() == 183:
        return  # a watchdog is already running
    crashes = []
    while True:
        started = time.time()
        code = subprocess.run(island_command(), cwd=app_dir()).returncode
        if code == 0:
            log("normal exit")
            break
        log(f"island exited (code {code}) after {time.time() - started:.0f} s — restarting")
        crashes = [crash for crash in crashes if time.time() - crash < 60] + [time.time()]
        if len(crashes) >= 5:
            log("too many crashes, giving up")
            break
        time.sleep(2)
    restore_taskbar()


if __name__ == "__main__":
    main()
