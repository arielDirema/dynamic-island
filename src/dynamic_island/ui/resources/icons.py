"""Color vector icons (weather, birthday cake) painted with QPainter
and cached — they replace emoji."""
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import QApplication

_CACHE = {}

SUN_A, SUN_B = QColor(255, 216, 50), QColor(255, 160, 0)
MOON = QColor(236, 228, 190)
CLOUD_L = (QColor(252, 253, 255), QColor(200, 208, 222))
CLOUD_D = (QColor(176, 186, 204), QColor(112, 122, 142))
RAIN = QColor(80, 170, 255)
SNOW = QColor(235, 245, 255)
BOLT = QColor(255, 204, 0)
FOG = QColor(190, 196, 208)


def weather_kind(code):
    if code == 0:
        return "clear"
    if code == 1:
        return "mostly"
    if code == 2:
        return "partly"
    if code == 3:
        return "cloudy"
    if code in (45, 48):
        return "fog"
    if code in (51, 53, 55):
        return "drizzle"
    if code in (56, 57, 66, 67):
        return "freezing"
    if code in (61, 63):
        return "rain"
    if code in (65, 82):
        return "heavy"
    if code in (80, 81):
        return "showers"
    if code in (71, 73, 75, 77, 85, 86):
        return "snow"
    if code in (95, 96, 99):
        return "thunder"
    return "cloudy"


