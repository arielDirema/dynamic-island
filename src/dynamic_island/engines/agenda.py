"""Agenda: local events + iCal subscriptions (Google Calendar, Outlook, Teams…),
birthdays, reminders and Teams / Zoom / Meet link detection."""
import datetime as dt
import re
import threading
import time
import urllib.request

from PySide6.QtCore import QObject, Signal

from dynamic_island.core.config.settings import settings
from dynamic_island.core.localization import translate as tr
from dynamic_island.engines import nlp
from dynamic_island.infrastructure.storage.collection import Collection

MEET_RE = re.compile(
    r"https://(?:[\w-]+\.)*(?:teams\.microsoft\.com|teams\.live\.com|zoom\.us|meet\.google\.com|"
    r"webex\.com|whereby\.com|meet\.jit\.si)/[^\s\"'<>)]+", re.I)
BIRTHDAY_RE = re.compile(r"\b(anniv(ersaire)?|birthday|geburtstag)\b", re.I)


def meeting_info(*texts):
    for t in texts:
        if not t:
            continue
        m = MEET_RE.search(t)
        if m:
            url = m.group(0).rstrip(".,;>")
            low = url.lower()
            app = ("Teams" if "teams" in low else "Zoom" if "zoom" in low else
                   "Meet" if "meet.google" in low else "Webex" if "webex" in low else "Visio")
            return app, url
    return None, None


