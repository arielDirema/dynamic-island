"""Fast file manager: shelf (pending files), active downloads, recent files,
favorite folders, copy/move operations and shortcuts."""
import glob
import os
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import time
import winreg

from PySide6.QtCore import QObject, Signal

from dynamic_island.core.config.settings import settings
from dynamic_island.core.localization import translate as tr

PARTIAL_EXT = (".crdownload", ".part", ".partial", ".download", ".opdownload")
BROWSER_DBS = [
    ("Chrome", r"%LOCALAPPDATA%\Google\Chrome\User Data\*\History"),
    ("Edge", r"%LOCALAPPDATA%\Microsoft\Edge\User Data\*\History"),
    ("Brave", r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\User Data\*\History"),
    ("Opera", r"%APPDATA%\Opera Software\Opera Stable\History"),
]


def known_folder(guid, fallback):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as k:
            v = winreg.QueryValueEx(k, guid)[0]
            return os.path.expandvars(v)
    except OSError:
        return os.path.join(os.path.expanduser("~"), fallback)


DOWNLOADS = known_folder("{374DE290-123F-4565-9164-39C4925E467B}", "Downloads")
DESKTOP = known_folder("Desktop", "Desktop")
DOCUMENTS = known_folder("Personal", "Documents")
PICTURES = known_folder("My Pictures", "Pictures")


class Files(QObject):
    changed = Signal()
    alert = Signal(str, str, str)  # kind, title, path

    def __init__(self):
        super().__init__()
        self.downloads = []   # [{name, path, size, total, speed, eta, browser}]
        self.recent = []      # [{name, path, mtime, is_dir}]
        self._sizes = {}      # path -> [(timestamp, size)]
        self._totals = {}
        self._known_partials = set()
        self._db_t = 0
        threading.Thread(target=self._dl_loop, daemon=True).start()
        threading.Thread(target=self._recent_loop, daemon=True).start()

    @property
    def shelf(self):
        return [p for p in settings.get("shelf", []) if os.path.exists(p)]

    def add_to_shelf(self, paths):
        cur = settings.get("shelf", [])
        added = 0
        for p in paths:
            p = os.path.normpath(p)
            if os.path.exists(p) and p not in cur:
                cur.insert(0, p)
                added += 1
        settings.set("shelf", cur[:60])
        self.changed.emit()
        return added

    def remove_from_shelf(self, path):
        settings.set("shelf", [p for p in settings.get("shelf", []) if p != path])
        self.changed.emit()

    def clear_shelf(self):
        settings.set("shelf", [])
        self.changed.emit()

    @property
    def favorites(self):
        favs = settings.get("fav_folders")
        if favs is None:
            favs = [p for p in (DESKTOP, DOCUMENTS, DOWNLOADS, PICTURES) if os.path.isdir(p)]
        return [p for p in favs if os.path.isdir(p)]

    def add_favorite(self, path):
        favs = self.favorites
        if path and os.path.isdir(path) and path not in favs:
            favs.append(path)
            settings.set("fav_folders", favs)

    def remove_favorite(self, path):
        settings.set("fav_folders", [p for p in self.favorites if p != path])

    def desktop_shortcut(self, path):
        """Create a .lnk shortcut on the Desktop pointing to the file or folder."""
        try:
            import pythoncom
            import win32com.client
            pythoncom.CoInitialize()
            sh = win32com.client.Dispatch("WScript.Shell")
            lnk = os.path.join(DESKTOP, os.path.basename(path.rstrip("\\")) + ".lnk")
            s = sh.CreateShortCut(lnk)
            s.TargetPath = path
            s.save()
            return lnk
        except Exception:
            return None

    @staticmethod
    def open(path):
        try:
            os.startfile(path)
        except OSError:
            pass

    @staticmethod
    def reveal(path):
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])

    def transfer(self, paths, dest, move=False):
        def work():
            done, err = 0, None
            for p in paths:
                try:
                    target = os.path.join(dest, os.path.basename(p.rstrip("\\")))
                    base, ext = os.path.splitext(target)
                    i = 1
                    while os.path.exists(target):
                        target = f"{base} ({i}){ext}"
                        i += 1
                    if move:
                        shutil.move(p, target)
                    elif os.path.isdir(p):
                        shutil.copytree(p, target)
                    else:
                        shutil.copy2(p, target)
                    done += 1
                    if move:
                        cur = settings.get("shelf", [])
                        settings.set("shelf", [target if x == p else x for x in cur])
                except Exception as e:
                    err = str(e)
            action = tr("files.action_moved") if move else tr("files.action_copied")
            self.alert.emit("files", tr("files.transferred", count=done, action=action), err or dest)
            self.changed.emit()
        threading.Thread(target=work, daemon=True).start()

    def _browser_totals(self):
        """Total size of active Chrome/Edge downloads (copied History database)."""
        totals = {}
        for name, pat in BROWSER_DBS:
            for db in glob.glob(os.path.expandvars(pat)):
                try:
                    tmp = os.path.join(tempfile.gettempdir(), f"di_hist_{abs(hash(db))}.db")
                    shutil.copy2(db, tmp)
                    con = sqlite3.connect(tmp)
                    for cur, tgt, tot, rec in con.execute(
                            "select current_path, target_path, total_bytes, received_bytes from downloads where state=0"):
                        for p in (cur, tgt):
                            if p:
                                totals[os.path.normcase(p)] = (tot, name, tgt)
                    con.close()
                    os.remove(tmp)
                except Exception:
                    continue
        return totals

    def _dl_loop(self):
        while True:
            try:
                self._scan_downloads()
            except Exception:
                pass
            time.sleep(1 if self.downloads else 3)

    def _scan_downloads(self):
        now = time.time()
        found = []
        for f in os.listdir(DOWNLOADS):
            if f.lower().endswith(PARTIAL_EXT):
                found.append(os.path.join(DOWNLOADS, f))
        if found and now - self._db_t > 3:
            self._db_t = now
            self._totals = self._browser_totals()
        items = []
        for p in found:
            try:
                size = os.path.getsize(p)
            except OSError:
                continue
            hist = self._sizes.setdefault(p, [])
            hist.append((now, size))
            hist[:] = [h for h in hist if now - h[0] < 6]
            speed = (hist[-1][1] - hist[0][1]) / (hist[-1][0] - hist[0][0]) if len(hist) > 1 and hist[-1][0] > hist[0][0] else 0
            tot, browser, target = self._totals.get(os.path.normcase(p), (0, None, None))
            name = os.path.basename(target) if target else os.path.splitext(os.path.basename(p))[0]
            if not browser:
                browser = "Firefox / Zen" if p.lower().endswith(".part") else tr("files.browser")
            eta = (tot - size) / speed if tot and speed > 0 else None
            items.append({"name": name, "path": p, "size": size, "total": tot or 0, "speed": max(0, speed),
                          "eta": eta, "browser": browser, "target": target or p[: -len(os.path.splitext(p)[1])]})
        # completed downloads
        for old in self._known_partials - set(found):
            final = old[: -len(os.path.splitext(old)[1])]
            tgt = next((d["target"] for d in self.downloads if d["path"] == old), final)
            if tgt and os.path.exists(tgt):
                self.alert.emit("download", tr("files.download_finished"), tgt)
            self._sizes.pop(old, None)
        self._known_partials = set(found)
        self.downloads = items
        self.changed.emit()

    def _recent_loop(self):
        try:
            import pythoncom
            import win32com.client
            pythoncom.CoInitialize()
            sh = win32com.client.Dispatch("WScript.Shell")
        except Exception:
            return
        cache = {}
        while True:
            try:
                rdir = os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Recent")
                links = sorted(glob.glob(os.path.join(rdir, "*.lnk")), key=os.path.getmtime, reverse=True)[:80]
                out = []
                for link in links:
                    if link not in cache:
                        try:
                            cache[link] = sh.CreateShortCut(link).TargetPath
                        except Exception:
                            cache[link] = ""
                    target = cache[link]
                    if target and os.path.exists(target):
                        out.append({"name": os.path.basename(target.rstrip("\\")) or target, "path": target,
                                    "mtime": os.path.getmtime(link), "is_dir": os.path.isdir(target)})
                    if len(out) >= 40:
                        break
                self.recent = out
                self.changed.emit()
            except Exception:
                pass
            time.sleep(30)
