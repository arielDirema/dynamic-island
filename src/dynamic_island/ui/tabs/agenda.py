"""Agenda tab: upcoming events, week, month, accounts and quick add."""
import datetime as dt
import time

from PySide6.QtCore import QPointF, QRectF

from dynamic_island.core.config.settings import settings
from dynamic_island.core.localization import format_date, format_day_name, translate as tr
from dynamic_island.core.utilities.formatting import until
from dynamic_island.engines import nlp
from dynamic_island.ui.components.drawing import CENTER, RIGHT
from dynamic_island.ui.resources import icons
from dynamic_island.ui.themes import G, T, W, font

CONTENT_H = 372
VIEWS = [
    ("up", "tabs.agenda.views.up"),
    ("week", "tabs.agenda.views.week"),
    ("month", "tabs.agenda.views.month"),
    ("accounts", "tabs.agenda.views.accounts"),
]


class AgendaTab:
    key, label_key, glyph = "agenda", "tabs.agenda", G["calendar"]

    def __init__(self, isl):
        self.isl = isl
        self.view = "up"
        self.week0 = self._monday(dt.date.today())
        self.month = dt.date.today().replace(day=1)
        self.sel_day = dt.date.today()
        self.editing = None

    @staticmethod
    def _monday(day):
        return day - dt.timedelta(days=day.weekday())

    def height(self):
        return CONTENT_H

    def set_view(self, view):
        self.view = view

    def paint(self, ui, cr):
        x0, x1 = cr.left() + 16, cr.right() - 16
        ui.segmented(QRectF(x0 - 6, cr.top(), 0, 30), VIEWS, self.view, self.set_view)
        y = cr.top() + 36
        if self.view != "accounts":
            placeholder = tr("agenda.edit_placeholder") if self.editing else tr("agenda.add_placeholder")
            ui.field(QRectF(x0, y, x1 - x0, 30), "agenda_add", placeholder,
                     on_submit=self._submit, glyph=G["add"])
            y += 38
        body = QRectF(cr.left() + 8, y, cr.width() - 16, cr.bottom() - y - 8)
        getattr(self, "_" + self.view)(ui, body)

    def _submit(self, text):
        if self.editing:
            occurrence, self.editing = self.editing, None
            result = nlp.parse(text)
            date = result["date"] or dt.date.fromtimestamp(occurrence["start"])
            if result["time"]:
                start = time.mktime(dt.datetime.combine(date, result["time"]).timetuple())
                self.isl.agenda.update(
                    occurrence,
                    title=result["title"] or occurrence["title"],
                    start=start,
                    end=start + (occurrence["end"] - occurrence["start"] if not occurrence["all_day"] else 3600),
                    all_day=False,
                )
            else:
                start = time.mktime(dt.datetime(date.year, date.month, date.day).timetuple())
                self.isl.agenda.update(
                    occurrence, title=result["title"] or occurrence["title"],
                    start=start, end=start + 86400, all_day=True,
                )
            return True
        event = self.isl.agenda.quick_add(text)
        if event:
            self.isl.show_alert("event", tr("agenda.event_added"), event["title"], T.accent, G["calendar"])
            self.sel_day = dt.date.fromtimestamp(event["start"])
        return event is not None

    def edit(self, occurrence):
        self.editing = occurrence
        day = dt.datetime.fromtimestamp(occurrence["start"])
        text = f"{occurrence['title']} {day.day:02d}/{day.month:02d}"
        if not occurrence["all_day"]:
            text += f" {day.hour}h{day.minute:02d}"
        self.isl.fields["agenda_add"] = text
        self.isl.focus("agenda_add")

    def _up(self, ui, body):
        isl = self.isl
        events = isl.agenda.upcoming(40, 60)
        if not events:
            ui.empty(body, G["calendar"], tr("agenda.no_upcoming"), tr("agenda.no_upcoming_hint"))
            return

        def draw(y0):
            y = y0
            last = None
            for occurrence in events:
                day = dt.date.fromtimestamp(
                    max(occurrence["start"], time.time()) if occurrence["all_day"] else occurrence["start"]
                )
                if day != last:
                    last = day
                    ui.text(QRectF(body.left() + 8, y + 4, 300, 18), self._day_label(day),
                            font(8, W.DemiBold), T.text2)
                    y += 24
                y = self.event_row(ui, body.left() + 4, body.right() - 8, y, occurrence)
            return y - y0
        ui.scroll("agenda_up", body, draw)

    @staticmethod
    def _day_label(day):
        today = dt.date.today()
        base = format_date(day, "EEEE d MMMM").capitalize()
        if day == today:
            return tr("agenda.today_date", date=base)
        if day == today + dt.timedelta(days=1):
            return tr("agenda.tomorrow_date", date=base)
        return base

    def event_row(self, ui, x0, x1, y, occurrence, compact=False):
        isl = self.isl
        now = time.time()
        r = QRectF(x0, y, x1 - x0, 46)
        if ui.visible(r):
            hover = ui.row_hover(r)
            ui.rect(r, T.layer2 if hover else T.layer, 6, T.stroke)
            color = T.orange if occurrence.get("birthday") else (
                T.accent if occurrence.get("local") else T.purple
            )
            ui.rect(QRectF(r.left() + 6, r.top() + 8, 3, 30), color, 1.5)
            if occurrence["all_day"]:
                when = tr("common.all_day")
            else:
                start, end = (dt.datetime.fromtimestamp(occurrence["start"]),
                              dt.datetime.fromtimestamp(occurrence["end"]))
                when = f"{start:%H:%M} – {end:%H:%M}"
            right = 10
            if occurrence.get("meet_url") and occurrence["end"] > now:
                br = QRectF(r.right() - 100, r.top() + 9, 90, 28)
                ui.button(br, tr("common.join"), lambda url=occurrence["meet_url"]: isl.open_url(url),
                          G["video"], accent=True)
                right = 106
            elif not occurrence["all_day"] and occurrence["start"] > now and occurrence["start"] - now < 86400:
                ui.text(QRectF(r.right() - 100, r.top(), 90, 46), until(occurrence["start"] - now),
                        font(8, W.DemiBold), T.accent, RIGHT)
                right = 100
            elif not occurrence["all_day"] and occurrence["start"] <= now < occurrence["end"]:
                right = 90
                ui.badge(r.right() - 80, r.top() + 15, tr("agenda.in_progress"), T.success)
            if occurrence.get("local") and hover:
                ui.icon_button(QPointF(r.right() - right - 14, r.center().y()), G["delete"],
                               lambda occurrence=occurrence: isl.agenda.delete(occurrence), 12, T.critical, 26)
                ui.icon_button(QPointF(r.right() - right - 42, r.center().y()), G["edit"],
                               lambda occurrence=occurrence: self.edit(occurrence), 12, None, 26)
                right += 60
            title = occurrence["title"]
            tx = r.left() + 18
            if occurrence.get("birthday"):
                title += tr("agenda.birthday_age", age=occurrence["age"]) if occurrence.get("age") else ""
                icons.cake(ui.p, QRectF(tx, r.top() + 6, 16, 16))
                tx += 20
            ui.text(QRectF(tx, r.top() + 6, r.right() - 8 - right - tx, 18), title,
                    font(9, W.DemiBold))
            source = occurrence.get("meet_app") or occurrence.get("location") or occurrence.get("source", "")
            ui.text(QRectF(r.left() + 18, r.top() + 24, r.width() - 26 - right, 16),
                    when + (" · " + source if source else ""), font(8), T.text2)
        return y + 52

    def _week(self, ui, body):
        isl = self.isl
        days = [self.week0 + dt.timedelta(days=index) for index in range(7)]
        y = body.top()
        ui.icon_button(QPointF(body.left() + 14, y + 12), G["left"], lambda: self._shift_week(-1), 11)
        ui.icon_button(QPointF(body.left() + 42, y + 12), G["right"], lambda: self._shift_week(1), 11)
        title = f"{format_date(days[0], 'd MMM')} – {format_date(days[6], 'd MMM yyyy')}"
        ui.text(QRectF(body.left() + 60, y, 300, 24), title, font(9, W.DemiBold))
        ui.button(QRectF(body.right() - 92, y, 84, 24), tr("agenda.this_week"),
                  lambda: setattr(self, "week0", self._monday(dt.date.today())))
        y += 30
        counts = isl.agenda.count_by_day(days[0], days[6])
        column_width = (body.width() - 8) / 7
        today = dt.date.today()
        for index, day in enumerate(days):
            cx = body.left() + 4 + index * column_width
            col = QRectF(cx + 1, y, column_width - 2, body.bottom() - y)
            ui.rect(col, T.layer2 if day == today else T.layer, 6, T.stroke)
            ui.text(QRectF(cx, y + 4, column_width, 14),
                    format_day_name(day, "abbreviated").rstrip(".").capitalize(),
                    font(7.5, W.DemiBold), T.accent if day == today else T.text3, CENTER)
            ui.text(QRectF(cx, y + 18, column_width, 20), str(day.day), font(11, W.DemiBold, True),
                    T.accent if day == today else T.text, CENTER)
            ui.hit(QRectF(cx, y, column_width, 40), lambda day=day: self._open_day(day))
            yy = y + 44
            for occurrence in counts.get(day, [])[:6]:
                er = QRectF(cx + 4, yy, column_width - 8, 32)
                color = T.orange if occurrence.get("birthday") else (
                    T.accent if occurrence.get("local") else T.purple
                )
                ui.rect(er, T.tint(color, 45), 4)
                ui.rect(QRectF(er.left(), er.top(), 2, er.height()), color, 1)
                label = tr("agenda.week_all_day") if occurrence["all_day"] else \
                    dt.datetime.fromtimestamp(occurrence["start"]).strftime("%H:%M")
                ui.text(QRectF(er.left() + 6, er.top() + 2, er.width() - 8, 14), label,
                        font(6.5, W.DemiBold), T.text2)
                ui.text(QRectF(er.left() + 6, er.top() + 15, er.width() - 8, 15), occurrence["title"],
                        font(7.5), T.text)
                if occurrence.get("meet_url"):
                    ui.hit(er, lambda url=occurrence["meet_url"]: isl.open_url(url))
                yy += 36
            extra = len(counts.get(day, [])) - 6
            if extra > 0:
                ui.text(QRectF(cx, yy, column_width, 14), f"+{extra}", font(7.5), T.text3, CENTER)

    def _shift_week(self, count):
        self.week0 += dt.timedelta(days=7 * count)

    def _open_day(self, day):
        self.sel_day = day
        self.month = day.replace(day=1)
        self.view = "month"

    def _month(self, ui, body):
        isl = self.isl
        month_start = self.month
        y = body.top()
        grid_width = 7 * 38
        ui.icon_button(QPointF(body.left() + 14, y + 12), G["left"], lambda: self._shift_month(-1), 11)
        ui.icon_button(QPointF(body.left() + grid_width - 10, y + 12), G["right"],
                       lambda: self._shift_month(1), 11)
        ui.text(QRectF(body.left() + 30, y, grid_width - 60, 24),
                format_date(month_start, "MMMM yyyy").capitalize(),
                font(9.5, W.DemiBold), T.text, CENTER)
        y += 28
        self.month_grid(ui, QRectF(body.left() + 4, y, grid_width, body.bottom() - y), month_start,
                        self.sel_day, lambda day: setattr(self, "sel_day", day))
        lx = body.left() + grid_width + 18
        lr = QRectF(lx, body.top(), body.right() - lx, body.height())
        ui.text(QRectF(lx, lr.top(), lr.width(), 24), self._day_label(self.sel_day),
                font(9, W.DemiBold))
        events = isl.agenda.day(self.sel_day)
        if not events:
            ui.text(QRectF(lx, lr.top() + 30, lr.width(), 18), tr("agenda.no_events"),
                    font(8.5), T.text3)
            return

        def draw(y0):
            yy = y0
            for occurrence in events:
                yy = self.event_row(ui, lx, lr.right() - 6, yy, occurrence)
            return yy - y0
        ui.scroll("agenda_day", QRectF(lx - 2, lr.top() + 28, lr.width() + 2, lr.height() - 28), draw)

    def _shift_month(self, count):
        month = self.month.month - 1 + count
        self.month = dt.date(self.month.year + month // 12, month % 12 + 1, 1)

    def month_grid(self, ui, r, month_start, selected, on_click, mini=False):
        column_width = r.width() / 7
        first = month_start - dt.timedelta(days=month_start.weekday())
        for index in range(7):
            day = first + dt.timedelta(days=index)
            ui.text(QRectF(r.left() + index * column_width, r.top(), column_width, 16),
                    format_day_name(day, "abbreviated").rstrip(".")[:2].capitalize(),
                    font(7, W.DemiBold), T.text3, CENTER)
        last = first + dt.timedelta(days=41)
        counts = self.isl.agenda.count_by_day(first, last)
        row_height = min(38.0, (r.height() - 18) / 6)
        today = dt.date.today()
        for index in range(42):
            day = first + dt.timedelta(days=index)
            cx = r.left() + (index % 7) * column_width
            cy = r.top() + 18 + (index // 7) * row_height
            cell = QRectF(cx + 1, cy + 1, column_width - 2, row_height - 2)
            center = cell.center()
            radius = min(column_width, row_height) / 2 - 3
            if day == today:
                ui.p.setPen(T.accent)
                ui.p.setBrush(T.accent)
                ui.p.drawEllipse(center, radius, radius)
            elif day == selected:
                ui.rect(cell.adjusted(2, 2, -2, -2), T.layer2, 4, T.stroke2)
            elif ui.hovering(cell):
                ui.rect(cell.adjusted(2, 2, -2, -2), T.hover, 4)
            color = T.on_accent if day == today else (T.text if day.month == month_start.month else T.disabled)
            ui.text(QRectF(cell.left(), cell.top() - (3 if counts.get(day) else 0), cell.width(), cell.height()),
                    str(day.day), font(7.5 if mini else 8.5, W.DemiBold if day == today else W.Normal),
                    color, CENTER)
            events = counts.get(day)
            if events:
                count = min(3, len(events))
                for marker in range(count):
                    occurrence = events[marker]
                    marker_color = T.on_accent if day == today else (
                        T.orange if occurrence.get("birthday") else T.accent
                    )
                    ui.p.setPen(marker_color)
                    ui.p.setBrush(marker_color)
                    ui.p.drawEllipse(QPointF(center.x() + (marker - (count - 1) / 2) * 5,
                                             center.y() + radius - 4), 1.6, 1.6)
            ui.hit(cell, lambda day=day: on_click(day))

    def _accounts(self, ui, body):
        isl = self.isl
        x0, x1 = body.left() + 8, body.right() - 8
        y = body.top() + 2
        ui.text(QRectF(x0, y, x1 - x0, 18), tr("agenda.sync_title"), font(9.5, W.DemiBold))
        y += 22
        ui.wrap(QRectF(x0, y, x1 - x0, 46), tr("agenda.sync_help"), font(8), T.text2, lines=3)
        y += 52
        ui.field(QRectF(x0, y, x1 - x0, 30), "ics_url", tr("agenda.ics_placeholder"),
                 on_submit=lambda text: isl.agenda.add_feed(text), glyph=G["link"])
        y += 40
        feeds = isl.agenda.feeds
        if not feeds:
            ui.text(QRectF(x0, y, x1 - x0, 20), tr("agenda.no_calendars"), font(8.5), T.text3)
            y += 26
        for feed in feeds:
            r = QRectF(x0, y, x1 - x0, 40)
            ui.card(r)
            ok, message, _count = isl.agenda.remote_status.get(
                feed["url"], (None, tr("agenda.syncing"), 0)
            )
            ui.glyph(QPointF(r.left() + 18, r.center().y()), G["cloud"], 14,
                     T.success if ok else (T.critical if ok is False else T.text3))
            ui.text(QRectF(r.left() + 36, r.top() + 4, r.width() - 120, 18), feed["name"],
                    font(9, W.DemiBold))
            ui.text(QRectF(r.left() + 36, r.top() + 21, r.width() - 120, 15), message,
                    font(7.5), T.critical if ok is False else T.text2)
            ui.button(QRectF(r.right() - 76, r.top() + 8, 68, 24), tr("common.remove"),
                      lambda url=feed["url"]: isl.agenda.remove_feed(url), danger=True)
            y += 46
        y += 4
        ui.text(QRectF(x0, y, 220, 24), tr("agenda.reminder_before"), font(8.5, W.Medium))
        x = x0 + 190
        current = settings.get("remind_min", 10)
        for minutes in (0, 5, 10, 15, 30):
            label = tr("units.minutes", count=minutes)
            width = ui.chip_w(label)
            ui.chip(QRectF(x, y + 1, width, 22), label, minutes == current,
                    lambda minutes=minutes: settings.set("remind_min", minutes))
            x += width + 4
        y += 30
        ui.button(QRectF(x0, y, 160, 26), tr("agenda.refresh_now"), isl.agenda.refresh, G["refresh"])
