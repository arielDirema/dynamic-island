"""Resource locations, source mode and installed mode."""
import sys
from pathlib import Path

from dynamic_island.core.config import paths


def test_source_app_dir_is_repository_root():
    root = paths.app_dir()
    assert paths.resource("src", "main.py") == str(Path(root) / "src" / "main.py")
    assert (Path(root) / "src" / "dynamic_island").is_dir()
    assert (Path(root) / "resources" / "phone_page.html").is_file()
    assert (Path(root) / "assets" / "island.ico").is_file()
    assert paths.frozen() is False


def test_frozen_app_dir_uses_executable_directory(tmp_path, monkeypatch):
    exe = tmp_path / "DynamicIsland.exe"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))
    assert paths.app_dir() == str(tmp_path)
    assert paths.resource("resources", "phone_page.html") == str(tmp_path / "resources" / "phone_page.html")


def test_data_dir_prefers_existing_sync_directory(tmp_path):
    assert paths.data_dir(str(tmp_path)) == str(tmp_path / "DynamicIsland")
    assert paths.data_dir(str(tmp_path / "absent")) == str(Path(paths.APPDATA) / "data")

