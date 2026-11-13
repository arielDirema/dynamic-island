"""Windows 11 (Fluent) painted components: buttons, tiles, sliders,
text fields, scrolling lists and segmented tabs."""
import time

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPen

from dynamic_island.core.localization import translate
from dynamic_island.ui.themes import R_CARD, R_CTRL, T, W, fm, font, ifont

AL = Qt.AlignmentFlag
LEFT = AL.AlignLeft | AL.AlignVCenter
RIGHT = AL.AlignRight | AL.AlignVCenter
CENTER = AL.AlignCenter


_EMOJI = {}
_ELIDE = {}
_QR = {}
_QR_PM = {}
_ICONS = {}
_PROVIDER = None


class UI:
    """Drawing helpers bound to the island (hit regions, focus and scrolling)."""

    def __init__(self, isl):
        self.isl = isl
        self.p = None

    def qr(self, rect, text, quiet=2):
        """QR code with a white background and black modules; the matrix is cached."""
        m = _QR.get(text)
        if m is None:
            import qrcode
            q = qrcode.QRCode(border=0, error_correction=qrcode.constants.ERROR_CORRECT_M)
            q.add_data(text)
            q.make(fit=True)
            m = _QR[text] = q.get_matrix()
        side = min(rect.width(), rect.height())
        x0 = rect.center().x() - side / 2
        y0 = rect.center().y() - side / 2
        key = (text, int(side))
        pm = _QR_PM.get(key)
        if pm is None:  # render once to a pixmap (otherwise hundreds of squares per frame)
            from PySide6.QtGui import QPainter, QPixmap
            from PySide6.QtWidgets import QApplication
            dpr = QApplication.primaryScreen().devicePixelRatio()
            pm = QPixmap(int(side * dpr), int(side * dpr))
            pm.setDevicePixelRatio(dpr)
            pm.fill(Qt.GlobalColor.transparent)
            q = QPainter(pm)
            q.setRenderHint(QPainter.RenderHint.Antialiasing)
            q.setPen(Qt.PenStyle.NoPen)
            q.setBrush(QColor(255, 255, 255))
            q.drawRoundedRect(QRectF(0, 0, side, side), 6, 6)
            q.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            q.setBrush(QColor(0, 0, 0))
            n = len(m)
            cell = side / (n + 2 * quiet)
            for y, row in enumerate(m):
                run_start = None
                for x, v in enumerate(list(row) + [False]):
                    if v and run_start is None:
                        run_start = x
                    elif not v and run_start is not None:
                        q.drawRect(QRectF((quiet + run_start) * cell, (quiet + y) * cell,
                                          (x - run_start) * cell + 0.5, cell + 0.5))
                        run_start = None
            q.end()
            if len(_QR_PM) > 20:
                _QR_PM.clear()
            _QR_PM[key] = pm
        self.p.drawPixmap(QPointF(x0, y0), pm)

    def file_icon(self, rect, path, fallback=None):
        """Windows icon for a file, folder or shortcut (cached)."""
        key = (path, int(rect.width()))
        pm = _ICONS.get(key)
        if pm is None:
            pm = False
            try:
                from PySide6.QtCore import QFileInfo
                from PySide6.QtWidgets import QFileIconProvider
                if path and not path.lower().startswith(("shell:", "http", "ps:", "py:", ">")):
                    global _PROVIDER
                    if _PROVIDER is None:
                        _PROVIDER = QFileIconProvider()
                    ic = _PROVIDER.icon(QFileInfo(path))
                    if not ic.isNull():
                        pm = ic.pixmap(int(rect.width() * 2), int(rect.height() * 2))
                        img = pm.toImage()
                        w_, h_ = img.width(), img.height()
                        vis = sum(1 for yy in range(0, h_, 3) for xx in range(0, w_, 3)
                                  if img.pixelColor(xx, yy).alpha() > 40)
                        if vis < (w_ // 3) * (h_ // 3) * 0.06:   # blank/transparent icon → fallback
                            pm = False
                        else:  # pre-scaled to the exact display size
                            from PySide6.QtWidgets import QApplication
                            dpr = QApplication.primaryScreen().devicePixelRatio()
                            pm = pm.scaled(int(rect.width() * dpr), int(rect.height() * dpr),
                                           Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                            pm.setDevicePixelRatio(dpr)
            except Exception:
                pm = False
            _ICONS[key] = pm
        if pm:
            self.p.drawPixmap(QPointF(rect.left(), rect.top()), pm)
        else:
            self.rect(rect, T.layer2, 4)
            self.glyph(rect.center(), fallback or "", rect.height() * 0.5, T.text2)

    def drag_row(self, rect, paths, click):
        """Row that can be dragged to another application or clicked."""
        cr = self.isl.clip_rect
        r = rect.intersected(cr) if cr is not None else rect
        if self.isl._reg and r.height() > 2:
            self.isl.draggables.append((QRectF(r), list(paths), click))

    def hit(self, rect, fn):
        if self.isl._reg:
            self.isl.hits.append((QRectF(rect), fn))

    def hovering(self, rect):
        return self.isl._reg and rect.contains(self.isl.mouse)

    def text(self, rect, s, f, color=None, align=LEFT, elide=True):
        p = self.p
        p.setFont(f)
        p.setPen(color or T.text)
        s = str(s)
        if elide:
            key = (s, f.key(), int(max(0, rect.width())))
            e = _ELIDE.get(key)
            if e is None:
                if len(_ELIDE) > 4000:
                    _ELIDE.clear()
                e = _ELIDE[key] = fm(f).elidedText(s, Qt.TextElideMode.ElideRight, key[2])
            s = e
        p.drawText(rect, int(align), s)

    def wrap(self, rect, s, f, color=None, lines=2):
        """Multi-line text, cleanly elided."""
        p = self.p
        p.setFont(f)
        p.setPen(color or T.text)
        m = fm(f)
        words, out, cur = str(s).split(), [], ""
        for w in words:
            t = (cur + " " + w).strip()
            if m.horizontalAdvance(t) <= rect.width():
                cur = t
            else:
                out.append(cur)
                cur = w
                if len(out) == lines:
                    break
        if len(out) < lines and cur:
            out.append(cur)
        out = out[:lines]
        if len(out) == lines and len(" ".join(out)) < len(" ".join(words)):
            out[-1] = m.elidedText(out[-1] + " …", Qt.TextElideMode.ElideRight, int(rect.width()))
        lh = m.height() + 1
        for i, line in enumerate(out):
            p.drawText(QRectF(rect.left(), rect.top() + i * lh, rect.width(), lh), int(LEFT), line)
        return len(out) * lh

    def emoji(self, rect, s, px):
        """Cached color emoji (direct color-font rendering is slow)."""
        key = (s, int(px))
        pm = _EMOJI.get(key)
        if pm is None:
            from PySide6.QtGui import QPixmap, QPainter, QFont
            size = int(px * 1.6)
            pm = QPixmap(size * 2, size * 2)
            pm.setDevicePixelRatio(2)
            pm.fill(Qt.GlobalColor.transparent)
            q = QPainter(pm)
            f = QFont("Segoe UI Emoji")
            f.setPixelSize(int(px))
            q.setFont(f)
            q.drawText(QRectF(0, 0, size, size), int(CENTER), s)
            q.end()
            _EMOJI[key] = pm
        w = pm.width() / 2
        self.p.drawPixmap(QPointF(rect.center().x() - w / 2, rect.center().y() - w / 2), pm)

    def tw(self, s, f):
        return fm(f).horizontalAdvance(str(s))

    def glyph(self, c, g, px, color=None, slash=False):
        p = self.p
        p.setFont(ifont(px))
        p.setPen(color or T.text)
        p.drawText(QRectF(c.x() - px, c.y() - px, px * 2, px * 2), int(CENTER), g)
        if slash:
            p.setPen(QPen(color or T.text, max(1.4, px / 10), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            d = px * 0.55
            p.drawLine(QPointF(c.x() - d, c.y() - d), QPointF(c.x() + d, c.y() + d))

    def rect(self, r, fill, radius=R_CTRL, stroke=None):
        p = self.p
        p.setPen(QPen(stroke, 1) if stroke else Qt.PenStyle.NoPen)
        p.setBrush(fill if fill else Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5) if stroke else r, radius, radius)

    def card(self, r, radius=R_CARD):
        self.rect(r, T.layer, radius, T.stroke)

    def section(self, x, y, w, label, right=None, right_fn=None):
        self.text(QRectF(x, y, w, 18), label, font(8.5, W.DemiBold), T.text)
        if right:
            f = font(8, W.Medium)
            rw = self.tw(right, f) + 4
            rr = QRectF(x + w - rw, y, rw, 18)
            self.text(rr, right, f, T.accent if self.hovering(rr) else T.text3, RIGHT)
            if right_fn:
                self.hit(rr, right_fn)

    def button(self, r, label=None, fn=None, glyph=None, accent=False, danger=False, enabled=True, sel=False):
        hov = enabled and self.hovering(r)
        if accent and enabled:
            fill = QColor(T.accent).lighter(108) if hov else T.accent
            self.rect(r, fill, R_CTRL)
            col = T.on_accent
        else:
            fill = T.layer2 if (hov or sel) else T.layer
            self.rect(r, fill, R_CTRL, T.stroke)
            col = T.critical if danger else (T.text if enabled else T.disabled)
        f = font(8.5, W.Medium)
        if glyph and label:
            w = 16 + 6 + self.tw(label, f)
            x = r.center().x() - w / 2
            self.glyph(QPointF(x + 8, r.center().y()), glyph, 12, col)
            self.text(QRectF(x + 22, r.top(), w - 20, r.height()), label, f, col)
        elif glyph:
            self.glyph(r.center(), glyph, 12, col)
        elif label:
            self.text(r, label, f, col, CENTER)
        if enabled and fn:
            self.hit(r, fn)

    def icon_button(self, c, g, fn, px=13, color=None, size=28, active=False):
        r = QRectF(c.x() - size / 2, c.y() - size / 2, size, size)
        if self.hovering(r) or active:
            self.rect(r, T.hover if not active else T.layer2, R_CTRL)
        self.glyph(c, g, px, color or T.text2)
        self.hit(r, fn)
        return r

    def link(self, r, label, fn, f=None):
        f = f or font(8.5, W.Medium)
        col = QColor(T.accent).lighter(115) if self.hovering(r) else T.accent
        self.text(r, label, f, col)
        self.hit(r, fn)

    def checkbox(self, c, checked, fn, color=None, round_=False, size=16):
        r = QRectF(c.x() - size / 2, c.y() - size / 2, size, size)
        hit = r.adjusted(-5, -5, 5, 5)
        hov = self.hovering(hit)
        rad = size / 2 if round_ else R_CTRL
        if checked:
            self.rect(r, color or T.accent, rad)
            self.glyph(c, "", size * 0.62, T.on_accent)
        else:
            self.rect(r, T.hover if hov else Qt.GlobalColor.transparent, rad, color or T.track)
        self.hit(hit, fn)

    def tile(self, r, g, label, active, fn, slash=False, enabled=True, color=None, more=None):
        """Windows 11 quick-settings tile. With “more”, the right chevron area opens a detailed
        panel (network selection, device list…), as in Windows."""
        hov = enabled and self.hovering(r)
        br = QRectF(r.left(), r.top(), r.width(), r.height() - 18)
        mr = QRectF(br.right() - 26, br.top(), 26, br.height()) if more else None
        if active and enabled:
            c = QColor(color or T.accent)
            self.rect(br, c.lighter(108) if hov else c, R_CTRL)
            ic = T.on_accent
        else:
            self.rect(br, T.layer2 if hov else T.layer, R_CTRL, T.stroke)
            ic = T.text if enabled else T.disabled
        if mr is not None:
            if self.hovering(mr):
                self.rect(mr.adjusted(1, 1, -1, -1), QColor(255, 255, 255, 40) if active else T.hover, R_CTRL)
            self.rect(QRectF(mr.left(), mr.top() + 8, 1, mr.height() - 16), T.tint(ic, 70), 0)
            self.glyph(mr.center(), "", 10, ic)
            gc = QPointF(br.left() + (br.width() - 26) / 2, br.center().y())
        else:
            gc = br.center()
        self.glyph(gc, g, 15, ic, slash)
        self.text(QRectF(r.left() - 6, r.bottom() - 16, r.width() + 12, 16), label, font(7.5),
                  T.text if enabled else T.disabled, CENTER)
        if enabled:
            self.hit(r, fn)
        if mr is not None:
            self.hit(mr, more)  # registered last: takes priority over the toggle

    def slider(self, r, value, setter, color=None, enabled=True):
        """Fluent slider: thin track and round thumb with an accent dot."""
        p = self.p
        value = max(0.0, min(1.0, value))
        cy = r.center().y()
        tr = QRectF(r.left(), cy - 2, r.width(), 4)
        self.rect(tr, T.track if enabled else T.disabled, 2)
        if value > 0:
            self.rect(QRectF(tr.left(), tr.top(), tr.width() * value, 4), (color or T.accent) if enabled else T.disabled, 2)
        tx = r.left() + r.width() * value
        hov = enabled and self.hovering(r.adjusted(-8, -10, 8, 10))
        dragging = self.isl.drag is not None and self.isl.drag[1] is setter
        p.setPen(QPen(T.stroke2, 1))
        p.setBrush(QColor(69, 69, 69) if T.dark else QColor(255, 255, 255))
        p.drawEllipse(QPointF(tx, cy), 9.5, 9.5)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush((color or T.accent) if enabled else T.disabled)
        inner = 4.0 if dragging else (6.0 if hov else 5.0)
        p.drawEllipse(QPointF(tx, cy), inner, inner)
        if enabled and self.isl._reg:
            self.isl.sliders.append((r.adjusted(-8, -10, 8, 10), setter, value, r))

    def bar(self, r, frac, color=None, bg=None):
        rad = r.height() / 2
        self.rect(r, bg or T.layer2, rad)
        if frac > 0:
            self.rect(QRectF(r.left(), r.top(), max(r.height(), r.width() * min(1.0, frac)), r.height()),
                      color or T.accent, rad)

    def ring(self, c, radius, frac, color=None, width=3.0, bg=None):
        p = self.p
        rr = QRectF(c.x() - radius, c.y() - radius, radius * 2, radius * 2)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(bg or T.layer2, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawEllipse(rr)
        if frac > 0:
            p.setPen(QPen(color or T.accent, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawArc(rr, 90 * 16, -int(360 * 16 * min(1.0, frac)))

    def segmented(self, r, options, current, fn, translate_labels=True):
        """Windows 11 segmented selector with an accent indicator under the active item."""
        f = font(8.5, W.Medium)
        fa = font(8.5, W.DemiBold)
        x = r.left()
        for key, label_key in options:
            label = translate(label_key) if translate_labels else label_key
            w = self.tw(label, fa) + 22
            rr = QRectF(x, r.top(), w, r.height())
            on = key == current
            if self.hovering(rr) and not on:
                self.rect(rr, T.hover, R_CTRL)
            self.text(rr, label, fa if on else f, T.text if on else T.text2, CENTER)
            if on:
                self.rect(QRectF(rr.center().x() - 8, rr.bottom() - 3, 16, 3), T.accent, 1.5)
            self.hit(rr, lambda k=key: fn(k))
            x += w + 2
        return x

    def chip(self, r, label, on, fn, glyph=None):
        hov = self.hovering(r)
        if on:
            self.rect(r, T.accent, R_CTRL)
            col = T.on_accent
        else:
            self.rect(r, T.layer2 if hov else T.layer, R_CTRL, T.stroke)
            col = T.text2
        f = font(7.5, W.DemiBold)
        if glyph:
            self.glyph(QPointF(r.left() + 11, r.center().y()), glyph, 10, col)
            self.text(r.adjusted(20, 0, 0, 0), label, f, col)
        else:
            self.text(r, label, f, col, CENTER)
        self.hit(r, fn)

    def chip_w(self, label, glyph=None):
        return self.tw(label, font(7.5, W.DemiBold)) + (30 if glyph else 18)

    def badge(self, x, y, label, color):
        f = font(7, W.DemiBold)
        w = self.tw(label, f) + 10
        r = QRectF(x, y, w, 16)
        self.rect(r, T.tint(color, 50), 3)
        self.text(r, label, f, color, CENTER)
        return w

    def field(self, r, name, placeholder="", on_submit=None, glyph=None, on_change=None, secret=False):
        isl = self.isl
        focused = isl.focus_field == name
        hov = self.hovering(r)
        self.rect(r, (T.layer2 if hov else T.layer) if not focused else (QColor(30, 30, 30) if T.dark else QColor(255, 255, 255)),
                  R_CTRL, T.stroke)
        if focused:
            self.rect(QRectF(r.left() + 1, r.bottom() - 2, r.width() - 2, 2), T.accent, 1)
        else:
            self.rect(QRectF(r.left() + 1, r.bottom() - 1, r.width() - 2, 1), T.stroke2, 0)
        x = r.left() + 10
        if glyph:
            self.glyph(QPointF(r.left() + 16, r.center().y()), glyph, 11, T.text3)
            x = r.left() + 30
        f = font(9)
        val = isl.fields.get(name, "")
        shown = ("•" * len(val)) if secret else val
        tr = QRectF(x, r.top(), r.right() - x - 8, r.height())
        if shown:
            m = fm(f)
            if m.horizontalAdvance(shown) > tr.width():  # keep the end visible while editing
                while shown and m.horizontalAdvance("…" + shown) > tr.width():
                    shown = shown[1:]
                shown = "…" + shown
            self.text(tr, shown, f, T.text, elide=False)
        else:
            self.text(tr, placeholder, f, T.text3)
        if focused and int(time.time() * 2) % 2 == 0:
            cx = tr.left() + min(tr.width(), fm(f).horizontalAdvance(shown)) + 1
            self.p.setPen(QPen(T.text, 1.2))
            self.p.drawLine(QPointF(cx, r.top() + 8), QPointF(cx, r.bottom() - 8))
        isl.field_handlers[name] = (on_submit, on_change)
        self.hit(r, lambda: isl.focus(name))

    def scroll(self, key, r, draw):
        """Scroll area: draw(y) paints content from y and returns its height."""
        isl = self.isl
        content_h = isl.scroll_content.get(key, 0)
        cur, tgt = isl.scrolls.get(key, (0.0, 0.0))
        mx = max(0.0, content_h - r.height())
        if tgt > mx:
            tgt = mx
            cur = min(cur, mx)
        isl.scrolls[key] = (cur, tgt)
        if isl._reg:
            isl.scroll_regions.append((QRectF(r), key, mx))
        p = self.p
        p.save()
        p.setClipRect(r, Qt.ClipOperation.IntersectClip)
        saved = isl.clip_rect
        isl.clip_rect = r
        h = draw(r.top() - cur) or 0
        isl.clip_rect = saved
        p.restore()
        isl.scroll_content[key] = h
        if mx > 0:
            hh = max(20, r.height() * r.height() / content_h)
            y = r.top() + (r.height() - hh) * (cur / mx)
            self.rect(QRectF(r.right() - 3, y, 3, hh), T.track if self.hovering(r) else T.stroke2, 1.5)

    def toggle(self, c, on, fn):
        """Windows 11 toggle switch (40 × 20)."""
        r = QRectF(c.x() - 20, c.y() - 10, 40, 20)
        hov = self.hovering(r.adjusted(-4, -4, 4, 4))
        if on:
            self.rect(r, QColor(T.accent).lighter(108) if hov else T.accent, 10)
            kc, kx = T.on_accent, r.right() - 10
        else:
            self.rect(r, T.hover if hov else Qt.GlobalColor.transparent, 10, T.track)
            kc, kx = T.text2, r.left() + 10
        p = self.p
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(kc)
        rad = 6 if hov else 5
        p.drawEllipse(QPointF(kx, c.y()), rad, rad)
        self.hit(r.adjusted(-4, -4, 4, 4), fn)

    def visible(self, rect):
        cr = self.isl.clip_rect
        return cr is None or rect.intersects(cr)

    def row_hit(self, rect, fn):
        cr = self.isl.clip_rect
        r = rect.intersected(cr) if cr is not None else rect
        if r.height() > 2:
            self.hit(r, fn)
        return r

    def row_hover(self, rect):
        cr = self.isl.clip_rect
        r = rect.intersected(cr) if cr is not None else rect
        return r.height() > 2 and self.hovering(r)

    def empty(self, r, g, msg, sub=None):
        c = QPointF(r.center().x(), r.center().y() - 16)
        self.glyph(c, g, 26, T.text3)
        self.text(QRectF(r.left(), c.y() + 18, r.width(), 20), msg, font(9.5, W.DemiBold), T.text2, CENTER)
        if sub:
            self.text(QRectF(r.left() + 20, c.y() + 38, r.width() - 40, 18), sub, font(8), T.text3, CENTER)
