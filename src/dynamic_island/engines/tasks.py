"""Tasks (priorities, due dates, reminders, projects) and quick notes."""
import datetime as dt
import time

from PySide6.QtCore import QObject, Signal

from dynamic_island.core.localization import format_date, format_day_name, translate as tr
from dynamic_island.engines import nlp
from dynamic_island.infrastructure.storage.collection import Collection


class Tasks(QObject):
    reminder = Signal(object)

    def __init__(self):
        super().__init__()
        self.tasks = Collection("tasks")
        self.notes = Collection("notes")

    def quick_add(self, text):
        """“Send quote tomorrow 9am !high #client” → task with due date, reminder, priority and project."""
        r = nlp.parse(text)
        if not r["title"]:
            return None
        due = remind = None
        if r["date"]:
            due = r["date"].isoformat()
            if r["time"]:
                remind = time.mktime(dt.datetime.combine(r["date"], r["time"]).timetuple())
        return self.tasks.add(title=r["title"], done=False, priority=r["priority"], due=due,
                              due_time=r["time"].strftime("%H:%M") if r["time"] else None,
                              remind=remind, project=r["project"], done_at=None, reminded=False)

    def toggle(self, t):
        done = not t.get("done")
        self.tasks.update(t, done=done, done_at=time.time() if done else None)

    def set_priority(self, t, p):
        self.tasks.update(t, priority=p)

    def cycle_priority(self, t):
        self.tasks.update(t, priority=(t.get("priority", 0) + 1) % 4)

    def delete(self, t):
        self.tasks.remove(t)

    def projects(self):
        return sorted({t["project"] for t in self.tasks.items if t.get("project")})

    @staticmethod
    def _due(t):
        return dt.date.fromisoformat(t["due"]) if t.get("due") else None

    def sort_key(self, t):
        d = self._due(t)
        return (t.get("done", False), d is None, d or dt.date.max, -t.get("priority", 0), t.get("created", 0))

    def query(self, view="today", project=None, show_done=False):
        today = dt.date.today()
        out = []
        for t in self.tasks.items:
            if project and t.get("project") != project:
                continue
            d = self._due(t)
            if view == "today":
                if t.get("done"):
                    if not (t.get("done_at") and dt.date.fromtimestamp(t["done_at"]) == today):
                        continue
                elif not (d and d <= today):
                    continue
            elif not show_done and t.get("done"):
                continue
            out.append(t)
        out.sort(key=self.sort_key)
        return out

    def today_counts(self):
        today = dt.date.today()
        todo = [t for t in self.tasks.items if not t.get("done") and self._due(t) and self._due(t) <= today]
        done = [t for t in self.tasks.items if t.get("done") and t.get("done_at")
                and dt.date.fromtimestamp(t["done_at"]) == today]
        return len(todo), len(done)

    def done_this_week(self):
        a = time.time() - 7 * 86400
        return sum(1 for t in self.tasks.items if t.get("done") and (t.get("done_at") or 0) > a)

    def due_label(self, t):
        d = self._due(t)
        if not d:
            return None, False
        today = dt.date.today()
        late = d < today and not t.get("done")
        if d == today:
            label = tr("common.today")
        elif d == today + dt.timedelta(days=1):
            label = tr("common.tomorrow")
        elif d == today - dt.timedelta(days=1):
            label = tr("common.yesterday")
        elif 0 < (d - today).days < 7:
            label = format_day_name(d, "wide").capitalize()
        else:
            label = format_date(d, "d MMM")
        if t.get("due_time"):
            label += " " + t["due_time"]
        return label, late

    def check_reminders(self):
        now = time.time()
        for t in self.tasks.items:
            if t.get("remind") and not t.get("done") and not t.get("reminded") and now >= t["remind"]:
                self.tasks.update(t, reminded=True)
                self.reminder.emit(t)

    def add_note(self, text):
        text = text.strip()
        if not text:
            return None
        return self.notes.add(text=text, pinned=False)

    def edit_note(self, n, text):
        if text.strip():
            self.notes.update(n, text=text.strip())
        else:
            self.notes.remove(n)

    def toggle_pin_note(self, n):
        self.notes.update(n, pinned=not n.get("pinned"))

    def delete_note(self, n):
        self.notes.remove(n)

    def query_notes(self, search=""):
        s = search.lower().strip()
        out = [n for n in self.notes.items if not s or s in n["text"].lower()]
        out.sort(key=lambda n: (not n.get("pinned"), -n.get("mtime", 0)))
        return out
