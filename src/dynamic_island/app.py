"""Application startup: single instance, window, icon and Qt event loop."""
import ctypes
import os
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from dynamic_island.core.config import paths
from dynamic_island.core.localization import translate as tr
from dynamic_island.services import system
from dynamic_island.ui.components.tray import create_tray, make_tray_icon
from dynamic_island.ui.windows.island import Island


def main():
    ctypes.windll.kernel32.CreateMutexW(None, False, "DynamicIsland_SingleInstance")
    if ctypes.windll.kernel32.GetLastError() == 183:
        return
    ctypes.windll.winmm.timeBeginPeriod(1)
    sys.setswitchinterval(0.001)  # background threads no longer block the animation

    app = QApplication(sys.argv)
    app.setApplicationName(tr("app.name"))
    app.setApplicationDisplayName(tr("app.name"))
    app.setQuitOnLastWindowClosed(False)
    island = Island()

    ico_path = paths.resource("assets", "island.ico")
    app_icon = QIcon(ico_path) if os.path.exists(ico_path) else make_tray_icon()
    app.setWindowIcon(app_icon)
    create_tray(app, island, app_icon)

    QApplication.primaryScreen().geometryChanged.connect(lambda _: island.place())
    island.show()
    system.set_exstyle(island.hwnd, system.WS_EX_NOACTIVATE, True)
    island.apply_taskbar()
    app.aboutToQuit.connect(island.restore_taskbar)
    code = app.exec()
    ctypes.windll.winmm.timeEndPeriod(1)
    sys.exit(code)


if __name__ == "__main__":
    main()
