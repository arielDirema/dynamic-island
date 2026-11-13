"""Smart clipboard history: text, links, images, files,
search, pinning, categories, automatic detection and folder synchronization."""
import hashlib
import json
import os
import re
import time
import uuid

from PySide6.QtCore import QMimeData, QObject, QTimer, QUrl, Signal
from PySide6.QtGui import QImage

from dynamic_island.core.config.paths import APPDATA
from dynamic_island.core.config.settings import settings
from dynamic_island.core.localization import translate as tr

MAX_ITEMS = 300
MAX_TEXT = 50_000

RE_URL = re.compile(r"^(https?://|www\.)\S+$", re.I)
RE_EMAIL = re.compile(r"^[\w.+-]+@[\w-]+(\.[\w-]+)+$")
RE_PHONE = re.compile(r"^\+?[\d\s().-]{7,22}$")
RE_URL_IN = re.compile(r"(https?://\S+|www\.\S+)", re.I)
RE_EMAIL_IN = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
RE_PHONE_IN = re.compile(r"(?<![\w])\+?\d[\d .-]{7,18}\d(?![\w])")

def load_settings():
    return settings


def save_settings(_s=None):
    settings.save()


def classify(text):
    t = text.strip()
    if RE_URL.match(t):
        return "link"
    if RE_EMAIL.match(t):
        return "email"
    if RE_PHONE.match(t) and sum(c.isdigit() for c in t) >= 8:
        return "phone"
    return "text"


def detect(text):
    """Return detected items in free text (shown as badges)."""
    tags = []
    if RE_URL_IN.search(text):
        tags.append("link")
    if RE_EMAIL_IN.search(text):
        tags.append("email")
    if RE_PHONE_IN.search(text):
        tags.append("phone")
    return tags


