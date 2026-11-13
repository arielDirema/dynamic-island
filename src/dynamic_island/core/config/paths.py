"""Application file locations, from source checkout or installed executable."""
import os
import sys


def frozen():
    return bool(getattr(sys, "frozen", False))


def app_dir():
    """Application root: repository in source mode, DynamicIsland.exe directory once installed."""
    if frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    # src/dynamic_island/core/config/paths.py → repository root
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))


def resource(*parts):
    return os.path.join(app_dir(), *parts)


APPDATA = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "DynamicIsland")
SETTINGS_FILE = os.path.join(APPDATA, "settings.json")
WATCHDOG_LOG = os.path.join(APPDATA, "watchdog.log")


def data_dir(sync_dir=None):
    """Directory holding JSON collections (chosen cloud folder, otherwise local data)."""
    if sync_dir and os.path.isdir(sync_dir):
        return os.path.join(sync_dir, "DynamicIsland")
    return os.path.join(APPDATA, "data")
