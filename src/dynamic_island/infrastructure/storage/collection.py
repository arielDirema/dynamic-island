"""Local JSON storage plus optional synchronization through a cloud folder
(OneDrive, Google Drive, Dropbox…). Per-item “newest wins” merge."""
import json
import os
import time
import uuid

from dynamic_island.core.config.paths import data_dir
from dynamic_island.core.config.settings import settings


def _data_dir():
    return data_dir(settings.get("sync_dir"))


class Collection:
    """List of {id, mtime, …} items saved in <data_dir>/<name>.json."""

    _all = []

    def __init__(self, name):
        self.name = name
        self.items = []
        self.deleted = set()
        self._mtime = 0
        self.version = 0
        self.load()
        Collection._all.append(self)

    @property
    def path(self):
        return os.path.join(_data_dir(), self.name + ".json")

    def _read(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                d = json.load(f)
            self._mtime = os.path.getmtime(self.path)
            return d.get("items", []), set(d.get("deleted", []))
        except Exception:
            return [], set()

    def load(self):
        items, deleted = self._read()
        self.deleted = deleted
        self.items = [i for i in items if i.get("id") not in deleted]
        self.version += 1

    def _merge(self, items, deleted):
        self.deleted |= deleted
        by_id = {i["id"]: i for i in self.items}
        for it in items:
            cur = by_id.get(it["id"])
            if cur is None or it.get("mtime", 0) > cur.get("mtime", 0):
                by_id[it["id"]] = it
        self.items = [i for i in by_id.values() if i["id"] not in self.deleted]
        self.version += 1

    def save(self):
        os.makedirs(_data_dir(), exist_ok=True)
        if settings.get("sync_dir"):
            self._merge(*self._read())
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"items": self.items, "deleted": sorted(self.deleted)[-3000:]}, f, ensure_ascii=False)
        os.replace(tmp, self.path)
        self._mtime = os.path.getmtime(self.path)
        self.version += 1

    def check_sync(self):
        try:
            m = os.path.getmtime(self.path)
        except OSError:
            return False
        if m != self._mtime:
            self._merge(*self._read())
            self._mtime = m
            return True
        return False

    def add(self, **fields):
        now = time.time()
        it = {"id": uuid.uuid4().hex, "created": now, "mtime": now}
        it.update(fields)
        self.items.append(it)
        self.save()
        return it

    def update(self, item, **fields):
        item.update(fields)
        item["mtime"] = time.time()
        self.save()

    def remove(self, item):
        if item in self.items:
            self.items.remove(item)
        self.deleted.add(item["id"])
        self.save()

    def get(self, id_):
        for i in self.items:
            if i["id"] == id_:
                return i
        return None

    @classmethod
    def sync_all(cls):
        changed = False
        for c in cls._all:
            changed |= c.check_sync()
        return changed

    @classmethod
    def save_all(cls):
        """After changing the sync folder: merge memory with the new folder."""
        for c in cls._all:
            c.save()
