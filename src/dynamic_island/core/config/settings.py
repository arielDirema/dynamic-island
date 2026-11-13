"""Persistent application settings (%APPDATA%\\DynamicIsland\\settings.json)."""
import json
import os
import shutil
import threading

from dynamic_island.core.config.paths import SETTINGS_FILE


class Settings(dict):
    """Thread-safe settings persisted as JSON, with one last-good backup."""

    def __init__(self, path=SETTINGS_FILE):
        super().__init__()
        self.path = os.fspath(path)
        self.backup = self.path + ".bak"
        self._lock = threading.RLock()
        self._load()

    def _load(self):
        if self._read(self.path):
            return
        if os.path.exists(self.path):
            self._preserve_corrupt()
            if self._read(self.backup):
                return

    def _read(self, path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return False
        if not isinstance(data, dict):
            return False
        self.update(data)
        return True

    def _preserve_corrupt(self):
        try:
            os.replace(self.path, self.path + ".corrupt")
        except OSError:
            pass

    def save(self):
        with self._lock:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(dict(self), f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
            try:
                shutil.copyfile(self.path, self.backup)
            except OSError:
                pass

    def set(self, key, value):
        with self._lock:
            self[key] = value
            self.save()


settings = Settings()
