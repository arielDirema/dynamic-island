"""Island layout dimensions and constants."""

COMPACT = (132, 34)
COMPACT_MEDIA = (260, 34)
COMPACT_TIMER = (236, 34)
COMPACT_MEET = (300, 34)
COMPACT_BUILD = (210, 34)
ALERT = (360, 64)
EW = 620
TAB_H = 46
PAD = 10                 # shadow margin
WIN_W, WIN_H = EW + 420, TAB_H + 380 + 60   # wide enough for the dock right of the pill
TOP_MARGIN = 0
HOVER_DELAY = 0.07
LEAVE_DELAY = 0.30
ALERT_TIME = 2.8
HOTKEY_ID = 1
HOTKEY_LAUNCH = 2
DOCK_MAX = 9          # dock icons shown; beyond this, “+N”
DOCK_CELL = 30
MENU_QSS = ("QMenu{background:#000;color:#fff;border:1px solid #333;padding:4px;border-radius:8px}"
            "QMenu::item{padding:6px 22px 6px 14px;border-radius:4px}"
            "QMenu::item:selected{background:#262626}QMenu::item:disabled{color:#8a8a8a}"
            "QMenu::separator{height:1px;background:#2a2a2a;margin:4px 8px}")
COMPACT_MODES = ("compact", "cmedia", "ctimer", "cmeet", "cbuild")
