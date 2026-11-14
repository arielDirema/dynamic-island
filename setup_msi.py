"""Build the Windows application with cx_Freeze.

    python setup_msi.py build_exe   -> build/  (portable application: DynamicIsland.exe)
    python setup_msi.py bdist_msi   -> dist/   (Windows .msi installer)

The installer targets the current user (no administrator rights) under
%LOCALAPPDATA%\\Programs\\Dynamic Island, creates Start menu and Desktop shortcuts and enables
startup with Windows. Uninstalling removes these; user data in
%APPDATA%\\DynamicIsland is preserved."""
import os
import sys

from cx_Freeze import Executable, setup

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "src"))  # let cx_Freeze analyze the package from src/

VERSION = "1.1.0"
UPGRADE_CODE = "{32BDF7EE-F765-4C20-AB17-EBB9CFFF65DA}"  # never change: enables upgrades

build_exe_options = {
    "packages": [
        "dynamic_island",
        "winrt", "comtypes", "pycaw", "screen_brightness_control", "wmi", "icalendar",
        "recurring_ical_events", "qrcode", "cryptography", "tzdata", "psutil", "win32com",
        "pythoncom", "pywintypes", "zoneinfo", "xml", "sqlite3", "asyncio", "ctypes", "babel",
    ],
    "includes": [],
    "excludes": [
        "tkinter", "unittest", "pydoc_data", "test", "distutils", "setuptools", "pip",
        "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick", "PySide6.QtWebView",
        "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DExtras", "PySide6.QtCharts", "PySide6.QtDataVisualization",
        "PySide6.QtGraphs", "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtQuick",
        "PySide6.QtQuick3D", "PySide6.QtQml", "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtDesigner",
        "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtLocation", "PySide6.QtPositioning",
        "PySide6.QtSensors", "PySide6.QtSerialPort", "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtCanvasPainter",
        "PIL", "cx_Freeze",
    ],
    "include_files": [
        ("locales", "locales"),
        ("resources/phone_page.html", "resources/phone_page.html"),
        ("assets/island.ico", "assets/island.ico"),
        ("README.md", "README.md"),
    ],
    "include_msvcr": True,
    "optimize": 1,
}

bdist_msi_options = {
    "upgrade_code": UPGRADE_CODE,
    "add_to_path": False,
    "all_users": False,                                         # per-user installation, no UAC
    "initial_target_dir": r"[LocalAppDataFolder]Programs\Dynamic Island",
    "install_icon": "assets/island.ico",
    "product_code": None,
    "output_name": f"DynamicIsland-{VERSION}-win64.msi",
    "summary_data": {
        "author": "arielDirema",
        "comments": "Dynamic Island for Windows 11",
        "keywords": "dynamic island, windows 11, taskbar",
    },
    "data": {
        # Desktop shortcut (the Start menu shortcut is created by the executable below)
        "Shortcut": [
            ("DesktopShortcut", "DesktopFolder", "Dynamic Island", "TARGETDIR",
             "[TARGETDIR]DynamicIsland.exe", None, "Dynamic Island for Windows 11", None, None, None, None,
             "TARGETDIR"),
        ],
        # Start with Windows (managed by the installer; removed during uninstall)
        "Registry": [
            ("AutoStart", 1, r"Software\Microsoft\Windows\CurrentVersion\Run", "DynamicIsland",
             '"[TARGETDIR]DynamicIsland.exe"', "TARGETDIR"),
        ],
    },
}

setup(
    name="Dynamic Island",
    version=VERSION,
    description="Dynamic Island for Windows 11",
    author="arielDirema",
    options={"build_exe": build_exe_options, "bdist_msi": bdist_msi_options},
    executables=[
        Executable(
            "src/main.py",
            base="gui" if sys.platform == "win32" else None,     # no console
            target_name="DynamicIsland.exe",
            icon="assets/island.ico",
            shortcut_name="Dynamic Island",
            shortcut_dir="ProgramMenuFolder",
            copyright="arielDirema",
        )
    ],
)
