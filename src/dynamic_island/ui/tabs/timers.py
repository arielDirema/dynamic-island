"""Timers tab: multiple countdowns, Pomodoro, stopwatch, alarms and statistics."""
import datetime as dt
import re

from PySide6.QtCore import QPointF, QRectF

from dynamic_island.core.localization import (
    format_date,
    format_day_name,
    format_time,
    translate as tr,
    weekday_names,
)
from dynamic_island.core.utilities.formatting import fmt_dur, fmt_minutes
from dynamic_island.engines import nlp
from dynamic_island.ui.components.drawing import CENTER, RIGHT
from dynamic_island.ui.themes import G, T, W, font

CONTENT_H = 372
VIEWS = [
    ("timers", "tabs.timers.views.timers"),
    ("pomo", "tabs.timers.views.pomo"),
    ("sw", "tabs.timers.views.sw"),
    ("alarms", "tabs.timers.views.alarms"),
    ("stats", "tabs.timers.views.stats"),
]
PRESETS = [60, 180, 300, 600, 900, 1800, 3600]


class TimersTab:
    key, label_key, glyph = "timers", "tabs.timers", G["timer"]

    def __init__(self, isl):
        self.isl = isl
        self.view = "timers"

    def height(self):
        return CONTENT_H

    def set_view(self, view):
        self.view = view

    def paint(self, ui, cr):
        x0 = cr.left() + 16
        ui.segmented(QRectF(x0 - 6, cr.top(), 0, 30), VIEWS, self.view, self.set_view)
        body = QRectF(cr.left() + 16, cr.top() + 38, cr.width() - 32, cr.height() - 46)
        getattr(self, "_" + self.view)(ui, body)

    def _add(self, text):
        match = re.match(r"\s*(\S+)\s*(.*)", text)
        if not match:
            return False
        seconds = nlp.parse_duration(match.group(1))
        if not seconds:
            return False
        self.isl.timers.add_timer(seconds, match.group(2).strip() or None)
        return True

    def _timers(self, ui, body):
        timers = self.isl.timers
        x = body.left()
        for seconds in PRESETS:
            label = (tr("units.minutes", count=seconds // 60) if seconds < 3600
                     else tr("units.hours", count=1))
            width = ui.chip_w(label, G["add"])
            ui.chip(QRectF(x, body.top(), width, 24), label, False,
                    lambda seconds=seconds: timers.add_timer(seconds), G["add"])
            x += width + 4
        ui.field(QRectF(body.left(), body.top() + 32, body.width(), 30), "timer_add",
                 tr("timers.add_placeholder"), on_submit=self._add, glyph=G["timer"])
        lr = QRectF(body.left() - 8, body.top() + 70, body.width() + 16, body.height() - 70)
        if not timers.timers:
            ui.empty(lr, G["timer"], tr("timers.empty"), tr("timers.empty_hint"))
            return

        def draw(y0):
            y = y0
            for timer in list(timers.timers):
                r = QRectF(lr.left() + 8, y, lr.width() - 22, 58)
                if ui.visible(r):
                    ui.card(r)
                    remaining = timers.remaining(timer)
                    done = remaining <= 0
                    color = T.success if done else T.accent
                    ui.ring(QPointF(r.left() + 30, r.center().y()), 17,
                            1 - remaining / max(1, timer["duration"]), color, 3.5)
                    ui.glyph(QPointF(r.left() + 30, r.center().y()), G["check"] if done else
                             (G["pause"] if timer["running"] else G["play"]), 11, color)
                    ui.hit(QRectF(r.left() + 10, r.top() + 9, 40, 40),
                           lambda timer=timer: timers.toggle_timer(timer))
                    ui.text(QRectF(r.left() + 60, r.top() + 6, 220, 26), fmt_dur(remaining),
                            font(15, W.DemiBold, True))
                    status = tr("timers.finished") if done else (
                        "" if timer["running"] else tr("timers.paused")
                    )
                    ui.text(QRectF(r.left() + 60, r.top() + 32, 220, 18), timer["label"] + status,
                            font(8), T.text2)
                    bx = r.right() - 20
                    ui.icon_button(QPointF(bx, r.center().y()), G["delete"],
                                   lambda timer=timer: timers.remove_timer(timer), 12, T.critical)
                    ui.icon_button(QPointF(bx - 32, r.center().y()), G["refresh"],
                                   lambda timer=timer: timers.reset_timer(timer), 12)
                    ui.button(QRectF(bx - 96, r.center().y() - 13, 46, 26),
                              tr("timers.add_one_minute"), lambda timer=timer: timers.add_time(timer, 60))
                    ui.icon_button(QPointF(bx - 118, r.center().y()),
                                   G["pause"] if timer["running"] else G["play"],
                                   lambda timer=timer: timers.toggle_timer(timer), 13, T.text)
                y += 64
            return y - y0
        ui.scroll("timers", lr, draw)

    def _pomo(self, ui, body):
        isl = self.isl
        timers = isl.timers
        pomo = timers.pomo
        center = QPointF(body.left() + 84, body.top() + 104)
        remaining = timers.pomo_remaining()
        color = T.accent if pomo["phase"] == "work" else T.success
        ui.ring(center, 74, 1 - remaining / max(1, timers.phase_len()), color, 6)
        ui.text(QRectF(center.x() - 70, center.y() - 26, 140, 40), fmt_dur(remaining),
                font(22, W.DemiBold, True), T.text, CENTER)
        phase = {
            "work": tr("timers.pomodoro.work"),
            "short": tr("timers.pomodoro.short_break"),
            "long": tr("timers.pomodoro.long_break"),
        }[pomo["phase"]]
        ui.text(QRectF(center.x() - 70, center.y() + 12, 140, 18), phase,
                font(8.5, W.Medium), color, CENTER)
        every = timers.pomo_cfg["every"]
        done_in_cycle = pomo["cycles"] % every
        for index in range(every):
            ui.p.setPen(color if index < done_in_cycle else T.track)
            ui.p.setBrush(color if index < done_in_cycle else T.layer)
            ui.p.drawEllipse(QPointF(center.x() + (index - (every - 1) / 2) * 12,
                                     center.y() + 40), 3.5, 3.5)
        by = body.top() + 196
        ui.button(QRectF(body.left() + 4, by, 104, 32),
                  tr("common.pause") if pomo["running"] else tr("common.start"),
                  timers.pomo_toggle, G["pause"] if pomo["running"] else G["play"], accent=True)
        ui.icon_button(QPointF(body.left() + 128, by + 16), G["right"], timers.pomo_skip, 13, size=32)
        ui.icon_button(QPointF(body.left() + 162, by + 16), G["refresh"], timers.pomo_reset, 13, size=32)
        ui.text(QRectF(body.left(), by + 40, 200, 18),
                tr("timers.pomodoro.session_summary", count=pomo["cycles"], every=every),
                font(7.5), T.text3, CENTER)

        rx = body.left() + 206
        rw = body.right() - rx
        r = QRectF(rx, body.top(), rw, 64)
        ui.card(r)
        ui.glyph(QPointF(r.left() + 20, r.top() + 22), G["focus"], 15,
                 T.accent if timers.focus else T.text2)
        ui.text(QRectF(r.left() + 38, r.top() + 10, rw - 100, 18), tr("timers.pomodoro.focus_mode"),
                font(9.5, W.DemiBold))
        ui.wrap(QRectF(r.left() + 38, r.top() + 29, rw - 100, 30),
                tr("timers.pomodoro.focus_hint"), font(7.5), T.text2, lines=2)
        ui.toggle(QPointF(r.right() - 32, r.top() + 22), timers.focus,
                  lambda: isl.set_focus(not timers.focus))
        y = body.top() + 74
        ui.field(QRectF(rx, y, rw, 30), "pomo_label",
                 pomo.get("label") or tr("timers.pomodoro.label_placeholder"),
                 on_submit=lambda text: pomo.update(label=text.strip() or tr("timers.pomodoro.default_label")) or True,
                 glyph=G["edit"])
        y += 40
        for key, label, low, high, step in (
            ("work", tr("timers.pomodoro.work_duration"), 5, 90, 5),
            ("short", tr("timers.pomodoro.short_break"), 1, 30, 1),
            ("long", tr("timers.pomodoro.long_break"), 5, 60, 5),
            ("every", tr("timers.pomodoro.long_break_every"), 2, 8, 1),
        ):
            value = timers.pomo_cfg[key]
            ui.text(QRectF(rx, y, rw - 120, 28), label, font(8.5), T.text2)
            ui.icon_button(QPointF(rx + rw - 100, y + 14), "\ue738",
                           lambda key=key, value=value, low=low, step=step:
                           timers.set_pomo_cfg(**{key: max(low, value - step)}), 10, size=24)
            suffix = "" if key == "every" else " " + tr("common.minutes_short")
            ui.text(QRectF(rx + rw - 86, y, 56, 28), f"{value}{suffix}",
                    font(9, W.DemiBold), T.text, CENTER)
            ui.icon_button(QPointF(rx + rw - 16, y + 14), G["add"],
                           lambda key=key, value=value, high=high, step=step:
                           timers.set_pomo_cfg(**{key: min(high, value + step)}), 10, size=24)
            y += 30
        ui.text(QRectF(rx, y + 2, rw - 60, 24), tr("timers.pomodoro.auto_next"),
                font(8.5), T.text2)
        ui.toggle(QPointF(rx + rw - 22, y + 14), timers.pomo_cfg["auto"],
                  lambda: timers.set_pomo_cfg(auto=not timers.pomo_cfg["auto"]))

    def _sw(self, ui, body):
        timers = self.isl.timers
        elapsed = timers.sw_elapsed()
        centiseconds = int((elapsed % 1) * 100)
        ui.text(QRectF(body.left(), body.top() + 6, body.width(), 56),
                fmt_dur(elapsed, elapsed >= 3600) + f".{centiseconds:02d}",
                font(30, W.Light, True), T.text, CENTER)
        bx = body.center().x()
        by = body.top() + 72
        ui.button(QRectF(bx - 160, by, 100, 32), tr("timers.stopwatch.lap"), timers.sw_lap,
                  G["flag"], enabled=timers.stopwatch["running"])
        ui.button(QRectF(bx - 50, by, 100, 32),
                  tr("common.pause") if timers.stopwatch["running"] else tr("common.start"),
                  timers.sw_toggle, G["pause"] if timers.stopwatch["running"] else G["play"],
                  accent=True)
        ui.button(QRectF(bx + 60, by, 100, 32), tr("timers.stopwatch.reset"), timers.sw_reset,
                  G["refresh"])
        laps = timers.stopwatch["laps"]
        lr = QRectF(body.left() - 8, by + 44, body.width() + 16, body.bottom() - by - 44)
        if not laps:
            ui.text(QRectF(lr.left(), lr.top() + 20, lr.width(), 18),
                    tr("timers.stopwatch.empty"), font(8.5), T.text3, CENTER)
            return
        splits = [laps[index] - (laps[index + 1] if index + 1 < len(laps) else 0)
                  for index in range(len(laps))]
        best, worst = min(splits), max(splits)

        def draw(y0):
            y = y0
            for index, (total, split) in enumerate(zip(laps, splits)):
                r = QRectF(lr.left() + 8, y, lr.width() - 22, 28)
                if index % 2 == 0:
                    ui.rect(r, T.layer, 4)
                color = T.success if split == best and len(laps) > 1 else (
                    T.critical if split == worst and len(laps) > 1 else T.text
                )
                ui.text(QRectF(r.left() + 12, r.top(), 100, 28),
                        tr("timers.stopwatch.lap_number", number=len(laps) - index),
                        font(8.5), T.text2)
                ui.text(QRectF(r.center().x() - 60, r.top(), 120, 28),
                        "+" + fmt_dur(split) + f".{int(split % 1 * 100):02d}",
                        font(9, W.DemiBold), color, CENTER)
                ui.text(QRectF(r.right() - 132, r.top(), 120, 28),
                        fmt_dur(total) + f".{int(total % 1 * 100):02d}", font(9), T.text2, RIGHT)
                y += 30
            return y - y0
        ui.scroll("laps", lr, draw)

    def _add_alarm(self, text):
        match = re.match(r"\s*(\d{1,2})\s*[:h]\s*(\d{2})?\s*(.*)$", text, re.I)
        if not match or int(match.group(1)) > 23:
            return False
        hhmm = f"{int(match.group(1)):02d}:{int(match.group(2) or 0):02d}"
        rest = match.group(3).strip()
        days = []
        low = rest.lower()
        for pattern, selected in (
            (r"\b(semaine|lun-ven|jours ouvrés|en semaine|weekdays?|mon-fri|business days)\b", [0, 1, 2, 3, 4]),
            (r"\b(week-?end)\b", [5, 6]),
            (r"\b(tous les jours|quotidien|chaque jour|every day|daily)\b", list(range(7))),
        ):
            found = re.search(pattern, low)
            if found:
                days = selected
                rest = (rest[:found.start()] + rest[found.end():]).strip()
        self.isl.timers.add_alarm(hhmm, rest or tr("timers.alarms.default_label"), days)
        return True

    def _alarms(self, ui, body):
        timers = self.isl.timers
        ui.field(QRectF(body.left(), body.top(), body.width(), 30), "alarm_add",
                 tr("timers.alarms.placeholder"), on_submit=self._add_alarm, glyph=G["alarm"])
        next_alarm = timers.next_alarm()
        if next_alarm:
            delta = (next_alarm[0] - dt.datetime.now()).total_seconds()
            ui.text(QRectF(body.left(), body.top() + 36, body.width(), 18),
                    tr("timers.alarms.next", delay=fmt_minutes(delta // 60),
                       label=next_alarm[1]["label"]), font(8), T.text2)
        lr = QRectF(body.left() - 8, body.top() + 58, body.width() + 16, body.height() - 58)
        alarms = sorted(timers.alarms.items, key=lambda alarm: alarm["time"])
        if not alarms:
            ui.empty(lr, G["alarm"], tr("timers.alarms.empty"))
            return

        short_days = [name.rstrip(".") for name in weekday_names("short")]

        def draw(y0):
            y = y0
            for alarm in alarms:
                r = QRectF(lr.left() + 8, y, lr.width() - 22, 52)
                if ui.visible(r):
                    enabled = alarm.get("enabled", True)
                    ui.card(r)
                    ui.text(QRectF(r.left() + 14, r.top() + 2, 100, 32), alarm["time"],
                            font(17, W.DemiBold, True), T.text if enabled else T.disabled)
                    days = alarm.get("days") or []
                    if not days:
                        description = tr("timers.alarms.once")
                    elif len(days) == 7:
                        description = tr("timers.alarms.every_day")
                    elif days == [0, 1, 2, 3, 4]:
                        description = tr("timers.alarms.weekdays")
                    elif days == [5, 6]:
                        description = tr("timers.alarms.weekend")
                    else:
                        description = " ".join(short_days[day] for day in days)
                    ui.text(QRectF(r.left() + 14, r.top() + 31, 220, 16),
                            f"{alarm['label']} · {description}", font(8), T.text2)
                    ui.toggle(QPointF(r.right() - 76, r.center().y()), enabled,
                              lambda alarm=alarm: timers.toggle_alarm(alarm))
                    ui.icon_button(QPointF(r.right() - 22, r.center().y()), G["delete"],
                                   lambda alarm=alarm: timers.alarms.remove(alarm), 12, T.critical)
                y += 58
            return y - y0
        ui.scroll("alarms", lr, draw)

    def _stats(self, ui, body):
        timers = self.isl.timers
        stats = timers.stats()
        cards = [
            (tr("timers.stats.today"), fmt_minutes(stats["today"]), G["focus"]),
            (tr("timers.stats.sessions"), str(stats["count_today"]), G["history"]),
            (tr("timers.stats.week"), fmt_minutes(stats["week"]), G["chart"]),
            (tr("timers.stats.streak"), tr("timers.stats.streak_days", count=stats["streak"]), G["flag"]),
        ]
        column_width = (body.width() - 18) / 4
        for index, (label, value, glyph) in enumerate(cards):
            r = QRectF(body.left() + index * (column_width + 6), body.top(), column_width, 56)
            ui.card(r)
            ui.glyph(QPointF(r.left() + 16, r.top() + 16), glyph, 11, T.accent)
            ui.text(QRectF(r.left() + 28, r.top() + 6, column_width - 30, 20), label,
                    font(7.5), T.text2)
            ui.text(QRectF(r.left() + 10, r.top() + 26, column_width - 14, 26), value,
                    font(12, W.DemiBold, True))
        chart = QRectF(body.left(), body.top() + 66, body.width(), 110)
        ui.card(chart)
        maximum = max(30.0, max(stats["per_day"].values()))
        bar_width = (chart.width() - 40) / 7
        for index, day in enumerate(stats["days"]):
            value = stats["per_day"][day]
            height = (chart.height() - 44) * value / maximum
            bx = chart.left() + 20 + index * bar_width + bar_width * 0.25
            color = T.accent if day == dt.date.today() else T.tint(T.accent, 140)
            if value > 0:
                ui.rect(QRectF(bx, chart.bottom() - 24 - height, bar_width * 0.5, height), color, 3)
            ui.text(QRectF(bx - 10, chart.bottom() - 22, bar_width * 0.5 + 20, 16),
                    format_day_name(day, "abbreviated").rstrip(".").capitalize(),
                    font(7), T.text3, CENTER)
            if value > 0:
                ui.text(QRectF(bx - 14, chart.bottom() - 40 - height, bar_width * 0.5 + 28, 14),
                        tr("timers.stats.minutes_value", value=f"{value:.0f}"), font(7), T.text2, CENTER)
        y = chart.bottom() + 10
        ui.text(QRectF(body.left(), y, 220, 18), tr("timers.stats.history"), font(8.5, W.DemiBold))
        lr = QRectF(body.left() - 8, y + 22, body.width() + 16, body.bottom() - y - 22)
        sessions = timers.recent_sessions(30)
        if not sessions:
            ui.text(QRectF(lr.left() + 8, lr.top(), lr.width(), 18),
                    tr("timers.stats.history_hint"), font(8), T.text3)
            return

        def draw(y0):
            yy = y0
            for session in sessions:
                started = dt.datetime.fromtimestamp(session["start"])
                ui.glyph(QPointF(lr.left() + 18, yy + 11),
                         G["focus"] if session["kind"] == "pomodoro" else G["timer"], 10, T.accent)
                ui.text(QRectF(lr.left() + 32, yy, 220, 22),
                        session.get("label") or session["kind"], font(8.5))
                ui.text(QRectF(lr.right() - 230, yy, 216, 22),
                        f"{format_date(started, 'short')} {format_time(started)} · "
                        f"{fmt_minutes(session['duration'] // 60)}", font(8), T.text2, RIGHT)
                yy += 24
            return yy - y0
        ui.scroll("sessions", lr, draw)
