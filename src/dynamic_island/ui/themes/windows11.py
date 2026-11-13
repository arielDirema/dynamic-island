"""Windows 11 theme: light/dark, accent color, fonts and Fluent icons."""
import time
import winreg
from functools import lru_cache

from PySide6.QtGui import QColor, QFont, QFontMetrics

FONT = "Segoe UI Variable Text"
FONT_DISPLAY = "Segoe UI Variable Display"
ICON_FONT = "Segoe Fluent Icons"

# Windows 11 corner radii (less rounded than the iPhone)
R_COMPACT = 9
R_OPEN = 10
R_CTRL = 4
R_CARD = 6

G = {  # Segoe Fluent Icons
    "wifi": "", "bt": "", "plane": "", "sun": "", "moon": "",
    "night": "", "vol": "", "mute": "", "mic": "", "cam": "",
    "lock": "", "power": "", "clip": "", "copy": "", "pin": "",
    "pinned": "", "delete": "", "search": "", "link": "",
    "image": "", "doc": "", "mail": "", "phone": "", "folder": "",
    "music": "", "speaker": "", "headphone": "", "battery": "",
    "charging": "", "keyboard": "", "controls": "", "home": "",
    "check": "", "bolt": "", "calendar": "", "timer": "", "tasks": "",
    "info": "", "code": "", "add": "", "close": "", "edit": "",
    "play": "", "pause": "", "stop": "", "refresh": "", "flag": "",
    "alarm": "", "clock": "", "note": "", "globe": "", "chart": "",
    "news": "", "quote": "", "photo": "", "settings": "", "up": "",
    "down": "", "left": "", "right": "", "gift": "", "video": "",
    "branch": "", "terminal": "", "server": "", "build": "", "bug": "",
    "star": "", "star_on": "", "open": "", "people": "", "focus": "",
    "lap": "", "history": "", "warning": "", "error": "", "rocket": "",
    "cloud": "", "list": "", "project": "", "github": "", "bell": "",
}


def _dword(path, name, default=None):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as k:
            return winreg.QueryValueEx(k, name)[0]
    except OSError:
        return default


class Theme:
    def __init__(self):
        self._sig = None
        self._checked = 0
        self.reload()

    def _read(self):
        light = _dword(r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize", "AppsUseLightTheme", 0)
        pal = _dword(r"Software\Microsoft\Windows\CurrentVersion\Explorer\Accent", "AccentPalette", None)
        return bool(light), bytes(pal) if pal else None

    def check(self):
        """Re-read the Windows theme (at most every 3 s). Return True when it changed."""
        if time.time() - self._checked < 3:
            return False
        self._checked = time.time()
        if self._read() != self._sig:
            self.reload()
            return True
        return False

    def reload(self):
        light, pal = self._read()
        self._sig = (light, pal)
        self.dark = True  # the island stays black (user preference) regardless of the Windows theme
        # palette : Light3, Light2, Light1, Base, Dark1, Dark2, Dark3
        accents = []
        if pal and len(pal) >= 28:
            for i in range(7):
                r, g, b = pal[i * 4], pal[i * 4 + 1], pal[i * 4 + 2]
                accents.append(QColor(r, g, b))
        if not accents:
            accents = [QColor(153, 235, 255), QColor(118, 185, 237), QColor(76, 194, 255), QColor(0, 120, 212),
                       QColor(0, 95, 184), QColor(0, 72, 158), QColor(0, 51, 120)]
        if self.dark:
            self.bg = QColor(0, 0, 0)
            self.layer = QColor(255, 255, 255, 17)
            self.layer2 = QColor(255, 255, 255, 27)
            self.hover = QColor(255, 255, 255, 18)
            self.press = QColor(255, 255, 255, 10)
            self.stroke = QColor(255, 255, 255, 22)
            self.stroke2 = QColor(255, 255, 255, 40)
            self.text = QColor(255, 255, 255)
            self.text2 = QColor(255, 255, 255, 200)
            self.text3 = QColor(255, 255, 255, 139)
            self.disabled = QColor(255, 255, 255, 93)
            self.track = QColor(255, 255, 255, 139)
            self.accent = accents[1]
            self.on_accent = QColor(0, 0, 0)
            self.success = QColor(108, 203, 95)
            self.caution = QColor(252, 225, 0)
            self.critical = QColor(255, 153, 164)
            self.orange = QColor(255, 159, 10)
            self.purple = QColor(180, 160, 255)
            self.shadow = QColor(0, 0, 0, 90)
        else:
            self.bg = QColor(243, 243, 243)
            self.layer = QColor(255, 255, 255, 179)
            self.layer2 = QColor(255, 255, 255, 230)
            self.hover = QColor(0, 0, 0, 10)
            self.press = QColor(0, 0, 0, 6)
            self.stroke = QColor(0, 0, 0, 18)
            self.stroke2 = QColor(0, 0, 0, 40)
            self.text = QColor(0, 0, 0, 228)
            self.text2 = QColor(0, 0, 0, 158)
            self.text3 = QColor(0, 0, 0, 114)
            self.disabled = QColor(0, 0, 0, 92)
            self.track = QColor(0, 0, 0, 114)
            self.accent = accents[4]
            self.on_accent = QColor(255, 255, 255)
            self.success = QColor(15, 123, 15)
            self.caution = QColor(157, 93, 0)
            self.critical = QColor(196, 43, 28)
            self.orange = QColor(202, 80, 16)
            self.purple = QColor(100, 70, 200)
            self.shadow = QColor(0, 0, 0, 40)

    def tint(self, c, alpha):
        q = QColor(c)
        q.setAlpha(alpha)
        return q


T = Theme()


@lru_cache(maxsize=128)
def font(size, weight=QFont.Weight.Normal, display=False):
    f = QFont(FONT_DISPLAY if display else FONT)
    f.setPointSizeF(size)
    f.setWeight(weight)
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return f


@lru_cache(maxsize=32)
def ifont(px):
    f = QFont(ICON_FONT)
    f.setPixelSize(max(1, int(px)))
    return f


@lru_cache(maxsize=256)
def fm(f):
    return QFontMetrics(f)


W = QFont.Weight
