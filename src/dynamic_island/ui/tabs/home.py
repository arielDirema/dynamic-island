"""Home tab: time, date, weather, media, next event, daily tasks and timers."""
import datetime as dt
import time

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor

from dynamic_island.core.localization import (
    format_date,
    format_day_name,
    format_month_name,
    format_time,
    translate as tr,
)
from dynamic_island.core.utilities.formatting import fmt_dur, until
from dynamic_island.models.infos import WMO_KEYS
from dynamic_island.ui.components.drawing import RIGHT
from dynamic_island.ui.resources import icons
from dynamic_island.ui.themes import G, T, W, font

CONTENT_H = 372


class HomeTab:
    key, label_key, glyph = "home", "tabs.home", G["home"]

    def __init__(self, isl):
        self.isl = isl

    def height(self):
        return CONTENT_H

    def paint(self, ui, cr):
        isl = self.isl
        now = dt.datetime.now()
        x0, x1 = cr.left() + 16, cr.right() - 16
        y = cr.top() + 4

        ui.text(QRectF(x0, y, 220, 46), format_time(now), font(28, W.Light, True), T.text)
        ui.text(QRectF(x0 + 2, y + 46, 300, 18), format_date(now, "full").capitalize(), font(9), T.text2)

        w = isl.infos.weather
        if w:
            label = tr(WMO_KEYS.get(w["code"], "weather.wmo.unknown"))
            icons.weather(ui.p, QRectF(x1 - 214, y, 50, 50), w["code"], w.get("is_day", True))
            ui.text(QRectF(x1 - 160, y + 2, 160, 28), f"{w['temp']:.0f}°", font(18, W.DemiBold, True), T.text, RIGHT)
            sub = f"{label} · {w['city']}"
            ui.text(QRectF(x1 - 260, y + 32, 260, 16), sub, font(8), T.text2, RIGHT)
            if w.get("rain_now") is not None:
                ui.text(QRectF(x1 - 260, y + 48, 260, 16),
                        tr("home.weather.details", rain=w["rain_now"], feels=f"{w['feels']:.0f}"),
                        font(8), T.text3, RIGHT)
            ui.hit(QRectF(x1 - 260, y, 260, 64), lambda: isl.set_tab("infos"))
        elif isl.infos.weather_err:
            ui.text(QRectF(x1 - 260, y + 10, 260, 18), isl.infos.weather_err, font(8), T.text3, RIGHT)

        y += 72
        ui.scroll("home", QRectF(cr.left() + 8, y, cr.width() - 16, cr.bottom() - y - 8),
                  lambda yy: self._body(ui, cr, yy))

    def _body(self, ui, cr, y0):
        isl = self.isl
        x0, x1 = cr.left() + 16, cr.right() - 16
        y = y0

        m = isl.media
        if m:
            card = QRectF(x0 - 4, y, x1 - x0 + 8, 74)
            ui.card(card)
            art = QRectF(card.left() + 10, card.top() + 10, 54, 54)
            isl.draw_art(ui.p, art, 6)
            tx = card.left() + 76
            tw = card.width() - 76 - 176
            info = QRectF(art.left(), card.top() + 4, tx + tw - art.left(), 44)
            if ui.row_hover(info):  # clicking the artwork or title opens the player
                ui.rect(art, QColor(0, 0, 0, 120), 6)
                ui.glyph(art.center(), G["open"], 16, T.text)
            ui.hit(info, isl.open_media_app)
            ui.text(QRectF(tx, card.top() + 12, tw, 18), m["title"], font(9.5, W.DemiBold))
            sub = " · ".join(x for x in (m["artist"], m["app"]) if x)
            ui.text(QRectF(tx, card.top() + 31, tw, 16), sub, font(8.5), T.text2)
            if m["duration"] > 0:
                ui.bar(QRectF(tx, card.top() + 54, tw, 3), isl.media_position() / m["duration"])
            # button: real icon of the playing application
            ab = QRectF(card.right() - 172, card.center().y() - 17, 34, 34)
            if ui.hovering(ab):
                ui.rect(ab, T.hover, 4)
            if isl.media_exe:
                ui.file_icon(ab.adjusted(8, 8, -8, -8), isl.media_exe, G["open"])
            else:
                ui.glyph(ab.center(), G["open"], 13, T.text2)
            ui.hit(ab, isl.open_media_app)
            cx, cy = card.right() - 70, card.center().y()
            ui.icon_button(QPointF(cx - 38, cy), "\ue892", lambda: isl.media_cmd("previous"), 14)
            ui.icon_button(QPointF(cx, cy), G["pause"] if m["playing"] else G["play"],
                           lambda: isl.media_cmd("play_pause"), 16, T.text, 34)
            ui.icon_button(QPointF(cx + 38, cy), "\ue893", lambda: isl.media_cmd("next"), 14)
            y += 82

        act = isl.timers.active()
        if act:
            label, rem, frac, kind = act
            card = QRectF(x0 - 4, y, x1 - x0 + 8, 44)
            ui.card(card)
            col = T.success if kind == "pomo" and isl.timers.pomo["phase"] != "work" else T.accent
            if frac is not None:
                ui.ring(QPointF(card.left() + 24, card.center().y()), 11, frac, col, 3)
            else:
                ui.glyph(QPointF(card.left() + 24, card.center().y()), G["timer"], 14, col)
            ui.text(QRectF(card.left() + 46, card.top(), 200, 44), label, font(9, W.Medium))
            ui.text(QRectF(card.right() - 150, card.top(), 136, 44), fmt_dur(rem), font(14, W.DemiBold, True), T.text, RIGHT)
            ui.hit(card, lambda: isl.set_tab("timers"))
            y += 52

        ui.section(x0, y, x1 - x0, tr("home.upcoming"), tr("home.agenda_link"), lambda: isl.set_tab("agenda"))
        y += 22
        nxt = isl.agenda.upcoming(3, 14)
        if not nxt:
            ui.text(QRectF(x0, y, x1 - x0, 20), tr("home.no_upcoming"), font(8.5), T.text3)
            y += 26
        for event in nxt[:2]:
            y = self._event_row(ui, x0, x1, y, event)
        birthdays = [b for b in isl.agenda.birthdays(30) if b not in nxt]
        if birthdays:
            birthday = birthdays[0]
            day = dt.date.fromtimestamp(birthday["start"])
            age = tr("home.birthday_age", age=birthday["age"]) if birthday.get("age") else ""
            icons.cake(ui.p, QRectF(x0, y, 17, 17))
            ui.text(QRectF(x0 + 22, y, x1 - x0 - 22, 18),
                    f"{birthday['title']}{age} — {day.day} {format_month_name(day)}",
                    font(8.5), T.text2)
            y += 24

        y += 6
        todo, done = isl.tasks.today_counts()
        ui.section(x0, y, x1 - x0, tr("home.today_tasks"),
                   tr("home.tasks_done", done=done, total=todo + done), lambda: isl.set_tab("tasks"))
        y += 24
        ui.field(QRectF(x0, y, x1 - x0, 30), "home_task", tr("home.add_task_placeholder"),
                 on_submit=lambda text: isl.tasks.quick_add(text) is not None, glyph=G["add"])
        y += 36
        tasks = [task for task in isl.tasks.query("today") if not task.get("done")][:4]
        if not tasks:
            ui.text(QRectF(x0, y, x1 - x0, 20), tr("home.no_tasks"), font(8.5), T.text3)
            y += 24
        for task in tasks:
            r = QRectF(x0 - 4, y, x1 - x0 + 8, 28)
            if ui.row_hover(r):
                ui.rect(r, T.hover, 4)
            col = {3: T.critical, 2: T.orange, 1: T.accent}.get(task.get("priority", 0), T.track)
            ui.checkbox(QPointF(x0 + 8, y + 14), task.get("done"), lambda task=task: isl.tasks.toggle(task),
                        col, round_=True)
            ui.text(QRectF(x0 + 24, y, x1 - x0 - 140, 28), task["title"], font(9))
            label, late = isl.tasks.due_label(task)
            if label:
                ui.text(QRectF(x1 - 120, y, 116, 28), label, font(8), T.critical if late else T.text3, RIGHT)
            y += 30
        return y - y0 + 6

    def _event_row(self, ui, x0, x1, y, event):
        isl = self.isl
        now = time.time()
        r = QRectF(x0 - 4, y, x1 - x0 + 8, 44)
        ui.card(r)
        col = T.orange if event.get("birthday") else (T.accent if event.get("local") else T.purple)
        ui.rect(QRectF(r.left() + 6, r.top() + 8, 3, 28), col, 1.5)
        day = dt.date.fromtimestamp(event["start"])
        if event["all_day"]:
            when = tr("common.all_day")
        else:
            when = dt.datetime.fromtimestamp(event["start"]).strftime("%H:%M")
            when += "–" + dt.datetime.fromtimestamp(event["end"]).strftime("%H:%M")
        if day != dt.date.today():
            when = (tr("common.tomorrow") + " " if day == dt.date.today() + dt.timedelta(days=1)
                    else f"{format_day_name(day, 'abbreviated').capitalize()} {day.day} ") + when
        right_w = 0
        if event.get("meet_url"):
            right_w = 96
            br = QRectF(r.right() - 92, r.top() + 8, 84, 28)
            ui.button(br, tr("common.join"), lambda url=event["meet_url"]: isl.open_url(url), G["video"], accent=True)
        elif not event["all_day"] and event["start"] > now:
            right_w = 90
            ui.text(QRectF(r.right() - 96, r.top(), 86, 44), until(event["start"] - now),
                    font(8.5, W.DemiBold), T.accent, RIGHT)
        ui.text(QRectF(r.left() + 18, r.top() + 5, r.width() - 30 - right_w, 18), event["title"],
                font(9, W.DemiBold))
        sub = when + (f" · {event['meet_app']}" if event.get("meet_app") else
                      (f" · {event['location']}" if event.get("location") else ""))
        ui.text(QRectF(r.left() + 18, r.top() + 23, r.width() - 30 - right_w, 16), sub, font(8), T.text2)
        return y + 50
