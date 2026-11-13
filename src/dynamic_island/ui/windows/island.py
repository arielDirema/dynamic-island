"""Main Dynamic Island window and user interactions."""
import ctypes
import datetime as dt
import os
import threading
import time
import webbrowser
import winsound
from ctypes import wintypes

import psutil
from PySide6.QtCore import QMimeData, QPointF, QRectF, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QCursor, QDrag, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QWidget

from dynamic_island.core.config.settings import settings
from dynamic_island.core.localization import (
    format_time,
    on_language_changed,
    translate as tr,
)
from dynamic_island.core.utilities.animation import spring
from dynamic_island.core.utilities.formatting import until
from dynamic_island.engines.agenda import Agenda
from dynamic_island.engines.binance import Binance
from dynamic_island.engines.clipboard import ClipboardHistory
from dynamic_island.engines.devtools import Dev
from dynamic_island.engines.files import Files
from dynamic_island.engines.hotspot import Hotspot
from dynamic_island.engines.infos import Infos
from dynamic_island.engines.launcher import Launcher
from dynamic_island.engines.media import MediaWorker
from dynamic_island.engines.network import Networks
from dynamic_island.engines.tasks import Tasks
from dynamic_island.engines.timers import Timers
from dynamic_island.infrastructure.storage.collection import Collection
from dynamic_island.services import system
from dynamic_island.services.phone import Phone
from dynamic_island.ui.components.drawing import LEFT, UI
from dynamic_island.ui.components.painting import IslandPainting, accent_from
from dynamic_island.ui.tabs import TABS
from dynamic_island.ui.themes import G, T, W, font
from dynamic_island.ui.windows.layout import (
    ALERT,
    ALERT_TIME,
    COMPACT,
    COMPACT_BUILD,
    COMPACT_MEET,
    COMPACT_MEDIA,
    COMPACT_MODES,
    COMPACT_TIMER,
    DOCK_MAX,
    EW,
    HOTKEY_ID,
    HOTKEY_LAUNCH,
    HOVER_DELAY,
    LEAVE_DELAY,
    PAD,
    TAB_H,
    TOP_MARGIN,
    WIN_H,
    WIN_W,
)

user32 = ctypes.windll.user32


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]