class Agenda(QObject):
    changed = Signal()
    reminder = Signal(object)  # occurrence

    def __init__(self):
        super().__init__()
        self.local = Collection("events")
        self.remote = []          # subscribed-calendar occurrences
        self.remote_status = {}   # url -> (ok, message, count)
        self.notified = set()
        self._lock = threading.Lock()
        self._wake = threading.Event()
        threading.Thread(target=self._sync_loop, daemon=True).start()

    @property
    def feeds(self):
        return settings.get("ics_feeds", [])

    def add_feed(self, url, name=None):
        url = url.strip()
        if url.startswith("webcal://"):
            url = "https://" + url[len("webcal://"):]
        if not url.startswith("http"):
            return False
        feeds = [f for f in self.feeds if f["url"] != url]
        feeds.append({"url": url, "name": name or self._guess_name(url)})
        settings.set("ics_feeds", feeds)
        self.refresh()
        return True

    def remove_feed(self, url):
        settings.set("ics_feeds", [f for f in self.feeds if f["url"] != url])
        with self._lock:
            self.remote = [o for o in self.remote if o["feed"] != url]
        self.changed.emit()

    @staticmethod
    def _guess_name(url):
        low = url.lower()
        if "google" in low:
            return tr("agenda.feeds.google")
        if "outlook" in low or "office365" in low or "live.com" in low:
            return "Outlook"
        return tr("agenda.feeds.calendar")

    def refresh(self):
        self._wake.set()

    def _sync_loop(self):
        while True:
            self._fetch_all()
            self._wake.wait(15 * 60)
            self._wake.clear()

    def _fetch_all(self):
        import icalendar
        import recurring_ical_events
        occ = []
        start = dt.datetime.now() - dt.timedelta(days=45)
        end = dt.datetime.now() + dt.timedelta(days=200)
        for feed in list(self.feeds):
            url = feed["url"]
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "DynamicIsland/1.0"})
                data = urllib.request.urlopen(req, timeout=20).read()
                cal = icalendar.Calendar.from_ical(data)
                n = 0
                for ev in recurring_ical_events.of(cal).between(start, end):
                    o = self._from_ical(ev, feed)
                    if o:
                        occ.append(o)
                        n += 1
                self.remote_status[url] = (True, tr("agenda.events_count", count=n), n)
            except Exception as e:
                self.remote_status[url] = (False, str(e)[:80], 0)
        with self._lock:
            self.remote = occ
        self.changed.emit()

    @staticmethod
    def _ts(v):
        if isinstance(v, dt.datetime):
            if v.tzinfo is not None:
                return v.timestamp(), False
            return time.mktime(v.timetuple()), False
        if isinstance(v, dt.date):
            return time.mktime(dt.datetime(v.year, v.month, v.day).timetuple()), True
        return None, False

    def _from_ical(self, ev, feed):
        try:
            s, all_day = self._ts(ev.get("DTSTART").dt)
            e_raw = ev.get("DTEND")
            e = self._ts(e_raw.dt)[0] if e_raw else s + (86400 if all_day else 3600)
            title = str(ev.get("SUMMARY", tr("agenda.untitled")))
            loc = str(ev.get("LOCATION", "") or "")
            desc = str(ev.get("DESCRIPTION", "") or "")
            app, url = meeting_info(loc, desc, str(ev.get("URL", "") or ""))
            return {"id": str(ev.get("UID", "")) + str(s), "title": title, "start": s, "end": e, "all_day": all_day,
                    "location": loc if not loc.startswith("http") else "", "meet_app": app, "meet_url": url,
                    "birthday": bool(BIRTHDAY_RE.search(title)) or "birthday" in feed["url"].lower()
                    or "contacts" in feed["url"].lower(), "source": feed["name"], "feed": feed["url"],
                    "local": False}
        except Exception:
            return None

    def add_event(self, title, start, end=None, all_day=False, location="", birthday=False, remind=10):
        if end is None:
            end = start + (86400 if all_day else 3600)
        app, url = meeting_info(location, title)
        return self.local.add(title=title, start=start, end=end, all_day=all_day, location=location,
                              birthday=birthday, remind=remind, meet_url=url, meet_app=app,
                              recur="yearly" if birthday else None)

    def quick_add(self, text):
        """Quick-add text: “Meeting tomorrow 2:30 pm”, “Marie's birthday 03/12”, “Team sync Monday 10am https://meet…”."""
        r = nlp.parse(text)
        if not r["title"]:
            return None
        date = r["date"] or dt.date.today()
        url_m = MEET_RE.search(text)
        title = MEET_RE.sub("", r["title"]).strip() or r["title"]
        if r["time"] and not r["birthday"]:
            start = time.mktime(dt.datetime.combine(date, r["time"]).timetuple())
            ev = self.add_event(title, start, start + (r["duration"] or 60) * 60,
                                location=url_m.group(0) if url_m else "")
        else:
            start = time.mktime(dt.datetime(date.year, date.month, date.day).timetuple())
            ev = self.add_event(title, start, all_day=True, birthday=r["birthday"])
        self.changed.emit()
        return ev

    def delete(self, occ):
        ev = self.local.get(occ["id"])
        if ev:
            self.local.remove(ev)
            self.changed.emit()

    def update(self, occ, **fields):
        ev = self.local.get(occ["id"])
        if ev:
            self.local.update(ev, **fields)
            self.changed.emit()

    def _local_occurrences(self, a, b):
        out = []
        for ev in self.local.items:
            base = dict(ev, local=True, source=tr("agenda.local_source"), feed=None)
            if ev.get("recur") == "yearly":
                d0 = dt.datetime.fromtimestamp(ev["start"])
                y0 = dt.datetime.fromtimestamp(a).year
                for y in (y0 - 1, y0, y0 + 1):
                    try:
                        s = time.mktime(d0.replace(year=y).timetuple())
                    except ValueError:
                        continue
                    if a <= s < b:
                        o = dict(base, start=s, end=s + (ev["end"] - ev["start"]))
                        o["age"] = y - d0.year if y > d0.year else None
                        out.append(o)
            elif ev["end"] > a and ev["start"] < b:
                out.append(base)
        return out

    def between(self, a, b):
        with self._lock:
            rem = [o for o in self.remote if o["end"] > a and o["start"] < b]
        res = self._local_occurrences(a, b) + rem
        res.sort(key=lambda o: (not o["all_day"], o["start"]))
        return res

    def day(self, date):
        a = time.mktime(dt.datetime(date.year, date.month, date.day).timetuple())
        evs = self.between(a, a + 86400)
        evs.sort(key=lambda o: (not o["all_day"], o["start"]))
        return evs

    def upcoming(self, n=10, days=30, include_running=True):
        now = time.time()
        evs = [o for o in self.between(now - 86400, now + days * 86400)
               if (o["end"] > now if include_running else o["start"] > now)]
        evs = [o for o in evs if not o["all_day"] or o["start"] + 86400 > now]
        evs.sort(key=lambda o: (o["start"] if not o["all_day"] else max(o["start"], now - 1)))
        return evs[:n]

    def next_timed(self):
        now = time.time()
        for o in self.upcoming(20, 7):
            if not o["all_day"] and o["start"] > now - 300:
                return o
        return None

    def birthdays(self, days=60):
        now = time.time()
        today = time.mktime(dt.date.today().timetuple())
        return [o for o in self.between(today, now + days * 86400) if o.get("birthday")]

    def count_by_day(self, first, last):
        a = time.mktime(dt.datetime(first.year, first.month, first.day).timetuple())
        b = time.mktime(dt.datetime(last.year, last.month, last.day).timetuple()) + 86400
        counts = {}
        for o in self.between(a, b):
            d = dt.date.fromtimestamp(max(o["start"], a))
            counts.setdefault(d, []).append(o)
        return counts

    def check_reminders(self):
        now = time.time()
        for o in self.upcoming(15, 2):
            if o["all_day"]:
                continue
            lead = (o.get("remind") if o.get("local") else settings.get("remind_min", 10)) or 0
            key = (o["id"], o["start"])
            if o["start"] - lead * 60 <= now < o["start"] + 60 and key not in self.notified:
                self.notified.add(key)
                self.reminder.emit(o)
