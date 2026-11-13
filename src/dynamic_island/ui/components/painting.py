"""Island painting: pill, tabs, dock, alerts and render caching."""
import ctypes
import datetime as dt
import math
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QMenu, QMessageBox

from dynamic_island.core.config.settings import settings
from dynamic_island.core.localization import format_time, translate as tr
from dynamic_island.core.utilities.animation import smooth
from dynamic_island.core.utilities.formatting import fmt_dur, until
from dynamic_island.services import system
from dynamic_island.ui.components.drawing import CENTER, RIGHT
from dynamic_island.ui.tabs import TAB_VIEWS
from dynamic_island.ui.themes import G, R_COMPACT, R_OPEN, T, W, font
from dynamic_island.ui.windows.layout import DOCK_CELL, DOCK_MAX, EW, MENU_QSS, PAD, TAB_H, WIN_W

user32 = ctypes.windll.user32


def accent_from(img: QImage) -> QColor:
    small = img.scaled(10, 10, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    best, score = None, -1
    for x in range(small.width()):
        for y in range(small.height()):
            c = QColor(small.pixel(x, y))
            s = c.hsvSaturationF() * c.valueF()
            if s > score:
                best, score = c, s
    if best is None or score < 0.15:
        return QColor(T.accent)
    return QColor.fromHsv(best.hsvHue(), min(255, max(140, best.hsvSaturation())), max(200, best.value()))


class IslandPainting:

    def draw_art(self, p, rect, radius):
        clip = QPainterPath()
        clip.addRoundedRect(rect, radius, radius)
        p.save()
        p.setClipPath(clip, Qt.ClipOperation.IntersectClip)
        if self.art:
            p.drawPixmap(rect.toRect(), self.art)
        else:
            p.fillRect(rect, T.layer2)
            self.ui.glyph(rect.center(), G["music"], rect.height() * 0.42, T.text3)
        p.restore()

    def draw_eq(self, p, rect, color):
        n = 4
        bw = rect.width() / (n * 2 - 1)
        t = time.time() - self.t0
        playing = self.media and self.media["playing"]
        p.save()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        for i in range(n):
            k = 0.25 + 0.75 * abs(math.sin(t * (5.1 + i * 1.7) + i * 1.3) * math.sin(t * (2.3 + i * 0.6))) \
                if playing else 0.18
            bh = max(bw, rect.height() * k)
            p.drawRoundedRect(QRectF(rect.left() + i * bw * 2, rect.center().y() - bh / 2, bw, bh), bw / 2, bw / 2)
        p.restore()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        ui = self.ui
        ui.p = p

        self.paint_dock(p)
        r = self.pill_rect()
        radius = R_OPEN if self.h > 60 else min(R_COMPACT, r.height() / 2)
        self.paint_shadow(p, r, radius)
        path = QPainterPath()
        path.addRoundedRect(r, radius, radius)
        p.fillPath(path, T.bg)
        p.setPen(QPen(T.stroke2 if T.dark else T.stroke, 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
        # rectangular clip (fast): a rounded path would make every text ~8× slower
        p.setClipRect(r.adjusted(2, 2, -2, -2))

        self.hits, self.sliders, self.scroll_regions = [], [], []
        self.draggables = []
        self.field_handlers = {}
        t = time.time() - self.mode_t
        a_new = smooth((t - 0.03) / 0.20)
        a_old = 1 - smooth(t / 0.10)
        new_exp, old_exp = self.mode.startswith("tab:"), self.prev_mode.startswith("tab:")
        both = new_exp and old_exp
        cx = r.center().x()

        # fixed tab bar while switching from one tab to another
        if both:
            self._reg = True
            p.setOpacity(1.0)
            self.paint_tabbar(ui, r)

        # old content: always from a cached pixmap (avoids painting everything twice)
        if a_old > 0 and self.prev_mode != self.mode:
            self._reg = False
            p.setOpacity(a_old)
            p.save()
            if both:
                p.translate(-self.slide_dir * 16 * (1 - a_old), 0)
            if old_exp:
                pm, tw, th = self.content_pixmap(self.prev_mode)
                skip = TAB_H if both else 0
                self._blit_content(p, pm, cx, r.top(), tw, th, skip)
            else:
                self.paint_mode(ui, self.prev_mode, r)
            p.restore()

        # new content: cached while the island resizes, then painted directly
        if a_new > 0:
            p.setOpacity(a_new)
            p.save()
            if both:
                p.translate(self.slide_dir * 16 * (1 - a_new), 0)
            else:
                s = 0.95 + 0.05 * a_new
                p.translate(cx, r.top())
                p.scale(s, s)
                p.translate(-cx, -r.top())
            if new_exp and self.moving:
                self._reg = False
                pm, tw, th = self.content_pixmap(self.mode)
                skip = TAB_H if both else 0
                self._blit_content(p, pm, cx, r.top(), tw, th, skip)
            else:
                self._reg = a_new > 0.6
                if new_exp and not both:
                    self.paint_tabbar(ui, r)
                self.paint_mode(ui, self.mode, r)
            p.restore()
        self._reg = False
        p.end()

    def warmup(self, keys=None):
        keys = list(self.tab_keys) if keys is None else keys
        if not keys:
            return
        key = keys.pop(0)
        if not self.is_open:
            try:
                self.content_pixmap("tab:" + key)
                tab = self.tabs[key]
                for v in TAB_VIEWS.get(key, []):
                    old = tab.view
                    tab.view = v
                    self._cc.pop("tab:" + key, None)
                    self.content_pixmap("tab:" + key)
                    tab.view = old
            except Exception:
                pass
            self._cc.pop("tab:" + key, None)
        else:
            keys.insert(0, key)
        QTimer.singleShot(120, lambda: self.warmup(keys))

    def content_pixmap(self, mode):
        """Render tabs and content to a pixmap cached for about 0.4 s during animations."""
        tab = self.tabs[mode[4:]]
        tw, th = EW, TAB_H + tab.height()
        key = (mode, tw, th, T.dark)
        c = self._cc.get(mode)
        if c and c[0] == key and time.time() - c[2] < 0.4:
            return c[1], tw, th
        dpr = self.devicePixelRatioF()
        pm = QPixmap(int(tw * dpr) + 1, int(th * dpr) + 1)
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)
        q = QPainter(pm)
        q.setRenderHint(QPainter.RenderHint.Antialiasing)
        q.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        q.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        main_p, reg = self.ui.p, self._reg
        self.ui.p, self._reg = q, False
        rr = QRectF(0, 0, tw, th)
        q.setClipRect(rr.adjusted(2, 2, -2, -2))
        self.paint_tabbar(self.ui, rr)
        self.paint_mode(self.ui, mode, rr)
        q.end()
        self.ui.p, self._reg = main_p, reg
        self._cc[mode] = (key, pm, time.time())
        return pm, tw, th

    @staticmethod
    def _blit_content(p, pm, cx, top, tw, th, skip=0):
        """Draw cached content using device-pixel source coordinates.

        QPainter.drawPixmap does not apply QPixmap.devicePixelRatio to its
        source rectangle, so logical units magnify the frame on scaled displays.
        """
        dpr = pm.devicePixelRatio()
        p.drawPixmap(
            QRectF(cx - tw / 2, top + skip, tw, th - skip),
            pm,
            QRectF(0, skip * dpr, tw * dpr, (th - skip) * dpr),
        )

    @property
    def dock_enabled(self):
        return settings.get("dock", True)

    def dock_layout(self):
        """Dock rectangle (right of the pill) and cells [(rect, group | None for “+N”)]]."""
        apps = self.launcher.running
        if not apps or self.dock_alpha <= 0.01 and not (self.dock_enabled and not self.is_open):
            return None, []
        pr = self.pill_rect()
        room = int((WIN_W - 16 - (pr.right() + 8) - 8) // DOCK_CELL)
        shown = apps[:max(1, min(DOCK_MAX, room))]
        extra = len(apps) - len(shown)
        if extra and len(shown) > 1:
            shown = shown[:-1]
            extra += 1
        n = len(shown) + (1 if extra else 0)
        dr = QRectF(pr.right() + 8, PAD, 8 + n * DOCK_CELL, 34)
        cells = [(QRectF(dr.left() + 4 + i * DOCK_CELL, dr.top() + 2, DOCK_CELL, 30), g)
                 for i, g in enumerate(shown + ([None] if extra else []))]
        self._dock_extra = extra
        return dr, cells

    def paint_dock(self, p):
        dr, cells = self.dock_layout()
        if dr is None or self.dock_alpha <= 0.01:
            return
        ui = self.ui
        p.save()
        p.setOpacity(self.dock_alpha)
        # slide slightly out of the pill on appearance
        p.translate(-10 * (1 - self.dock_alpha), 0)
        self.paint_shadow(p, dr, R_COMPACT)
        path = QPainterPath()
        path.addRoundedRect(dr, R_COMPACT, R_COMPACT)
        p.fillPath(path, T.bg)
        p.setPen(QPen(T.stroke2, 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(dr.adjusted(0.5, 0.5, -0.5, -0.5), R_COMPACT, R_COMPACT)
        fg = user32.GetForegroundWindow()
        label = None
        for i, (rr, g) in enumerate(cells):
            c = rr.center()
            hov = i == self.dock_hover
            if hov:
                ui.rect(rr.adjusted(2, 1, -2, -1), T.hover, 6)
            if g is None:
                ui.text(rr, f"+{self._dock_extra}", font(8, W.DemiBold), T.text2, CENTER)
                if hov:
                    label = (c, tr("island.dock.all_apps"))
                continue
            size = 22 if hov else 20
            minimized = all(w["min"] for w in g["windows"])
            if minimized:
                p.setOpacity(self.dock_alpha * 0.5)
            ui.file_icon(QRectF(c.x() - size / 2, c.y() - size / 2 - 1, size, size), g["exe"], chr(0xE71D))
            p.setOpacity(self.dock_alpha)
            active = any(w["hwnd"] == fg for w in g["windows"])
            if active:  # foreground application indicator, like the taskbar
                ui.rect(QRectF(c.x() - 6, rr.bottom() - 2, 12, 2.5), T.accent, 1.25)
            elif len(g["windows"]) > 1:
                ui.rect(QRectF(c.x() - 2, rr.bottom() - 2, 4, 2.5), T.text3, 1.25)
            if hov:
                n = len(g["windows"])
                label = (c, g["name"] + (tr("island.dock.window_count", count=n) if n > 1 else ""))
        if label:
            c, txt = label
            f = font(8, W.Medium)
            w = ui.tw(txt, f) + 18
            lr = QRectF(c.x() - w / 2, dr.bottom() + 6, w, 22)
            if lr.right() > WIN_W - 4:
                lr.moveRight(WIN_W - 4)
            ui.rect(lr, T.bg, 6, T.stroke2)
            ui.text(lr, txt, f, T.text, CENTER)
        p.restore()

    def dock_activate(self, group):
        """Click: show the application or minimize it when already in front (like the taskbar)."""
        fg = user32.GetForegroundWindow()
        hwnds = [window["hwnd"] for window in group["windows"]]
        if fg in hwnds and not user32.IsIconic(fg):
            self.launcher.minimize_window(fg)
        else:
            system.activate_window(hwnds[0])
        QTimer.singleShot(300, self.launcher.refresh_running)

    def dock_menu(self, group):
        """Right click: application windows and actions."""
        launcher = self.launcher
        menu = QMenu()
        menu.setStyleSheet(MENU_QSS)
        memory = tr("units.megabyte", value=f"{group['mem'] / 2 ** 20:.0f}")
        head = menu.addAction(f"{group['name']}  ·  {memory}")
        head.setEnabled(False)
        menu.addSeparator()
        if len(group["windows"]) > 1:
            for window in group["windows"]:
                title = window["title"] if len(window["title"]) < 60 else window["title"][:57] + "…"
                action = menu.addAction(("◦ " if window["min"] else "• ") + title)
                action.triggered.connect(lambda _=False, hwnd=window["hwnd"]: system.activate_window(hwnd))
            menu.addSeparator()
        menu.addAction(tr("island.dock.show")).triggered.connect(
            lambda: system.activate_window(group["windows"][0]["hwnd"])
        )
        menu.addAction(tr("island.dock.minimize")).triggered.connect(
            lambda: [launcher.minimize_window(window["hwnd"]) for window in group["windows"]]
        )
        menu.addAction(tr("island.dock.close")).triggered.connect(lambda: launcher.close_app(group))
        menu.addSeparator()

        def force():
            message = tr("island.dock.force_stop_message", name=group["name"])
            if QMessageBox.question(None, tr("app.name"), message) == QMessageBox.StandardButton.Yes:
                launcher.kill_app(group)
        menu.addAction(tr("island.dock.force_stop")).triggered.connect(force)
        menu.exec(QCursor.pos())
        launcher.refresh_running()

    _shadow_cache = {}

    def paint_shadow(self, p, r, radius):
        """Soft Windows 11 shadow in 9 slices, precomputed (avoids 8 rounded shapes per frame)."""
        m = 9
        key = (int(radius), T.shadow.alpha())
        pm = self._shadow_cache.get(key)
        c = m + int(radius) + 2
        if pm is None:
            size = 2 * c + 2
            pm = QPixmap(size, size)
            pm.fill(Qt.GlobalColor.transparent)
            q = QPainter(pm)
            q.setRenderHint(QPainter.RenderHint.Antialiasing)
            q.setPen(Qt.PenStyle.NoPen)
            inner = QRectF(m, m, size - 2 * m, size - 2 * m)
            for i in range(1, m):
                q.setBrush(QColor(0, 0, 0, int(T.shadow.alpha() * (1 - i / m) ** 2 * 0.5)))
                q.drawRoundedRect(inner.adjusted(-i, -i, i, i), radius + i, radius + i)
            q.end()
            self._shadow_cache[key] = pm
        size = pm.width()
        o = QRectF(r.left() - m, r.top() - m + 2, r.width() + 2 * m, r.height() + 2 * m + 1)
        if o.width() < 2 * c or o.height() < 2 * c:
            return
        mid = size - 2 * c
        L, T_, R, B = o.left(), o.top(), o.right(), o.bottom()
        pieces = [  # (target, source)
            (QRectF(L, T_, c, c), QRectF(0, 0, c, c)),
            (QRectF(R - c, T_, c, c), QRectF(size - c, 0, c, c)),
            (QRectF(L, B - c, c, c), QRectF(0, size - c, c, c)),
            (QRectF(R - c, B - c, c, c), QRectF(size - c, size - c, c, c)),
            (QRectF(L + c, T_, o.width() - 2 * c, c), QRectF(c, 0, mid, c)),
            (QRectF(L + c, B - c, o.width() - 2 * c, c), QRectF(c, size - c, mid, c)),
            (QRectF(L, T_ + c, c, o.height() - 2 * c), QRectF(0, c, c, mid)),
            (QRectF(R - c, T_ + c, c, o.height() - 2 * c), QRectF(size - c, c, c, mid)),
        ]
        for tgt, src in pieces:
            p.drawPixmap(tgt, pm, src)

    def paint_mode(self, ui, mode, r):
        if mode.startswith("tab:"):
            cr = QRectF(r.left(), r.top() + TAB_H, r.width(), max(0, r.height() - TAB_H))
            ui.p.save()
            ui.p.setClipRect(cr, Qt.ClipOperation.IntersectClip)
            self.tabs[mode[4:]].paint(ui, cr)
            ui.p.restore()
        else:
            getattr(self, "paint_" + mode)(ui, r)

    def paint_tabbar(self, ui, r):
        y = r.top()
        bw, bh, gap = 34, 32, 2
        n = len(self.tab_keys)
        x0 = r.right() - 84 - n * (bw + gap)
        hov_label = None
        for i, key in enumerate(self.tab_keys):
            t = self.tabs[key]
            br = QRectF(x0 + i * (bw + gap), y + 7, bw, bh)
            on = key == self.tab
            if ui.hovering(br):
                hov_label = tr(t.label_key)
                if not on:
                    ui.rect(br, T.hover, 4)
            if on:
                ui.rect(br, T.layer2, 4)
            ui.glyph(br.center(), t.glyph, 14, T.text if on else T.text2)
            ui.hit(br, lambda key=key: self.set_tab(key))
        ix = x0 + self.tab_x * (bw + gap) + bw / 2
        ui.rect(QRectF(ix - 8, y + 7 + bh - 3, 16, 3), T.accent, 1.5)
        ui.text(QRectF(r.left() + 18, y + 6, x0 - r.left() - 24, 34),
                hov_label or tr(self.tabs[self.tab].label_key),
                font(10, W.DemiBold, True), T.text)
        ui.text(QRectF(r.right() - 78, y + 6, 44, 34), format_time(dt.datetime.now()),
                font(9, W.DemiBold), T.text, RIGHT)
        if self.battery:
            percent, plugged = self.battery
            color = T.success if plugged else (T.critical if percent <= 20 else T.text2)
            ui.glyph(QPointF(r.right() - 20, y + 23),
                     G["charging"] if plugged else G["battery"], 15, color)
            ui.hit(QRectF(r.right() - 34, y + 8, 28, 30), lambda: self.show_alert(
                "battery", tr("island.battery.title", percent=percent),
                tr("island.battery.charging") if plugged else tr("island.battery.on_battery"),
                color, G["battery"]))
        ui.rect(QRectF(r.left() + 1, y + TAB_H - 1, r.width() - 2, 1), T.stroke, 0)

    def indicators(self, ui, r, x):
        p = ui.p
        p.setPen(Qt.PenStyle.NoPen)
        for busy, col in ((self.cam_busy, T.success), (self.mic_busy, T.orange)):
            if busy:
                p.setBrush(col)
                p.drawEllipse(QPointF(x, r.center().y()), 3.2, 3.2)
                x -= 11
        if self.timers.focus:
            ui.glyph(QPointF(x - 2, r.center().y()), G["moon"], 10, T.accent)
            x -= 16
        return x

    def paint_compact(self, ui, r):
        ui.text(r, format_time(dt.datetime.now()), font(10, W.DemiBold), T.text, CENTER)
        x = self.indicators(ui, r, r.right() - 14)
        if self.battery and self.battery[1] and x == r.right() - 14:
            ui.glyph(QPointF(r.right() - 16, r.center().y()), G["bolt"], 11, T.success)
        if self.caps:
            ui.glyph(QPointF(r.left() + 16, r.center().y()), G["keyboard"], 11, T.success)

    def paint_cmedia(self, ui, r):
        if not self.media:
            return
        self.draw_art(ui.p, QRectF(r.left() + 7, r.top() + 6, 22, 22), 5)
        ui.text(QRectF(r.left() + 36, r.top(), r.width() - 90, r.height()), self.media["title"], font(8.5, W.Medium),
                T.text2)
        self.draw_eq(ui.p, QRectF(r.right() - 30, r.top() + 10, 18, 14), self.accent)
        self.indicators(ui, r, r.right() - 42)

    def paint_ctimer(self, ui, r):
        act = self.timers.active()
        if not act:
            return
        label, rem, frac, kind = act
        col = T.success if kind == "pomo" and self.timers.pomo["phase"] != "work" else T.accent
        c = QPointF(r.left() + 19, r.center().y())
        if frac is not None:
            ui.ring(c, 9, frac, col, 2.5)
        else:
            ui.glyph(c, G["timer"], 12, col)
        ui.text(QRectF(r.left() + 36, r.top(), 110, r.height()), label, font(8.5, W.Medium), T.text2)
        ui.text(QRectF(r.right() - 96, r.top(), 82, r.height()), fmt_dur(rem), font(10.5, W.DemiBold), col, RIGHT)

    def paint_cmeet(self, ui, r):
        o = self.agenda.next_timed()
        if not o:
            return
        now = time.time()
        ui.glyph(QPointF(r.left() + 18, r.center().y()), G["video"] if o.get("meet_url") else G["calendar"], 12, T.accent)
        ui.text(QRectF(r.left() + 34, r.top(), r.width() - 130, r.height()), o["title"], font(8.5, W.Medium), T.text)
        txt = tr("island.event.in_progress") if o["start"] <= now else until(o["start"] - now)
        ui.text(QRectF(r.right() - 100, r.top(), 86, r.height()), txt, font(8.5, W.DemiBold), T.accent, RIGHT)

    def paint_cbuild(self, ui, r):
        b = self.dev.build
        if not b:
            return
        ang = (time.time() * 360) % 360
        p = ui.p
        c = QPointF(r.left() + 19, r.center().y())
        p.setPen(QPen(T.caution, 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(QRectF(c.x() - 8, c.y() - 8, 16, 16), int(-ang * 16), 270 * 16)
        ui.text(QRectF(r.left() + 36, r.top(), r.width() - 90, r.height()),
                tr("island.build.title", project=b.get("project") or ""),
                font(8.5, W.Medium), T.text2)
        ui.text(QRectF(r.right() - 60, r.top(), 46, r.height()),
                tr("island.build.seconds", seconds=int(time.time() - b["start"])),
                font(9, W.DemiBold), T.caution, RIGHT)

    def paint_alert(self, ui, r):
        a = self.alert
        if not a:
            return
        c = QPointF(r.left() + 34, r.center().y())
        if a["kind"] == "media":
            self.draw_art(ui.p, QRectF(c.x() - 20, c.y() - 20, 40, 40), 6)
        else:
            ui.rect(QRectF(c.x() - 20, c.y() - 20, 40, 40), T.tint(a["color"], 45), 6)
            ui.glyph(c, a["glyph"] or G["info"], 17, a["color"])
        tx = r.left() + 66
        right = 96 if a.get("action") else (50 if a["kind"] == "media" else 18)
        tw = r.right() - tx - right
        if a.get("bar") is not None:
            ui.text(QRectF(tx, r.top() + 10, tw, 20), a["title"], font(10, W.DemiBold))
            ui.bar(QRectF(tx, r.top() + 38, tw - 46, 4), a["bar"])
            ui.text(QRectF(r.right() - 66, r.top() + 29, 48, 22), f"{a['bar'] * 100:.0f}", font(9, W.DemiBold),
                    T.text, RIGHT)
            return
        ui.text(QRectF(tx, r.top() + 12, tw, 20), a["title"], font(10, W.DemiBold))
        ui.text(QRectF(tx, r.top() + 32, tw, 18), a["subtitle"], font(8.5), T.text2)
        if a["kind"] == "media":
            self.draw_eq(ui.p, QRectF(r.right() - 40, r.center().y() - 9, 20, 18), self.accent)
        act = a.get("action")
        if act:
            def run(fn=act[1]):
                fn()
                self.alert_until = 0
            ui.button(QRectF(r.right() - 92, r.center().y() - 15, 80, 30), act[0], run, accent=True)