def _sun(p, cx, cy, r, rays=True):
    if rays:
        p.setPen(QPen(SUN_B, r * 0.16, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        for i in range(8):
            a = i * math.pi / 4
            p.drawLine(QPointF(cx + math.cos(a) * r * 1.35, cy + math.sin(a) * r * 1.35),
                       QPointF(cx + math.cos(a) * r * 1.7, cy + math.sin(a) * r * 1.7))
    g = QRadialGradient(QPointF(cx - r * 0.3, cy - r * 0.3), r * 1.4)
    g.setColorAt(0, SUN_A)
    g.setColorAt(1, SUN_B)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(g)
    p.drawEllipse(QPointF(cx, cy), r, r)


def _moon(p, cx, cy, r):
    a = QPainterPath()
    a.addEllipse(QPointF(cx, cy), r, r)
    b = QPainterPath()
    b.addEllipse(QPointF(cx + r * 0.55, cy - r * 0.35), r * 0.9, r * 0.9)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(MOON)
    p.drawPath(a.subtracted(b))


def _cloud(p, x, y, s, dark=False):
    """Cloud whose top-left corner is (x, y), width 70·s."""
    path = QPainterPath()
    path.addRoundedRect(QRectF(x, y + 22 * s, 70 * s, 26 * s), 13 * s, 13 * s)
    for cx, cy, r in ((22, 24, 15), (42, 16, 19), (56, 28, 13)):
        e = QPainterPath()
        e.addEllipse(QPointF(x + cx * s, y + cy * s), r * s, r * s)
        path = path.united(e)
    top, bot = CLOUD_D if dark else CLOUD_L
    g = QLinearGradient(QPointF(0, y), QPointF(0, y + 48 * s))
    g.setColorAt(0, top)
    g.setColorAt(1, bot)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(g)
    p.drawPath(path)


def _drops(p, xs, y, length, color=RAIN, width=5):
    p.setPen(QPen(color, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    for x in xs:
        p.drawLine(QPointF(x, y), QPointF(x - length * 0.35, y + length))


def _flakes(p, pts, r=3.6):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(SNOW)
    for x, y in pts:
        p.drawEllipse(QPointF(x, y), r, r)


def _bolt(p, x, y, s=1.0):
    path = QPainterPath()
    pts = [(10, 0), (0, 20), (9, 20), (3, 36), (20, 13), (11, 13), (17, 0)]
    path.moveTo(x + pts[0][0] * s, y + pts[0][1] * s)
    for px, py in pts[1:]:
        path.lineTo(x + px * s, y + py * s)
    path.closeSubpath()
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(BOLT)
    p.drawPath(path)


def _paint_weather(p, kind, day):
    sky = (lambda: _sun(p, 50, 50, 22)) if day else (lambda: _moon(p, 50, 50, 26))
    small_sky = (lambda: _sun(p, 64, 32, 15)) if day else (lambda: _moon(p, 64, 32, 16))
    if kind == "clear":
        sky()
    elif kind == "mostly":
        if day:
            _sun(p, 44, 42, 20)
        else:
            _moon(p, 44, 42, 22)
        _cloud(p, 40, 50, 0.72)
    elif kind == "partly":
        small_sky()
        _cloud(p, 12, 34, 0.95)
    elif kind == "cloudy":
        _cloud(p, 26, 18, 0.85, dark=True)
        _cloud(p, 10, 36, 0.95)
    elif kind == "fog":
        _cloud(p, 15, 14, 0.95)
        p.setPen(QPen(FOG, 6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        for i, (a, b) in enumerate(((18, 70), (28, 84), (14, 62))):
            p.drawLine(QPointF(a, 70 + i * 11), QPointF(b, 70 + i * 11))
    elif kind in ("drizzle", "rain", "heavy", "showers", "freezing"):
        if kind == "showers":
            small_sky()
        _cloud(p, 14, 14 if kind != "showers" else 24, 0.95, dark=kind in ("rain", "heavy"))
        base = 66 if kind != "showers" else 74
        if kind == "drizzle":
            _drops(p, (32, 50, 68), base + 2, 9, width=4.5)
        elif kind == "heavy":
            _drops(p, (28, 42, 56, 70), base, 20)
        elif kind == "freezing":
            _drops(p, (34, 62), base, 16)
            _flakes(p, ((48, base + 10),))
        else:
            _drops(p, (34, 50, 66), base, 16)
    elif kind == "snow":
        _cloud(p, 14, 14, 0.95)
        _flakes(p, ((30, 72), (50, 76), (70, 72), (40, 88), (60, 88)))
    elif kind == "thunder":
        _cloud(p, 14, 12, 0.95, dark=True)
        _bolt(p, 40, 58, 1.0)
        _drops(p, (28, 74), 66, 14)


def _pixmap(key, size, painter_fn):
    dpr = QApplication.primaryScreen().devicePixelRatio() if QApplication.instance() else 1.0
    k = (key, int(size), dpr)
    pm = _CACHE.get(k)
    if pm is None:
        pm = QPixmap(int(size * dpr), int(size * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)
        q = QPainter(pm)
        q.setRenderHint(QPainter.RenderHint.Antialiasing)
        q.scale(size / 100, size / 100)
        painter_fn(q)
        q.end()
        _CACHE[k] = pm
    return pm


def weather(p, rect, code, day=True):
    """Paint the weather icon for a WMO code, centered in rect."""
    size = min(rect.width(), rect.height())
    kind = weather_kind(code)
    pm = _pixmap(("w", kind, day), size, lambda q: _paint_weather(q, kind, day))
    p.drawPixmap(QPointF(rect.center().x() - size / 2, rect.center().y() - size / 2), pm)


def _paint_cake(q):
    q.setPen(Qt.PenStyle.NoPen)
    q.setBrush(QColor(255, 140, 170))
    q.drawRoundedRect(QRectF(14, 52, 72, 36), 8, 8)
    q.setBrush(QColor(255, 236, 214))
    path = QPainterPath()
    path.addRoundedRect(QRectF(14, 46, 72, 16), 8, 8)
    for x in (24, 42, 60, 76):
        e = QPainterPath()
        e.addEllipse(QPointF(x, 62), 6, 6)
        path = path.united(e)
    q.drawPath(path)
    q.setBrush(QColor(120, 190, 255))
    q.drawRoundedRect(QRectF(46, 24, 8, 24), 3, 3)
    g = QRadialGradient(QPointF(50, 16), 10)
    g.setColorAt(0, QColor(255, 236, 120))
    g.setColorAt(1, QColor(255, 140, 0))
    q.setBrush(g)
    q.drawEllipse(QPointF(50, 15), 6, 9)


def cake(p, rect):
    size = min(rect.width(), rect.height())
    pm = _pixmap(("cake",), size, _paint_cake)
    p.drawPixmap(QPointF(rect.center().x() - size / 2, rect.center().y() - size / 2), pm)