class ClipboardHistory(QObject):
    changed = Signal()

    def __init__(self, clipboard):
        super().__init__()
        self.cb = clipboard
        self.settings = load_settings()
        self.items = []      # newest first
        self.deleted = set()  # deleted ids (for synchronization)
        self.paused = False
        self._mtime = 0
        self._save_timer = QTimer(self, singleShot=True, interval=600, timeout=self.save)
        self.load()
        self.cb.dataChanged.connect(self._on_change)
        QTimer(self, interval=4000, timeout=self._check_sync).start()

    @property
    def base_dir(self):
        sync = self.settings.get("sync_dir")
        if sync and os.path.isdir(sync):
            return os.path.join(sync, "DynamicIsland")
        return os.path.join(APPDATA, "clipboard")

    @property
    def path(self):
        return os.path.join(self.base_dir, "history.json")

    @property
    def img_dir(self):
        return os.path.join(self.base_dir, "images")

    def image_path(self, item):
        return os.path.join(self.img_dir, item["image"])

    def _read_file(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            self._mtime = os.path.getmtime(self.path)
            return data.get("items", []), set(data.get("deleted", []))
        except Exception:
            return [], set()

    def load(self):
        items, deleted = self._read_file()
        self.deleted = deleted
        self.items = [i for i in items if i["id"] not in deleted]
        self._sort()

    def _merge(self, items, deleted):
        self.deleted |= deleted
        by_id = {i["id"]: i for i in self.items}
        for it in items:
            cur = by_id.get(it["id"])
            if cur is None or it.get("mtime", 0) > cur.get("mtime", 0):
                by_id[it["id"]] = it
        merged, seen = [], set()
        for it in sorted(by_id.values(), key=lambda i: -i.get("mtime", i["time"])):
            if it["id"] in self.deleted or it["hash"] in seen:
                continue
            seen.add(it["hash"])
            merged.append(it)
        self.items = merged
        self._sort()

    def save(self):
        os.makedirs(self.base_dir, exist_ok=True)
        if self.settings.get("sync_dir"):
            other, deleted = self._read_file()
            self._merge(other, deleted)
        self._trim()
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"items": self.items, "deleted": sorted(self.deleted)[-2000:]}, f, ensure_ascii=False)
        os.replace(tmp, self.path)
        self._mtime = os.path.getmtime(self.path)

    def _check_sync(self):
        if not self.settings.get("sync_dir"):
            return
        try:
            m = os.path.getmtime(self.path)
        except OSError:
            return
        if m != self._mtime:
            items, deleted = self._read_file()
            self._merge(items, deleted)
            self.changed.emit()

    def set_sync_dir(self, path):
        if path:
            # move the local history into the synchronized folder
            old_items = list(self.items)
            old_img_dir = self.img_dir
            self.settings["sync_dir"] = path
            os.makedirs(self.img_dir, exist_ok=True)
            for it in old_items:
                if it.get("image"):
                    src, dst = os.path.join(old_img_dir, it["image"]), os.path.join(self.img_dir, it["image"])
                    if os.path.exists(src) and not os.path.exists(dst):
                        try:
                            with open(src, "rb") as a, open(dst, "wb") as b:
                                b.write(a.read())
                        except OSError:
                            pass
            items, deleted = self._read_file()
            self._merge(items, deleted)
        else:
            self.settings.pop("sync_dir", None)
        save_settings(self.settings)
        self.save()
        self.changed.emit()

    def _sort(self):
        self.items.sort(key=lambda i: -i["time"])

    def _trim(self):
        unpinned = [i for i in self.items if not i.get("pinned")]
        for it in unpinned[MAX_ITEMS:]:
            self.items.remove(it)
            if it.get("image"):
                try:
                    os.remove(self.image_path(it))
                except OSError:
                    pass

    def _touch(self):
        self._save_timer.start()
        self.changed.emit()

    def _on_change(self):
        if self.paused:
            return
        try:
            md = self.cb.mimeData()
        except Exception:
            return
        if md is None:
            return
        fmts = " ".join(md.formats())
        # password managers ask not to be recorded
        if "ExcludeClipboardContentFromMonitorProcessing" in fmts or "Clipboard Viewer Ignore" in fmts:
            return
        if "CanIncludeInClipboardHistory" in fmts:
            for f in md.formats():
                if "CanIncludeInClipboardHistory" in f and bytes(md.data(f))[:4] == b"\x00\x00\x00\x00":
                    return

        item = None
        if md.hasUrls() and md.urls() and all(u.isLocalFile() for u in md.urls()):
            files = [u.toLocalFile() for u in md.urls()]
            item = {"kind": "files", "files": files,
                    "text": "\n".join(files), "hash": self._h("\n".join(files))}
        elif md.hasImage():
            img = self.cb.image()
            if img.isNull():
                return
            h = hashlib.md5(bytes(img.constBits())).hexdigest()
            name = h + ".png"
            os.makedirs(self.img_dir, exist_ok=True)
            p = os.path.join(self.img_dir, name)
            if not os.path.exists(p):
                img.save(p, "PNG", 85)
            item = {"kind": "image", "image": name, "w": img.width(), "h": img.height(),
                    "text": tr("clipboard.image_size", width=img.width(), height=img.height()),
                    "hash": h}
        elif md.hasText():
            text = md.text()
            if not text.strip():
                return
            text = text[:MAX_TEXT]
            item = {"kind": classify(text), "text": text, "hash": self._h(text), "tags": detect(text)}
        if item:
            self._add(item)

    @staticmethod
    def _h(s):
        return hashlib.md5(s.encode("utf-8", "ignore")).hexdigest()

    def _add(self, item):
        now = time.time()
        for it in self.items:
            if it["hash"] == item["hash"]:
                it["time"] = it["mtime"] = now  # already present: move it to the top
                self._sort()
                self._touch()
                return
        item.update({"id": uuid.uuid4().hex, "time": now, "mtime": now, "pinned": False})
        self.items.insert(0, item)
        self._trim()
        self._touch()

    def query(self, search="", category="all"):
        s = search.lower().strip()
        out = []
        for it in self.items:
            k = it["kind"]
            if category == "pinned" and not it.get("pinned"):
                continue
            if category == "text" and k != "text":
                continue
            if category == "link" and k != "link" and not ({"link", "lien"} & set(it.get("tags", []))):
                continue
            if category == "contact" and k not in ("email", "phone") and not (
                    {"email", "e-mail", "phone", "numéro"} & set(it.get("tags", []))):
                continue
            if category in ("image", "files") and k != category:
                continue
            if s and s not in it.get("text", "").lower():
                continue
            out.append(it)
        # pinned items first
        out.sort(key=lambda i: (not i.get("pinned"), -i["time"]))
        return out

    def copy(self, item):
        """Put the item back on the clipboard."""
        k = item["kind"]
        if k == "image":
            img = QImage(self.image_path(item))
            if img.isNull():
                return False
            self.cb.setImage(img)
        elif k == "files":
            md = QMimeData()
            md.setUrls([QUrl.fromLocalFile(f) for f in item["files"]])
            md.setText(item["text"])
            self.cb.setMimeData(md)
        else:
            self.cb.setText(item["text"])
        return True

    def toggle_pin(self, item):
        item["pinned"] = not item.get("pinned")
        item["mtime"] = time.time()
        self._touch()

    def delete(self, item):
        if item in self.items:
            self.items.remove(item)
        self.deleted.add(item["id"])
        if item.get("image") and not any(i.get("image") == item["image"] for i in self.items):
            try:
                os.remove(self.image_path(item))
            except OSError:
                pass
        self._touch()

    def clear(self):
        for it in [i for i in self.items if not i.get("pinned")]:
            self.delete(it)