class Island(IslandPainting, QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFixedSize(WIN_W, WIN_H)
        self.setWindowTitle(tr("app.name"))
        self.place()
        self.hwnd = int(self.winId())
        system.set_exstyle(self.hwnd, system.WS_EX_NOACTIVATE, True)
        self.click_through = None
        self.ui = UI(self)

        self.w, self.h = COMPACT
        self.vw = self.vh = 0.0
        self.mode = self.prev_mode = "compact"
        self.mode_t = 0.0
        self.slide_dir = 0
        self.moving = False
        self._cc = {}
        self.dock_alpha = 0.0
        self.dock_hover = None
        self._dock_sig = None
        self.last_tick = time.time()
        self.t0 = time.time()

        self.hovered = self.pinned = self.hover_block = False
        self.enter_at = self.leave_at = None
        self.mouse = QPointF(-1, -1)
        self.hits, self.sliders, self.scroll_regions = [], [], []
        self.scrolls, self.scroll_content = {}, {}
        self.clip_rect = None
        self._reg = False
        self.drag = None
        self.fields, self.field_handlers = {}, {}
        self.focus_field = None
        self.prev_fg = None

        # alertes
        self.alert = None
        self.alert_until = 0.0

        self.media = None
        self.media_at = 0.0
        self.media_key = None
        self.first_media = True
        self.art = None
        self.thumb_bytes = None
        self.accent = QColor(T.accent)
        self.media_exe = None      # playing app executable, used for its icon
        self._media_app_key = None

        self.audio = system.Audio()
        self.bright = system.Brightness()
        self.dnd = system.DoNotDisturb()
        self.radio = system.RadioWorker()
        self.radio.updated.connect(self.on_radios)
        self.radio.start()
        self.wifi = self.bt = None
        self.night = system.night_light_on()
        self.night_ok = system.night_light_supported()
        self.cam_allowed = system.camera_allowed()
        self.cam_busy = self.mic_busy = False
        self.caps, self.num = system.caps_lock(), system.num_lock()
        self.vol, self.muted = self.audio.volume(), self.audio.muted()
        self.out_id = self.audio.default_id()
        psutil.cpu_percent(None)
        self.battery = None
        self.plugged = None
        self.low_warned = False
        self._dnd_by_focus = False

        self.clip = ClipboardHistory(QApplication.clipboard())
        self.agenda = Agenda()
        self.timers = Timers()
        self.tasks = Tasks()
        self.infos = Infos()
        self.dev = Dev()
        self.files = Files()
        self.launcher = Launcher()
        self.phone = Phone(self.files)
        self.wallet = Binance()
        self.net = Networks()
        self.hotspot = Hotspot()
        self.hotspot.alert.connect(lambda title, subtitle, ok: self.show_alert(
            "hotspot", title, subtitle, T.success if ok else T.critical, chr(0xE88A), duration=5))
        self.net.alert.connect(lambda kind, title, subtitle, ok: self.show_alert(
            "net", title, subtitle, T.success if ok else T.critical,
            G["wifi"] if kind == "wifi" else G["bt"], duration=4))
        QTimer.singleShot(4000, lambda: (self.net.scan_wifi(active=False), self.net.refresh_bt()))
        self.files.alert.connect(self.on_files_alert)
        self.launcher.output.connect(lambda t, s_: self.show_alert("launch", t, s_, T.accent, G["terminal"]))
        self.phone.alert.connect(self.on_phone_alert)
        self.phone.text_received.connect(self.on_phone_text)
        self.phone.remote.connect(self.on_remote)
        QApplication.clipboard().dataChanged.connect(self.on_clipboard_for_phone)
        self.draggables, self._press = [], None
        self.drop_hover = self.drag_out = False
        self.setAcceptDrops(True)
        self.agenda.reminder.connect(self.on_event_reminder)
        self.tasks.reminder.connect(self.on_task_reminder)
        self.timers.fired.connect(self.on_timer_fired)
        self.dev.alert.connect(self.on_dev_alert)

        self.tabs = {}
        for cls in TABS:
            t = cls(self)
            self.tabs[t.key] = t
        self.tab_keys = list(self.tabs)
        self.tab = "home"
        self.tab_x = 0.0
        self._language_unsubscribe = on_language_changed(self._language_changed)

        self.update_stats()

        self.anim = QTimer(self)
        self.anim.setTimerType(Qt.TimerType.PreciseTimer)
        self.anim.timeout.connect(self.tick)
        self.anim.start(8)
        self._fast_t = self._mid_t = 0.0
        QTimer(self, interval=1500, timeout=self.update_stats).start()
        QTimer(self, interval=2000, timeout=self.stay_on_screen).start()
        QTimer(self, interval=400, timeout=self.enforce_taskbar).start()
        QTimer(self, interval=1000, timeout=self.refresh_visible).start()
        QTimer(self, interval=5000, timeout=Collection.sync_all).start()
        QTimer(self, interval=15000, timeout=self.check_reminders).start()

        # pre-warm each tab's fonts (avoids a stutter on first display)
        QTimer.singleShot(1500, self.warmup)

        self.worker = MediaWorker()
        self.worker.updated.connect(self.on_media)
        self.worker.start()
        user32.RegisterHotKey(self.hwnd, HOTKEY_ID, 0x0002 | 0x0001 | 0x4000, 0x56)  # Ctrl+Alt+V
        user32.RegisterHotKey(self.hwnd, HOTKEY_LAUNCH, 0x0002 | 0x0001 | 0x4000, 0x20)  # Ctrl+Alt+Space

    def _language_changed(self, _language):
        """Refresh translated labels and discard cached translated pixmaps."""
        self.setWindowTitle(tr("app.name"))
        self._cc.clear()
        self.update()

    def place(self):
        geo = QApplication.primaryScreen().geometry()
        self.move(geo.x() + (geo.width() - WIN_W) // 2, geo.y() + TOP_MARGIN)

    def pill_rect(self):
        return QRectF((WIN_W - self.w) / 2, PAD, self.w, self.h)

    @property
    def is_open(self):
        return (self.hovered or self.pinned or self.focus_field is not None or self.drag is not None
                or self.drop_hover)

    def compact_mode(self):
        now = time.time()
        if self.timers.active():
            return COMPACT_TIMER, "ctimer"
        if now - getattr(self, "_nxt_t", 0) > 1:
            self._nxt_t, self._nxt = now, self.agenda.next_timed()
        nxt = self._nxt
        if nxt and nxt["start"] - now <= 15 * 60 and now < nxt["start"] + 5 * 60:
            return COMPACT_MEET, "cmeet"
        if self.media:
            return COMPACT_MEDIA, "cmedia"
        if self.dev.build and self.dev.build.get("running"):
            return COMPACT_BUILD, "cbuild"
        return COMPACT, "compact"

    def target(self):
        if self.alert and time.time() < self.alert_until and not self.is_open:
            w = ALERT[0] + (90 if self.alert.get("action") else 0)
            return (w, ALERT[1]), "alert"
        if self.is_open:
            return (EW, TAB_H + self.tabs[self.tab].height()), "tab:" + self.tab
        return self.compact_mode()

    def tick(self):
        now = time.time()
        dt_ = min(0.05, max(0.001, now - self.last_tick))
        self.last_tick = now
        if T.check():
            self.update()

        self.mouse = QPointF(self.mapFromGlobal(QCursor.pos()))
        m = 10 if self.is_open else 6
        inside = self.isVisible() and self.pill_rect().adjusted(-m, -m - PAD, m, m + 4).contains(self.mouse)

        dock_r, dock_items = self.dock_layout()
        in_dock = dock_r is not None and self.dock_alpha > 0.5 and dock_r.adjusted(-4, -PAD, 4, 4).contains(self.mouse)
        hov = None
        if in_dock:
            for i, (rr, _g) in enumerate(dock_items):
                if rr.contains(self.mouse):
                    hov = i
        dock_changed = hov != self.dock_hover
        self.dock_hover = hov
        want = 1.0 if (self.dock_enabled and not self.is_open and self.launcher.running) else 0.0
        self.dock_alpha += (want - self.dock_alpha) * min(1.0, dt_ * 12)
        if abs(want - self.dock_alpha) < 0.01:
            self.dock_alpha = want
        sig = tuple((g["key"], len(g["windows"])) for g in self.launcher.running[:DOCK_MAX + 1])
        sig += (user32.GetForegroundWindow(),)
        if sig != self._dock_sig:
            self._dock_sig = sig
            dock_changed = True
        through = not (inside or in_dock) and self.drag is None and self.focus_field is None
        if through != self.click_through:
            system.set_exstyle(self.hwnd, system.WS_EX_TRANSPARENT, through)
            self.click_through = through

        if inside:
            self.leave_at = None
            if not self.hovered and not self.hover_block:
                if self.enter_at is None:
                    self.enter_at = now
                elif now - self.enter_at >= HOVER_DELAY:
                    self.hovered = True
        else:
            self.enter_at = None
            self.hover_block = False
            if self.hovered:
                if self.leave_at is None:
                    self.leave_at = now
                elif now - self.leave_at >= LEAVE_DELAY:
                    self.hovered = False

        if (self.pinned or self.focus_field) and not inside and user32.GetAsyncKeyState(0x01) & 0x8000:
            self.close_island(restore_focus=False)

        (tw, th), mode = self.target()
        if mode != self.mode:
            if mode.startswith("tab:") and self.mode.startswith("tab:"):
                a, b = self.tab_keys.index(self.mode[4:]), self.tab_keys.index(mode[4:])
                self.slide_dir = 1 if b > a else -1
            else:
                self.slide_dir = 0
            self.prev_mode, self.mode, self.mode_t = self.mode, mode, now
            if mode.startswith("tab:"):
                t = self.tabs[mode[4:]]
                if hasattr(t, "on_open"):
                    t.on_open()
        self.w, self.vw = spring(self.w, self.vw, tw, 430, dt_)
        self.h, self.vh = spring(self.h, self.vh, th, 520, dt_)
        moving = abs(self.vw) > 2 or abs(self.vh) > 2 or abs(tw - self.w) > 0.3 or abs(th - self.h) > 0.3
        if not moving:
            self.w, self.h, self.vw, self.vh = tw, th, 0.0, 0.0
        self.moving = moving

        idx = self.tab_keys.index(self.tab)
        self.tab_x += (idx - self.tab_x) * min(1.0, dt_ * 18)
        for k, (cur, tgt) in list(self.scrolls.items()):
            if abs(tgt - cur) > 0.3:
                self.scrolls[k] = (cur + (tgt - cur) * min(1.0, dt_ * 16), tgt)
            elif cur != tgt:
                self.scrolls[k] = (tgt, tgt)

        if now - self._fast_t > 0.12:
            self._fast_t = now
            self.poll_fast()
        if now - self._mid_t > 0.25:
            self._mid_t = now
            self.timers.tick()

        fading = now - self.mode_t < 0.35
        scrolling = any(abs(c - t) > 0.3 for c, t in self.scrolls.values())
        animating = (moving or fading or abs(idx - self.tab_x) > 0.002 or scrolling
                     or 0.0 < self.dock_alpha < 1.0)
        live = bool(self.media and self.media["playing"]) or self.timers.active() is not None or bool(self.focus_field)
        self.anim.setInterval(7 if animating else (16 if (live or inside) else 40))
        # repaint only when something changes (mouse, animation, live content)
        moved = self.mouse != getattr(self, "_last_mouse", None)
        self._last_mouse = QPointF(self.mouse)
        since = now - getattr(self, "_last_paint", 0)
        need = (animating or self.drag or (inside and moved) or dock_changed or int(now) != int(now - dt_)
                or (live and since > (0.033 if self.media and self.media["playing"] else 0.25))
                or (self.is_open and since > 0.5))
        if need:
            self._last_paint = now
            # refresh region: current + previous island (+ shadow), not the whole window
            r = self.pill_rect().adjusted(-14, -PAD, 14, 14).toAlignedRect()
            if dock_r is not None or self.dock_alpha > 0:  # dock and its hover label
                r = r.united(QRectF(self.pill_rect().right(), 0, WIN_W - self.pill_rect().right(), 100).toAlignedRect())
            prev = getattr(self, "_last_dirty", r)
            self._last_dirty = r
            self.update(r.united(prev))

    def poll_fast(self):
        v, m = self.audio.volume(), self.audio.muted()
        if (abs(v - self.vol) > 0.004 or m != self.muted) and self.drag is None:
            if not (self.is_open and self.tab == "controls"):
                self.show_alert("volume", tr("island.volume.muted") if m else tr("island.volume.title"),
                                "", T.text, G["mute"] if m else G["vol"], bar=0 if m else v)
        self.vol, self.muted = v, m
        caps, num = system.caps_lock(), system.num_lock()
        if caps != self.caps:
            self.show_alert("key", tr("island.keyboard.caps_on" if caps else "island.keyboard.caps_off"),
                            tr("island.keyboard.subtitle"), T.success if caps else T.text, G["keyboard"])
        if num != self.num:
            self.show_alert("key", tr("island.keyboard.num_on" if num else "island.keyboard.num_off"),
                            tr("island.keyboard.subtitle"), T.success if num else T.text, G["keyboard"])
        self.caps, self.num = caps, num

    def refresh_visible(self):
        self.dev.visible = self.is_open and self.tab == "dev"
        self.launcher.running_visible = (self.is_open and self.tab == "launcher"
                                         and self.tabs["launcher"].view == "running")
        vis = self.is_open and self.tab == "wallet"
        if vis and not self.wallet.visible:
            self.wallet.refresh()
        self.wallet.visible = vis
        if self.is_open and self.tab == "controls" and self.drag is None:
            self._ctl_n = getattr(self, "_ctl_n", 0) + 1
            self.tabs["controls"].refresh(brightness=self._ctl_n % 5 == 0)

    def check_reminders(self):
        self.agenda.check_reminders()
        self.tasks.check_reminders()

    def update_stats(self):
        self.night = system.night_light_on()
        self.cam_allowed = system.camera_allowed()
        cam = system.camera_in_use()
        if cam and not self.cam_busy:
            self.show_alert("cam", tr("island.camera.active"), tr("island.camera.active_hint"),
                            T.success, G["cam"])
        self.cam_busy = cam
        self.mic_busy = system.mic_in_use()
        dev = self.audio.default_id()
        if dev != self.out_id:
            self.out_id = dev
            self.audio.refresh()
            self.show_alert("output", tr("island.audio.output"), self.audio.device_name, T.accent,
                            G["headphone"] if self.headphones() else G["speaker"])
        b = psutil.sensors_battery()
        if b is None:
            self.battery = None
            return
        pct = int(round(b.percent))
        self.battery = (pct, b.power_plugged)
        if self.plugged is not None and b.power_plugged != self.plugged:
            if b.power_plugged:
                self.show_alert("charge", tr("island.battery.charging"),
                                tr("island.battery.charging_value", percent=pct), T.success, G["charging"])
            else:
                self.show_alert("battery", tr("island.battery.on_battery"),
                                tr("island.battery.remaining", percent=pct), T.text, G["battery"])
        self.plugged = b.power_plugged
        if not b.power_plugged and pct <= 20 and not self.low_warned:
            self.low_warned = True
            self.show_alert("battery", tr("island.battery.low"),
                            tr("island.battery.remaining", percent=pct), T.critical, G["battery"])
        if b.power_plugged or pct > 25:
            self.low_warned = False

    def headphones(self):
        n = self.audio.device_name.lower()
        return any(k in n for k in ("casque", "headphone", "headset", "écouteurs", "airpods", "buds"))

    def on_radios(self, st):
        self.wifi, self.bt = st.get("wifi"), st.get("bluetooth")

    def on_media(self, info):
        if info is None:
            self.media = None
            self.media_key = None
            return
        key = (info["title"], info["artist"])
        if info["thumb"] is not self.thumb_bytes:
            self.thumb_bytes = info["thumb"]
            self.art = None
            if info["thumb"]:
                img = QImage.fromData(info["thumb"])
                if not img.isNull():
                    side = min(img.width(), img.height())
                    img = img.copy((img.width() - side) // 2, (img.height() - side) // 2, side, side)
                    self.art = QPixmap.fromImage(img.scaled(160, 160, Qt.AspectRatioMode.IgnoreAspectRatio,
                                                            Qt.TransformationMode.SmoothTransformation))
                    self.accent = accent_from(img)
            if self.art is None:
                self.accent = QColor(T.accent)
        if key != self.media_key:
            if not self.first_media and info["playing"]:
                self.show_alert("media", info["title"], info["artist"] or info["app"], self.accent)
            self.media_key = key
        self.first_media = False
        if self.media and time.time() - self.media.get("local_t", 0) < 1.2:
            info["playing"] = self.media["playing"]
            info["local_t"] = self.media["local_t"]
        self.media = info
        self.media_at = time.time()
        app_key = (info.get("aumid"), info["title"])
        if app_key != self._media_app_key:
            self._media_app_key = app_key
            def find(a=info.get("aumid"), t=info["title"]):
                self.media_exe = system.find_app_window(a, t)[1]
            threading.Thread(target=find, daemon=True).start()

    def media_position(self):
        m = self.media
        pos = m["position"]
        if m["playing"]:
            pos += max(0.0, time.time() - (m["updated_at"] or self.media_at))
        return min(pos, m["duration"]) if m["duration"] > 0 else pos

    def open_media_app(self):
        """Open the application that is playing media (Spotify, browser, player…)."""
        m = self.media
        if not m:
            return
        self.close_island(restore_focus=False)
        if not system.open_media_app(m.get("aumid", ""), m["title"]):
            self.show_alert("media", tr("island.media.app_not_found"), m.get("app") or "",
                            T.critical, G["error"])

    def media_cmd(self, name, arg=None):
        self.worker.command(name, arg)
        if not self.media:
            return
        if name == "play_pause":
            self.media["position"] = self.media_position()
            self.media["updated_at"] = time.time()
            self.media["playing"] = not self.media["playing"]
            self.media["local_t"] = time.time()
        elif name == "seek":
            self.media["position"] = arg
            self.media["updated_at"] = time.time()

    def show_alert(self, kind, title, subtitle, color, glyph=None, bar=None, action=None, duration=ALERT_TIME):
        self.alert = {"kind": kind, "title": title, "subtitle": subtitle, "color": QColor(color), "glyph": glyph,
                      "bar": bar, "action": action}
        self.alert_until = time.time() + duration

    def notify(self, title, msg):
        if hasattr(self, "tray") and not self.dnd.on:
            self.tray.showMessage(title, msg, QSystemTrayIcon.MessageIcon.Information, 6000)

    def on_timer_fired(self, kind, title, sub):
        stop = lambda: winsound.PlaySound(None, 0)
        if kind == "alarm":
            self.show_alert("alarm", title, sub, T.orange, G["alarm"],
                            action=(tr("common.stop"), stop), duration=30)
        elif kind == "pomodoro":
            self.show_alert("pomo", title, sub, T.success, G["focus"], duration=6)
        else:
            self.show_alert("timer", title, sub, T.accent, G["timer"],
                            action=(tr("common.ok"), stop), duration=12)
        self.notify(title, sub)

    def on_event_reminder(self, event):
        sub = until(event["start"] - time.time()).capitalize() + " · " + format_time(
            dt.datetime.fromtimestamp(event["start"])
        )
        action = (tr("common.join"), lambda url=event["meet_url"]: self.open_url(url)) \
            if event.get("meet_url") else None
        self.show_alert("event", event["title"], sub, T.accent,
                        G["video"] if event.get("meet_url") else G["calendar"],
                        action=action, duration=15)
        self.notify(tr("island.notify.event", title=event["title"]), sub)

    def on_task_reminder(self, task):
        self.show_alert("task", task["title"], tr("island.notify.task_reminder"), T.orange, G["tasks"],
                        action=(tr("common.done"), lambda task=task: self.tasks.toggle(task)), duration=12)
        self.notify(tr("island.notify.task", title=task["title"]), tr("island.notify.task"))

    def on_dev_alert(self, kind, title, sub):
        ok = kind.endswith("_ok")
        self.show_alert(kind, title, sub, T.success if ok else T.critical,
                        G["check"] if ok else G["error"], duration=4 if ok else 8)
        if not ok:
            self.notify(title, sub)

    def set_tab(self, tab):
        if tab != self.tab and self.focus_field:
            self.unfocus(restore=False)
        self.tab = tab

    def open_url(self, url):
        if url:
            webbrowser.open(url)
            self.close_island(restore_focus=False)

    def copy_text(self, text):
        QApplication.clipboard().setText(text)
        self.show_alert("clip", tr("common.copied"), text.split("\n")[0][:60], T.accent, G["copy"], duration=1.4)

    def copy_item(self, item):
        if self.clip.copy(item):
            self.show_alert("clip", tr("common.copied"), (item.get("text") or "").split("\n")[0][:60],
                            T.accent, G["copy"], duration=1.4)

    def paste_item(self, item):
        target = self.prev_fg if self.focus_field else user32.GetForegroundWindow()
        if not target or target == self.hwnd:
            target = self.prev_fg
        if not self.clip.copy(item):
            return
        self.close_island(restore_focus=False)
        if target:
            system.force_foreground(target)
        QTimer.singleShot(120, system.send_ctrl_v)
        self.show_alert("clip", tr("island.clipboard.pasted"), (item.get("text") or "").split("\n")[0][:60],
                        T.success, G["clip"], duration=1.4)

    def close_island(self, restore_focus=True):
        self.pinned = self.hovered = False
        self.hover_block = True
        self.unfocus(restore=restore_focus)
        if hasattr(self, "pin_action"):
            self.pin_action.setChecked(False)

    def open_clipboard(self):
        self.tab = "clip"
        self.pinned = True
        self.fields["clip_search"] = ""
        self.scrolls.pop("clip", None)
        self.focus("clip_search")

    def set_focus(self, on):
        self.timers.set_focus(on)
        if on and not self.dnd.on:
            self.dnd.toggle()
            self._dnd_by_focus = True
        elif not on and self._dnd_by_focus:
            if self.dnd.on:
                self.dnd.toggle()
            self._dnd_by_focus = False
        self.show_alert("focus", tr("island.focus.enabled" if on else "island.focus.disabled"),
                        tr("island.focus.active_hint", minutes=self.timers.pomo_cfg["work"]) if on
                        else tr("island.focus.done"), T.accent, G["focus"])

    def airplane_on(self):
        st = [x for x in (self.wifi, self.bt) if x is not None]
        return bool(st) and not any(st)

    def toggle_radio(self, kind):
        cur = self.wifi if kind == "wifi" else self.bt
        if cur is None:
            return
        if kind == "wifi":
            self.wifi = not cur
        else:
            self.bt = not cur
        self.radio.set_radio(kind, not cur)

    def toggle_airplane(self):
        on = not self.airplane_on()
        self.radio.set_airplane(on)
        if on:
            self.wifi = False if self.wifi is not None else None
            self.bt = False if self.bt is not None else None

    def toggle_night(self):
        target = not self.night
        if system.set_night_light(target):
            self.night = target
            return
        self.show_alert("night", tr("controls.tiles.night_light"),
                        tr("controls.night_settings_hint"), T.caution, G["night"])
        self.open_url("ms-settings:nightlight")

    def toggle_camera(self):
        system.set_camera_allowed(not self.cam_allowed)
        self.cam_allowed = not self.cam_allowed

    def focus(self, name):
        if self.focus_field is None:
            fg = user32.GetForegroundWindow()
            if fg and fg != self.hwnd:
                self.prev_fg = fg
            system.set_exstyle(self.hwnd, system.WS_EX_NOACTIVATE, False)
            system.force_foreground(self.hwnd)
            self.activateWindow()
            self.setFocus()
        self.focus_field = name

    def unfocus(self, restore=True):
        if self.focus_field is None:
            return
        self.focus_field = None
        system.set_exstyle(self.hwnd, system.WS_EX_NOACTIVATE, True)
        if restore and self.prev_fg:
            system.force_foreground(self.prev_fg)

    def stay_on_screen(self):
        """Keep the island visible above everything, even fullscreen applications."""
        if not self.isVisible():
            self.show()
            system.set_exstyle(self.hwnd, system.WS_EX_NOACTIVATE, self.focus_field is None)
        system.keep_topmost(self.hwnd)

    @property
    def taskbar_hidden(self):
        return settings.get("hide_taskbar", True)

    def apply_taskbar(self):
        if self.taskbar_hidden:
            if "taskbar_prev_autohide" not in settings:
                settings.set("taskbar_prev_autohide", system.taskbar_autohide())
            system.set_taskbar_autohide(True)
            system.hide_taskbar()
        else:
            self.restore_taskbar()

    def restore_taskbar(self):
        system.show_taskbar()
        if "taskbar_prev_autohide" in settings:
            system.set_taskbar_autohide(bool(settings.pop("taskbar_prev_autohide")))
            settings.save()

    def set_taskbar_hidden(self, on):
        settings.set("hide_taskbar", on)
        self.apply_taskbar()

    def enforce_taskbar(self):
        """Windows shows the taskbar again on hover, Start click or Explorer restart; hide it again."""
        if self.taskbar_hidden and system.hide_taskbar():
            system.set_taskbar_autohide(True)

    def check_fullscreen(self):
        fs = self.foreground_fullscreen()
        if fs and self.isVisible():
            self.hide()
        elif not fs and not self.isVisible():
            self.show()
            system.set_exstyle(self.hwnd, system.WS_EX_NOACTIVATE, self.focus_field is None)

    def foreground_fullscreen(self):
        hwnd = user32.GetForegroundWindow()
        if not hwnd or hwnd == self.hwnd:
            return False
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls, 256)
        if cls.value in ("Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"):
            return False
        r = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(r))
        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(mi)
        user32.GetMonitorInfoW(user32.MonitorFromWindow(hwnd, 2), ctypes.byref(mi))
        m = mi.rcMonitor
        return r.left <= m.left and r.top <= m.top and r.right >= m.right and r.bottom >= m.bottom

    def nativeEvent(self, event_type, message):
        try:
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == 0x0312 and msg.wParam == HOTKEY_ID:
                if self.is_open and self.tab == "clip":
                    self.close_island()
                else:
                    self.open_clipboard()
                return True, 0
            if msg.message == 0x0312 and msg.wParam == HOTKEY_LAUNCH:
                if self.is_open and self.tab == "launcher":
                    self.close_island()
                else:
                    self.tab = "launcher"
                    self.pinned = True
                    self.fields["launch_search"] = ""
                    self.focus("launch_search")
                return True, 0
        except Exception:
            pass
        return False, 0

    def changeEvent(self, e):
        if e.type() == e.Type.ActivationChange and not self.isActiveWindow() and self.focus_field:
            self.focus_field = None
            system.set_exstyle(self.hwnd, system.WS_EX_NOACTIVATE, True)
        super().changeEvent(e)

    def mousePressEvent(self, e):
        pos = QPointF(e.position())
        dock_r, dock_items = self.dock_layout()
        if dock_r is not None and self.dock_alpha > 0.5 and dock_r.contains(pos):
            for rr, g in dock_items:
                if rr.contains(pos):
                    if g is None:  # “+N”: all applications in the launcher
                        self.tab = "launcher"
                        self.tabs["launcher"].set_view("running")
                        self.pinned = True
                    elif e.button() == Qt.MouseButton.RightButton:
                        self.dock_menu(g)
                    else:
                        self.dock_activate(g)
                    self.update()
            return
        if not self.pill_rect().contains(pos):
            return
        if e.button() == Qt.MouseButton.RightButton:
            self.tray_menu.popup(QCursor.pos())
            return
        for hit, setter, _v, track in reversed(self.sliders):
            if hit.contains(pos):
                self.drag = (track, setter)
                self._drag_to(pos)
                return
        for rect, fn in reversed(self.hits):
            if rect.contains(pos):
                fn()
                self.update()
                return
        for rect, paths, click in reversed(self.draggables):
            if rect.contains(pos):
                self._press = (pos, paths, click)  # click or drag decided on move/release
                return
        if self.focus_field:
            self.unfocus(restore=False)
        if self.mode == "alert":
            a = self.alert or {}
            self.alert_until = 0
            goto = {"media": "home", "volume": "controls", "output": "controls", "clip": "clip", "timer": "timers",
                    "alarm": "timers", "pomo": "timers", "event": "agenda", "task": "tasks", "ci_fail": "dev",
                    "build_fail": "dev", "build_ok": "dev", "ci_ok": "dev", "phone": "phone", "phone_notif": "phone",
                    "phone_call": "phone", "phone_file": "files", "files": "files", "download": "files",
                    "launch": "launcher", "wallet": "wallet"}.get(a.get("kind"))
            if goto:
                self.tab = goto
                self.pinned = True
            return
        if self.mode in COMPACT_MODES:
            self.tab = {"cmedia": "home", "ctimer": "timers", "cmeet": "agenda", "cbuild": "dev"}.get(self.mode, self.tab)
            self.pinned = True
            if hasattr(self, "pin_action"):
                self.pin_action.setChecked(True)

    def _drag_to(self, pos):
        rect, setter = self.drag
        setter(max(0.0, min(1.0, (pos.x() - rect.left()) / rect.width())))

    def mouseMoveEvent(self, e):
        if self.drag:
            self._drag_to(QPointF(e.position()))
        elif self._press:
            pos, paths, _click = self._press
            if (QPointF(e.position()) - pos).manhattanLength() > 8:
                self._press = None
                self.start_file_drag(paths)

    def mouseReleaseEvent(self, e):
        if self.drag:
            self.drag = None
            self.refresh_visible()
        if self._press:
            _pos, _paths, click = self._press
            self._press = None
            click()

    def start_file_drag(self, paths):
        """Drag files from the island to another application (Explorer, email, browser…)."""
        md = QMimeData()
        md.setUrls([QUrl.fromLocalFile(p) for p in paths])
        drag = QDrag(self)
        drag.setMimeData(md)
        pm = QPixmap(220, 36)
        pm.fill(Qt.GlobalColor.transparent)
        q = QPainter(pm)
        q.setRenderHint(QPainter.RenderHint.Antialiasing)
        q.setBrush(QColor(0, 0, 0, 230))
        q.setPen(QPen(T.stroke2, 1))
        q.drawRoundedRect(QRectF(0.5, 0.5, 219, 35), 6, 6)
        q.setPen(T.text)
        q.setFont(font(9, W.Medium))
        name = os.path.basename(paths[0]) + (f"  +{len(paths) - 1}" if len(paths) > 1 else "")
        q.drawText(QRectF(12, 0, 200, 36), int(LEFT), name)
        q.end()
        drag.setPixmap(pm)
        drag.setHotSpot(pm.rect().center())
        self.drag_out = True
        drag.exec(Qt.DropAction.CopyAction | Qt.DropAction.MoveAction, Qt.DropAction.CopyAction)
        self.drag_out = False
        self.files.changed.emit()

    def dragEnterEvent(self, e):
        md = e.mimeData()
        if self.drag_out or not md.hasUrls() or not any(u.isLocalFile() for u in md.urls()):
            e.ignore()
            return
        e.acceptProposedAction()
        self.drop_hover = True
        self.tab = "files"
        self.tabs["files"].set_view("shelf")

    def dragMoveEvent(self, e):
        if self.drop_hover:
            e.acceptProposedAction()

    def dragLeaveEvent(self, e):
        self.drop_hover = False

    def dropEvent(self, e):
        self.drop_hover = False
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        n = self.files.add_to_shelf(paths)
        e.acceptProposedAction()
        self.pinned = True
        title = (tr("island.files.pending", count=n) if n
                 else tr("island.files.already_on_shelf"))
        self.show_alert("files", title, os.path.basename(paths[0]) if paths else "",
                        T.accent, G["folder"])

    def copy_files(self, paths):
        md = QMimeData()
        md.setUrls([QUrl.fromLocalFile(p) for p in paths])
        QApplication.clipboard().setMimeData(md)
        self.show_alert("files", tr("island.files.copied", count=len(paths)),
                        tr("island.files.paste_hint"), T.accent, G["copy"], duration=2)

    def on_phone_text(self, text):
        self._from_phone = text
        QApplication.clipboard().setText(text)
        self.show_alert("phone", tr("island.phone.received"),
                        tr("island.phone.received_text", text=" ".join(text.split())[:70]),
                        T.accent, G["phone"])

    def on_clipboard_for_phone(self):
        ph = self.phone
        if not (ph.sync_clip and ph.running):
            return
        t = QApplication.clipboard().text()
        if t and t != getattr(self, "_from_phone", None) and (not ph.outbox or ph.outbox[0]["text"] != t):
            ph.push_text(t, "clip")

    def on_phone_alert(self, kind, title, sub, data):
        if kind == "phone_call":
            self.show_alert(kind, title, sub or tr("island.phone.incoming_call"), T.success,
                            G["phone"], duration=20,
                            action=(tr("common.link"), lambda: self.tabs["phone"]._open_link()))
        elif kind == "phone_file":
            self.show_alert(kind, title, sub, T.accent, G["phone"], duration=6,
                            action=(tr("common.open"), lambda: self.files.open(data)))
        elif kind == "phone_err":
            self.show_alert(kind, title, sub, T.critical, G["error"], duration=6)
        else:
            self.show_alert(kind, title, sub, T.accent, G["bell"], duration=5)

    def on_remote(self, action, arg):
        keys = {"play": 0xB3, "next": 0xB0, "prev": 0xB1, "volup": 0xAF, "voldown": 0xAE, "mute": 0xAD,
                "left": 0x25, "right": 0x27, "space": 0x20}
        if action in keys:
            vk = keys[action]
            user32.keybd_event(vk, 0, 0, 0)
            user32.keybd_event(vk, 0, 2, 0)
        elif action == "open" and arg.lower().startswith(("http://", "https://")):
            webbrowser.open(arg)

    def on_files_alert(self, kind, title, path):
        if kind == "download":
            self.show_alert(kind, title, os.path.basename(path), T.success, "\ue896", duration=6,
                            action=(tr("common.open"), lambda path=path: self.files.open(path)))
        else:
            self.show_alert(kind, title, path, T.accent, G["folder"])

    def wheelEvent(self, e):
        pos = QPointF(e.position())
        steps = e.angleDelta().y() / 120
        for hit, setter, val, _t in reversed(self.sliders):
            if hit.contains(pos):
                setter(max(0.0, min(1.0, val + steps * 0.04)))
                return
        for rect, key, mx in reversed(self.scroll_regions):
            if rect.contains(pos):
                cur, tgt = self.scrolls.get(key, (0.0, 0.0))
                self.scrolls[key] = (cur, max(0.0, min(mx, tgt - steps * 60)))
                return
        if self.mode in COMPACT_MODES:
            self.audio.set_volume(self.audio.volume() + steps * 0.04)

    def keyPressEvent(self, e):
        name = self.focus_field
        if not name:
            return
        tab = self.tabs.get(self.tab)
        if name in ("clip_search", "launch_search") and hasattr(tab, "key_event") and e.key() != Qt.Key.Key_Escape \
                and tab.key_event(e):
            self.update()
            return
        k = e.key()
        mods = e.modifiers()
        val = self.fields.get(name, "")
        on_submit, on_change = self.field_handlers.get(name, (None, None))
        changed = False
        if k == Qt.Key.Key_Escape:
            if val:
                self.fields[name] = ""
                changed = True
            else:
                self.unfocus()
                if self.pinned and not self.hovered:
                    self.close_island()
        elif k in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if on_submit and val.strip():
                if on_submit(val):
                    self.fields[name] = ""
                    changed = True
        elif k == Qt.Key.Key_Backspace:
            if mods & Qt.KeyboardModifier.ControlModifier:
                v = val.rstrip()
                self.fields[name] = v[: max(0, v.rfind(" ") + 1)]
            else:
                self.fields[name] = val[:-1]
            changed = True
        elif k == Qt.Key.Key_V and mods & Qt.KeyboardModifier.ControlModifier:
            txt = QApplication.clipboard().text()
            if name != "note_add":
                txt = " ".join(txt.split())
            self.fields[name] = val + txt
            changed = True
        elif e.text() and e.text().isprintable() and not (mods & Qt.KeyboardModifier.ControlModifier):
            self.fields[name] = val + e.text()
            changed = True
        if changed and on_change:
            on_change(self.fields.get(name, ""))
        self.update()

    def shutdown(self):
        unsubscribe = getattr(self, "_language_unsubscribe", None)
        if unsubscribe:
            unsubscribe()
        self.restore_taskbar()
        user32.UnregisterHotKey(self.hwnd, HOTKEY_ID)
        user32.UnregisterHotKey(self.hwnd, HOTKEY_LAUNCH)
        if self.timers.focus:
            self.set_focus(False)
        self.worker.stop()
        self.radio.stop()
        try:
            self.clip.save()
        except Exception:
            pass
