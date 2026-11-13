"""Notification-area menu (taskbar tray icon)."""
import os

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QAction, QActionGroup, QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QFileDialog, QMenu, QMessageBox, QSystemTrayIcon

from dynamic_island.core.application.autostart import autostart_enabled, set_autostart
from dynamic_island.core.config.settings import settings
from dynamic_island.core.localization import (
    UnsupportedLanguageError,
    available_languages,
    current_language,
    on_language_changed,
    set_language,
    translate as tr,
)
from dynamic_island.infrastructure.storage.collection import Collection
from dynamic_island.ui.themes import T
from dynamic_island.ui.windows.layout import MENU_QSS


def make_tray_icon():
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(32, 32, 32))
    painter.setPen(QPen(QColor(255, 255, 255, 140), 2))
    painter.drawRoundedRect(QRectF(4, 20, 56, 24), 7, 7)
    painter.setBrush(QColor(T.accent))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(QPointF(48, 32), 5, 5)
    painter.end()
    return QIcon(pixmap)


def create_tray(app, island, app_icon):
    """Build the island context menu and the notification icon."""
    tray = QSystemTrayIcon(app_icon, app)
    tray.setToolTip(tr("app.name"))
    island.tray = tray
    menu = QMenu()

    pin = QAction(tr("tray.keep_open"), menu, checkable=True)
    pin.toggled.connect(lambda value: setattr(island, "pinned", value))

    autostart = QAction(tr("tray.start_with_windows"), menu, checkable=True)
    if not settings.get("autostart_done"):  # permanent island: enable autostart once by default
        set_autostart(True)
        settings.set("autostart_done", True)
    elif autostart_enabled():
        set_autostart(True)  # update the command so it goes through the watchdog
    autostart.setChecked(autostart_enabled())
    autostart.toggled.connect(set_autostart)

    dock = QAction(tr("tray.dock"), menu, checkable=True)
    dock.setChecked(island.dock_enabled)
    dock.toggled.connect(lambda value: settings.set("dock", value))
    menu.setStyleSheet(MENU_QSS)

    taskbar = QAction(tr("tray.hide_taskbar"), menu, checkable=True)
    taskbar.setChecked(island.taskbar_hidden)
    taskbar.toggled.connect(island.set_taskbar_hidden)

    clipboard_menu = menu.addMenu(tr("tray.clipboard"))
    open_clipboard = QAction(tr("tray.open_clipboard"), clipboard_menu)
    open_clipboard.triggered.connect(island.open_clipboard)
    pause = QAction(tr("tray.pause_history"), clipboard_menu, checkable=True)
    pause.toggled.connect(lambda value: setattr(island.clip, "paused", value))

    def clear():
        if QMessageBox.question(None, tr("app.name"), tr("tray.clear_confirm")) == \
                QMessageBox.StandardButton.Yes:
            island.clip.clear()

    clear_action = QAction(tr("tray.clear_history"), clipboard_menu)
    clear_action.triggered.connect(clear)
    for action in (open_clipboard, pause, clear_action):
        clipboard_menu.addAction(action)

    sync_action = QAction(tr("tray.sync_choose"), menu)
    stop_sync = QAction(tr("tray.sync_stop"), menu)

    def refresh_sync():
        directory = settings.get("sync_dir")
        sync_action.setText(
            tr("tray.sync_current", path=directory) if directory else tr("tray.sync_choose")
        )
        stop_sync.setVisible(bool(directory))

    def choose_sync():
        directory = QFileDialog.getExistingDirectory(
            None, tr("tray.sync_dialog"), os.environ.get("OneDrive", os.path.expanduser("~"))
        )
        if directory:
            island.clip.set_sync_dir(directory)
            Collection.save_all()
            refresh_sync()

    def disable_sync():
        island.clip.set_sync_dir(None)
        Collection.save_all()
        refresh_sync()

    sync_action.triggered.connect(choose_sync)
    stop_sync.triggered.connect(disable_sync)
    refresh_sync()

    # language selector: native names, independent from the active translation
    language_menu = menu.addMenu(tr("languages.title"))
    language_group = QActionGroup(language_menu)
    language_group.setExclusive(True)
    language_actions = {}
    for info in available_languages():
        action = QAction(info.native_name, language_menu, checkable=True)
        action.setChecked(info.code == current_language())
        action.triggered.connect(lambda _checked=False, code=info.code: change_language(code))
        language_group.addAction(action)
        language_menu.addAction(action)
        language_actions[info.code] = action

    def change_language(code):
        try:
            set_language(code)
        except UnsupportedLanguageError:
            QMessageBox.warning(None, tr("app.name"), tr("languages.unavailable"))
        else:
            retranslate()

    quit_action = QAction(tr("tray.quit"), menu)

    def quit_app():
        unsubscribe = getattr(tray, "_language_unsubscribe", None)
        if unsubscribe:
            unsubscribe()
        island.shutdown()
        tray.hide()
        app.quit()

    quit_action.triggered.connect(quit_app)
    menu.addAction(pin)
    menu.addAction(autostart)
    menu.addAction(taskbar)
    menu.addAction(dock)
    menu.addSeparator()
    menu.addAction(sync_action)
    menu.addAction(stop_sync)
    menu.addSeparator()
    menu.addAction(quit_action)
    tray.setContextMenu(menu)
    tray.show()
    island.tray_menu = menu
    island.pin_action = pin

    def retranslate():
        tray.setToolTip(tr("app.name"))
        pin.setText(tr("tray.keep_open"))
        autostart.setText(tr("tray.start_with_windows"))
        dock.setText(tr("tray.dock"))
        taskbar.setText(tr("tray.hide_taskbar"))
        menu.setTitle("")
        clipboard_menu.setTitle(tr("tray.clipboard"))
        open_clipboard.setText(tr("tray.open_clipboard"))
        pause.setText(tr("tray.pause_history"))
        clear_action.setText(tr("tray.clear_history"))
        stop_sync.setText(tr("tray.sync_stop"))
        language_menu.setTitle(tr("languages.title"))
        quit_action.setText(tr("tray.quit"))
        refresh_sync()
        selected = current_language()
        for code, action in language_actions.items():
            action.setChecked(code == selected)

    tray._language_unsubscribe = on_language_changed(lambda _language: retranslate())
    return tray
