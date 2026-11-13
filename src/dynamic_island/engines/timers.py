"""Multiple timers, stopwatch, Pomodoro with breaks, alarms,
work-session history, statistics and focus mode."""
import datetime as dt
import os
import time
import uuid
import winsound

from PySide6.QtCore import QObject, Signal

from dynamic_island.core.config.settings import settings
from dynamic_island.core.localization import translate as tr
from dynamic_island.infrastructure.storage.collection import Collection

SOUND_TIMER = r"C:\Windows\Media\Alarm01.wav"
SOUND_ALARM = r"C:\Windows\Media\Alarm03.wav"
SOUND_SOFT = r"C:\Windows\Media\Windows Notify Calendar.wav"


def play(path):
    try:
        if os.path.exists(path):
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
        else:
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
    except Exception:
        pass


class Timers(QObject):
    fired = Signal(str, str, str)   # kind, title, subtitle
    focus_changed = Signal(bool)

    def __init__(self):
        super().__init__()
        self.timers = []       # countdowns
        self.stopwatch = {"running": False, "start": 0.0, "acc": 0.0, "laps": []}
        cfg = settings.get("pomodoro", {})
        self.pomo_cfg = {"work": cfg.get("work", 25), "short": cfg.get("short", 5),
                         "long": cfg.get("long", 15), "every": cfg.get("every", 4),
                         "auto": cfg.get("auto", True)}
        self.pomo = {"phase": "work", "running": False, "end": 0.0, "remaining": self.pomo_cfg["work"] * 60,
                     "cycles": 0, "label": "", "started": None}
        self.focus = False
        self.alarms = Collection("alarms")
        self.sessions = Collection("sessions")
        self._alarm_fired = set()

    def add_timer(self, seconds, label=None):
        t = {"id": uuid.uuid4().hex, "label": label or self._label(seconds), "duration": seconds,
             "end": time.time() + seconds, "remaining": seconds, "running": True, "started": time.time()}
        self.timers.append(t)
        return t

    @staticmethod
    def _label(seconds):
        if seconds % 3600 == 0:
            return tr("units.hours", count=seconds // 3600)
        if seconds >= 3600:
            return tr("units.hours_minutes", hours=seconds // 3600, minutes=seconds % 3600 // 60)
        if seconds % 60 == 0:
            return tr("units.minutes", count=seconds // 60)
        if seconds >= 60:
            return tr("units.minutes_seconds", minutes=seconds // 60, seconds=seconds % 60)
        return tr("units.seconds", count=seconds)

    def remaining(self, t):
        return max(0.0, t["end"] - time.time()) if t["running"] else t["remaining"]

    def toggle_timer(self, t):
        if t["running"]:
            t["remaining"] = self.remaining(t)
            t["running"] = False
        else:
            if t["remaining"] <= 0:
                t["remaining"] = t["duration"]
            t["end"] = time.time() + t["remaining"]
            t["running"] = True

    def reset_timer(self, t):
        t["running"] = False
        t["remaining"] = t["duration"]

    def remove_timer(self, t):
        if t in self.timers:
            self.timers.remove(t)

    def add_time(self, t, seconds):
        if t["running"]:
            t["end"] += seconds
        else:
            t["remaining"] += seconds
        t["duration"] += seconds

    def sw_elapsed(self):
        s = self.stopwatch
        return s["acc"] + (time.time() - s["start"] if s["running"] else 0)

    def sw_toggle(self):
        s = self.stopwatch
        if s["running"]:
            s["acc"] = self.sw_elapsed()
            s["running"] = False
        else:
            s["start"] = time.time()
            s["running"] = True

    def sw_lap(self):
        if self.stopwatch["running"]:
            self.stopwatch["laps"].insert(0, self.sw_elapsed())

    def sw_reset(self):
        self.stopwatch = {"running": False, "start": 0.0, "acc": 0.0, "laps": []}

    def phase_len(self, phase=None):
        return self.pomo_cfg[phase or self.pomo["phase"]] * 60

    def pomo_remaining(self):
        p = self.pomo
        return max(0.0, p["end"] - time.time()) if p["running"] else p["remaining"]

    def pomo_toggle(self):
        p = self.pomo
        if p["running"]:
            p["remaining"] = self.pomo_remaining()
            p["running"] = False
        else:
            p["end"] = time.time() + p["remaining"]
            p["running"] = True
            if p["phase"] == "work" and p["started"] is None:
                p["started"] = time.time()

    def pomo_skip(self):
        self._pomo_next(log=False)

    def pomo_reset(self):
        self.pomo.update(phase="work", running=False, remaining=self.phase_len("work"), cycles=0, started=None)

    def set_pomo_cfg(self, **kw):
        self.pomo_cfg.update(kw)
        settings.set("pomodoro", self.pomo_cfg)
        if not self.pomo["running"]:
            self.pomo["remaining"] = self.phase_len()

    def _pomo_next(self, log=True):
        p = self.pomo
        if p["phase"] == "work":
            if log and p["started"]:
                self.log_session("pomodoro", p["started"], time.time(), p["label"])
            p["cycles"] += 1
            p["phase"] = "long" if p["cycles"] % self.pomo_cfg["every"] == 0 else "short"
        else:
            p["phase"] = "work"
        p["started"] = None
        p["remaining"] = self.phase_len()
        if self.pomo_cfg["auto"] and p["running"]:
            p["end"] = time.time() + p["remaining"]
            if p["phase"] == "work":
                p["started"] = time.time()
        else:
            p["running"] = False

    def set_focus(self, on):
        if on == self.focus:
            return
        self.focus = on
        if on:
            self.pomo_reset()
            self.pomo_toggle()
        else:
            p = self.pomo
            if p["phase"] == "work" and p["started"] and time.time() - p["started"] > 60:
                self.log_session("pomodoro", p["started"], time.time(), p["label"])
            self.pomo_reset()
        self.focus_changed.emit(on)

    def add_alarm(self, hhmm, label=None, days=None):
        return self.alarms.add(time=hhmm, label=label or tr("timers.alarms.default_label"),
                               days=days or [], enabled=True)

    def toggle_alarm(self, a):
        self.alarms.update(a, enabled=not a.get("enabled", True))

    def next_alarm(self):
        now = dt.datetime.now()
        best = None
        for a in self.alarms.items:
            if not a.get("enabled", True):
                continue
            h, m = map(int, a["time"].split(":"))
            for add in range(8):
                d = now.date() + dt.timedelta(days=add)
                when = dt.datetime.combine(d, dt.time(h, m))
                if when <= now or (a.get("days") and d.weekday() not in a["days"]):
                    continue
                if best is None or when < best[0]:
                    best = (when, a)
                break
        return best

    def log_session(self, kind, start, end, label=""):
        if end - start >= 30:
            self.sessions.add(kind=kind, start=start, end=end, duration=end - start, label=label)

    def stats(self):
        today = dt.date.today()
        days = [today - dt.timedelta(days=i) for i in range(6, -1, -1)]
        per_day = {d: 0.0 for d in days}
        count_today = 0
        for s in self.sessions.items:
            d = dt.date.fromtimestamp(s["start"])
            if d in per_day:
                per_day[d] += s["duration"] / 60
            if d == today:
                count_today += 1
        total_week = sum(per_day.values())
        streak = 0
        for d in reversed(days):
            if per_day[d] > 0:
                streak += 1
            else:
                break
        return {"days": days, "per_day": per_day, "today": per_day[today], "count_today": count_today,
                "week": total_week, "streak": streak}

    def recent_sessions(self, n=8):
        return sorted(self.sessions.items, key=lambda s: -s["start"])[:n]

    def tick(self):
        now = time.time()
        for t in list(self.timers):
            if t["running"] and now >= t["end"]:
                t["running"] = False
                t["remaining"] = 0
                self.log_session("timer", t["started"], now, t["label"])
                play(SOUND_TIMER)
                self.fired.emit("timer", tr("timers.fired.timer"), t["label"])
        p = self.pomo
        if p["running"] and now >= p["end"]:
            was = p["phase"]
            self._pomo_next()
            play(SOUND_SOFT)
            if was == "work":
                next_phase = tr("timers.pomodoro.long_break") if p["phase"] == "long" \
                    else tr("timers.pomodoro.short_break")
                self.fired.emit("pomodoro", tr("timers.fired.session"),
                                tr("timers.fired.next_break", name=next_phase,
                                   minutes=self.pomo_cfg[p["phase"]]))
            else:
                self.fired.emit("pomodoro", tr("timers.fired.break_over"),
                                tr("timers.fired.back_to_work"))
        n = dt.datetime.now()
        hhmm = n.strftime("%H:%M")
        for a in self.alarms.items:
            if not a.get("enabled", True) or a["time"] != hhmm:
                continue
            if a.get("days") and n.weekday() not in a["days"]:
                continue
            key = (a["id"], n.date(), hhmm)
            if key in self._alarm_fired:
                continue
            self._alarm_fired.add(key)
            play(SOUND_ALARM)
            self.fired.emit("alarm", a.get("label") or tr("timers.alarms.default_label"), hhmm)
            if not a.get("days"):
                self.alarms.update(a, enabled=False)

    def active(self):
        """Timer to show in the compact pill: (label, remaining, fraction) or None."""
        p = self.pomo
        if p["running"]:
            remaining = self.pomo_remaining()
            name = {
                "work": tr("timers.pomodoro.focus_phase"),
                "short": tr("timers.pomodoro.pause_phase"),
                "long": tr("timers.pomodoro.pause_phase"),
            }[p["phase"]]
            return name, remaining, 1 - remaining / max(1, self.phase_len()), "pomo"
        running = [t for t in self.timers if t["running"]]
        if running:
            timer = min(running, key=self.remaining)
            remaining = self.remaining(timer)
            return timer["label"], remaining, 1 - remaining / max(1, timer["duration"]), "timer"
        if self.stopwatch["running"]:
            return tr("tabs.timers.views.sw"), self.sw_elapsed(), None, "sw"
        return None
