"""Info tab: customizable widgets (weather, world clock, statistics, quote,
news, stocks, photo, calendar)."""
import datetime as dt
import os
import time

import psutil
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QPainterPath, QPen, QPixmap

from dynamic_island.core.config.settings import settings
from dynamic_island.core.localization import (
    format_date,
    format_day_name,
    format_number,
    format_time,
    translate as tr,
)
from dynamic_island.core.utilities.formatting import fmt_minutes
from dynamic_island.models.infos import WIDGETS, WMO_KEYS, quote_of_day
from dynamic_island.ui.components.drawing import CENTER, RIGHT
from dynamic_island.ui.resources import icons
from dynamic_island.ui.themes import G, T, W, font

CONTENT_H = 372


class InfosTab:
    key, label_key, glyph = "infos", "tabs.infos", G["info"]

    def __init__(self, isl):
        self.isl = isl
        self.editing = False
        self.photo = None
        isl.infos.photo_ready.connect(self._photo)

    def _photo(self, image):
        self.photo = QPixmap.fromImage(image)

    def height(self):
        return CONTENT_H

    def paint(self, ui, cr):
        isl = self.isl
        x0, x1 = cr.left() + 16, cr.right() - 16
        ui.text(QRectF(x0, cr.top(), 320, 28),
                tr("infos.customize_title") if self.editing else tr("infos.widgets_title"),
                font(10.5, W.DemiBold))
        ui.button(QRectF(x1 - 96, cr.top() + 1, 96, 26),
                  tr("common.done") if self.editing else tr("common.edit"),
                  lambda: setattr(self, "editing", not self.editing),
                  G["check"] if self.editing else G["settings"], accent=self.editing)
        ui.icon_button(QPointF(x1 - 116, cr.top() + 14), G["refresh"], isl.infos.refresh, 12)
        body = QRectF(cr.left() + 8, cr.top() + 34, cr.width() - 16, cr.height() - 40)
        if self.editing:
            ui.scroll("infos_edit", body, lambda y: self._edit(ui, body, y))
        else:
            ui.scroll("infos", body, lambda y: self._widgets(ui, body, y))

    def _widgets(self, ui, body, y0):
        y = y0
        x0, width = body.left() + 8, body.width() - 22
        for key in self.isl.infos.widgets:
            render = getattr(self, "w_" + key, None)
            if render:
                height = render(ui, QRectF(x0, y, width, 0))
                y += height + 8
        return y - y0

    def _card(self, ui, r, title, glyph):
        if ui.visible(r):
            ui.card(r)
            ui.glyph(QPointF(r.left() + 16, r.top() + 15), glyph, 11, T.text2)
            ui.text(QRectF(r.left() + 30, r.top() + 5, r.width() - 40, 20), title,
                    font(8, W.DemiBold), T.text2)

    def w_weather(self, ui, r):
        infos = self.isl.infos
        weather = infos.weather
        r = QRectF(r.left(), r.top(), r.width(), 214 if weather else 60)
        title = tr("infos.widgets.weather")
        if weather:
            title += f" · {weather['city']}"
        self._card(ui, r, title, G["cloud"])
        if not ui.visible(r):
            return r.height()
        if not weather:
            ui.text(QRectF(r.left() + 16, r.top() + 28, r.width() - 32, 20),
                    infos.weather_err or tr("common.loading"), font(8.5), T.text3)
            return r.height()
        label = tr(WMO_KEYS.get(weather["code"], "weather.wmo.unknown"))
        icons.weather(ui.p, QRectF(r.left() + 10, r.top() + 24, 58, 58),
                      weather["code"], weather.get("is_day", True))
        ui.text(QRectF(r.left() + 72, r.top() + 24, 120, 40),
                f"{weather['temp']:.0f}°", font(24, W.DemiBold, True))
        ui.text(QRectF(r.left() + 74, r.top() + 62, 200, 16), label, font(8.5), T.text2)
        details = [
            (tr("infos.weather.feels_like"), f"{weather['feels']:.0f}°"),
            (tr("infos.weather.humidity"), tr("units.percent", value=weather["hum"])),
            (tr("infos.weather.wind"), tr("infos.weather.wind_value", value=f"{weather['wind']:.0f}")),
            (tr("weather.wmo.rain"), tr("units.percent", value=weather["rain_now"]
                                        if weather["rain_now"] is not None else "–")),
        ]
        for index, (key, value) in enumerate(details):
            cx = r.left() + 210 + (index % 2) * 130
            cy = r.top() + 30 + (index // 2) * 24
            ui.text(QRectF(cx, cy, 70, 20), key, font(8), T.text3)
            ui.text(QRectF(cx + 60, cy, 64, 20), value, font(8.5, W.DemiBold), T.text, RIGHT)
        hy = r.top() + 86
        hour_width = (r.width() - 24) / 8
        for index, hour in enumerate(weather["hourly"][:8]):
            cx = r.left() + 12 + index * hour_width
            ui.text(QRectF(cx, hy, hour_width, 14),
                    tr("infos.weather.now") if index == 0 else hour["t"],
                    font(7), T.text3, CENTER)
            icons.weather(ui.p, QRectF(cx, hy + 12, hour_width, 22), hour["code"],
                          hour.get("day", True))
            ui.text(QRectF(cx, hy + 33, hour_width, 14), f"{hour['temp']:.0f}°",
                    font(8, W.DemiBold), T.text, CENTER)
            ui.text(QRectF(cx, hy + 46, hour_width, 12),
                    tr("units.percent", value=hour["rain"]), font(6.5), T.accent, CENTER)
        dy = r.top() + 152
        ui.rect(QRectF(r.left() + 12, dy - 4, r.width() - 24, 1), T.stroke, 0)
        day_width = (r.width() - 24) / 5
        for index, day in enumerate(weather["daily"][1:6]):
            cx = r.left() + 12 + index * day_width
            ui.text(QRectF(cx, dy + 2, day_width, 16),
                    format_day_name(day["date"], "abbreviated").rstrip(".").capitalize(),
                    font(7.5, W.DemiBold), T.text2, CENTER)
            icons.weather(ui.p, QRectF(cx, dy + 17, 26, 24), day["code"], True)
            ui.text(QRectF(cx + 24, dy + 18, day_width - 24, 22),
                    f"{day['max']:.0f}° / {day['min']:.0f}°", font(8, W.DemiBold), T.text)
            ui.text(QRectF(cx, dy + 40, day_width, 14),
                    tr("infos.weather.rain_chance", value=day["rain"]),
                    font(6.5), T.accent, CENTER)
        return r.height()

    def w_clocks(self, ui, r):
        times = self.isl.infos.world_times()
        r = QRectF(r.left(), r.top(), r.width(), 86)
        self._card(ui, r, tr("infos.widgets.clocks"), G["globe"])
        if not ui.visible(r):
            return r.height()
        count = max(1, len(times))
        column_width = (r.width() - 24) / count
        for index, (label, value, difference, day_suffix) in enumerate(times):
            cx = r.left() + 12 + index * column_width
            ui.text(QRectF(cx, r.top() + 26, column_width - 6, 16), label,
                    font(8, W.Medium), T.text2)
            ui.text(QRectF(cx, r.top() + 40, column_width - 6, 26), format_time(value),
                    font(15, W.DemiBold, True))
            sign = "+" if difference >= 0 else "−"
            offset = tr("infos.weather.same_time") if difference == 0 else \
                tr("infos.weather.time_offset", sign=sign, hours=f"{abs(difference):g}")
            ui.text(QRectF(cx, r.top() + 64, column_width - 6, 16), offset + day_suffix,
                    font(7), T.text3)
        return r.height()

    def w_stats(self, ui, r):
        isl = self.isl
        stats = isl.timers.stats()
        todo, done = isl.tasks.today_counts()
        today0 = time.mktime(dt.date.today().timetuple())
        clips = sum(1 for item in isl.clip.items if item["time"] >= today0)
        events = len(isl.agenda.day(dt.date.today()))
        uptime = time.time() - psutil.boot_time()
        items = [
            (tr("infos.stats.focus"), fmt_minutes(stats["today"]), G["focus"]),
            (tr("infos.stats.tasks_done"), tr("infos.stats.tasks_done_value",
                                              done=done, week=isl.tasks.done_this_week()), G["check"]),
            (tr("infos.stats.events"), str(events), G["calendar"]),
            (tr("infos.stats.copies"), str(clips), G["clip"]),
            (tr("infos.stats.uptime"), fmt_minutes(uptime // 60), G["power"]),
            (tr("infos.stats.focus_streak"), tr("timers.stats.streak_days", count=stats["streak"]), G["flag"]),
        ]
        r = QRectF(r.left(), r.top(), r.width(), 124)
        self._card(ui, r, tr("infos.stats.title"), G["chart"])
        if not ui.visible(r):
            return r.height()
        column_width = (r.width() - 24) / 3
        for index, (key, value, glyph) in enumerate(items):
            cx = r.left() + 12 + (index % 3) * column_width
            cy = r.top() + 30 + (index // 3) * 46
            ui.glyph(QPointF(cx + 10, cy + 12), glyph, 12, T.accent)
            ui.text(QRectF(cx + 26, cy, column_width - 28, 16), key, font(7.5), T.text3)
            ui.text(QRectF(cx + 26, cy + 15, column_width - 28, 22), value,
                    font(10, W.DemiBold, True))
        return r.height()

    def w_quote(self, ui, r):
        quote, author = quote_of_day()
        r = QRectF(r.left(), r.top(), r.width(), 92)
        self._card(ui, r, tr("infos.widgets.quote"), G["quote"])
        if ui.visible(r):
            ui.wrap(QRectF(r.left() + 16, r.top() + 28, r.width() - 32, 40),
                    tr("infos.quote_text", quote=quote), font(9.5), T.text, 2)
            ui.text(QRectF(r.left() + 16, r.top() + 68, r.width() - 32, 16),
                    "— " + author, font(8), T.text2, RIGHT)
        return r.height()

    def w_news(self, ui, r):
        news = self.isl.infos.news[:6]
        r = QRectF(r.left(), r.top(), r.width(), 34 + max(1, len(news)) * 30)
        self._card(ui, r, tr("infos.widgets.news"), G["news"])
        if not news:
            ui.text(QRectF(r.left() + 16, r.top() + 30, r.width() - 32, 20),
                    tr("infos.news_loading"), font(8.5), T.text3)
            return r.height()
        y = r.top() + 30
        for item in news:
            rr = QRectF(r.left() + 6, y, r.width() - 12, 28)
            if ui.row_hover(rr):
                ui.rect(rr, T.hover, 4)
            ui.text(QRectF(rr.left() + 10, y, 90, 28), item["source"], font(7, W.DemiBold), T.accent)
            ui.text(QRectF(rr.left() + 104, y, rr.width() - 112, 28), item["title"], font(8.5))
            ui.row_hit(rr, lambda url=item["link"]: self.isl.open_url(url))
            y += 30
        return r.height()

    def w_stocks(self, ui, r):
        infos = self.isl.infos
        symbols = [symbol for symbol in infos.symbols if symbol in infos.stocks]
        r = QRectF(r.left(), r.top(), r.width(), 34 + max(1, len(symbols)) * 30)
        self._card(ui, r, tr("infos.widgets.stocks"), G["chart"])
        if not symbols:
            ui.text(QRectF(r.left() + 16, r.top() + 30, r.width() - 32, 20),
                    tr("infos.stocks_loading"), font(8.5), T.text3)
            return r.height()
        y = r.top() + 30
        painter = ui.p
        for symbol in symbols:
            data = infos.stocks[symbol]
            up = data["change"] >= 0
            color = T.success if up else T.critical
            ui.text(QRectF(r.left() + 16, y, 80, 28), symbol, font(8.5, W.DemiBold))
            ui.text(QRectF(r.left() + 96, y, 140, 28), data["name"], font(7.5), T.text3)
            spark = data.get("spark") or []
            if len(spark) > 2 and ui.visible(QRectF(r.left(), y, r.width(), 28)):
                sx, sw, sy, sh = r.left() + 240, 90, y + 5, 18
                low, high = min(spark), max(spark)
                path = QPainterPath()
                for index, value in enumerate(spark):
                    px = sx + sw * index / (len(spark) - 1)
                    py = sy + sh - (sh * (value - low) / (high - low) if high > low else sh / 2)
                    path.moveTo(px, py) if index == 0 else path.lineTo(px, py)
                painter.setPen(QPen(color, 1.4))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPath(path)
            price = data["price"]
            price_text = format_number(price, format="#,##0.00") if price else "–"
            ui.text(QRectF(r.right() - 170, y, 100, 28), f"{price_text} {data['cur']}",
                    font(8.5, W.DemiBold), T.text, RIGHT)
            change = ("+" if up else "") + format_number(data["change"], format="#,##0.00")
            ui.text(QRectF(r.right() - 64, y, 50, 28), tr("units.percent", value=change),
                    font(8, W.DemiBold), color, RIGHT)
            y += 30
        return r.height()

    def w_photo(self, ui, r):
        r = QRectF(r.left(), r.top(), r.width(), 170)
        self._card(ui, r, tr("infos.widgets.photo"), G["photo"])
        if not ui.visible(r):
            return r.height()
        image_rect = QRectF(r.left() + 8, r.top() + 28, r.width() - 16, r.height() - 36)
        if self.photo:
            clip = QPainterPath()
            clip.addRoundedRect(image_rect, 4, 4)
            ui.p.save()
            ui.p.setClipPath(clip, Qt.ClipOperation.IntersectClip)
            pixmap = self.photo
            sx = max(0, (pixmap.width() - image_rect.width()) / 2)
            sy = max(0, (pixmap.height() - image_rect.height()) / 2)
            ui.p.drawPixmap(image_rect, pixmap, QRectF(sx, sy, min(pixmap.width(), image_rect.width()),
                                                       min(pixmap.height(), image_rect.height())))
            ui.p.restore()
            path = self.isl.infos.photo_path
            if path:
                ui.row_hit(image_rect, lambda: os.startfile(path))
        else:
            ui.text(image_rect, tr("infos.no_photo"), font(8.5), T.text3, CENTER)
        return r.height()

    def w_calendar(self, ui, r):
        r = QRectF(r.left(), r.top(), r.width(), 196)
        self._card(ui, r, tr("infos.widgets.calendar"), G["calendar"])
        if ui.visible(r):
            agenda = self.isl.tabs["agenda"]
            today = dt.date.today()
            ui.text(QRectF(r.left() + 16, r.top() + 26, 240, 18),
                    format_date(today, "MMMM yyyy").capitalize(), font(9, W.DemiBold))
            agenda.month_grid(ui, QRectF(r.left() + 12, r.top() + 46, r.width() - 24, 144),
                              today.replace(day=1), None,
                              lambda day: (agenda._open_day(day), self.isl.set_tab("agenda")),
                              mini=True)
        return r.height()

    def _edit(self, ui, body, y0):
        isl = self.isl
        infos = isl.infos
        x0, x1 = body.left() + 8, body.right() - 14
        y = y0
        ui.text(QRectF(x0, y, 320, 18), tr("infos.edit.widgets_order"), font(8.5, W.DemiBold))
        y += 24
        enabled = list(infos.widgets)
        order = enabled + [key for key, _ in WIDGETS if key not in enabled]
        names = {key: label_key for key, label_key in WIDGETS}
        for key in order:
            r = QRectF(x0, y, x1 - x0, 32)
            ui.card(r)
            on = key in enabled
            ui.text(QRectF(r.left() + 14, r.top(), 200, 32), tr(names[key]),
                    font(9), T.text if on else T.text3)
            if on:
                index = enabled.index(key)
                ui.icon_button(QPointF(r.right() - 120, r.center().y()), G["up"],
                               lambda index=index: self._move(index, -1), 10, size=24)
                ui.icon_button(QPointF(r.right() - 94, r.center().y()), G["down"],
                               lambda index=index: self._move(index, 1), 10, size=24)
            ui.toggle(QPointF(r.right() - 34, r.center().y()), on,
                      lambda key=key: self._toggle(key))
            y += 36
        y += 8
        location = infos.location or {}
        fields = (
            ("cfg_city", tr("infos.edit.city", city=location.get("name") or tr("common.auto")),
             tr("infos.edit.city_placeholder"), lambda text: infos.set_city(text) or True),
            ("cfg_clocks", tr("infos.edit.clocks", cities=", ".join(city[0] for city in infos.clocks)),
             tr("infos.edit.clocks_placeholder"), lambda text: infos.set_clocks_text(text)),
            ("cfg_stocks", tr("infos.edit.stocks", symbols=", ".join(infos.symbols)),
             tr("infos.edit.stocks_placeholder"), lambda text: infos.set_symbols_text(text) or True),
            ("cfg_feed", tr("infos.edit.feeds", count=len(infos.feeds)),
             tr("infos.edit.feeds_placeholder"), lambda text: infos.add_feed(text.strip()) or True),
        )
        for name, label, placeholder, submit in fields:
            ui.text(QRectF(x0, y, x1 - x0, 18), label, font(8, W.Medium), T.text2)
            ui.field(QRectF(x0, y + 20, x1 - x0, 30), name, placeholder, on_submit=submit)
            y += 58
        ui.text(QRectF(x0, y, x1 - x0 - 150, 26),
                tr("infos.edit.photos", folder=settings.get("photo_dir") or tr("infos.photos_default")),
                font(8, W.Medium), T.text2)
        ui.button(QRectF(x1 - 140, y, 140, 26), tr("infos.choose_folder"),
                  self._pick_photos, G["folder"])
        y += 34
        return y - y0

    def _move(self, index, delta):
        widgets = list(self.isl.infos.widgets)
        target = index + delta
        if 0 <= target < len(widgets):
            widgets[index], widgets[target] = widgets[target], widgets[index]
            self.isl.infos.set_widgets(widgets)

    def _toggle(self, key):
        widgets = list(self.isl.infos.widgets)
        if key in widgets:
            widgets.remove(key)
        else:
            widgets.append(key)
        self.isl.infos.set_widgets(widgets)

    def _pick_photos(self):
        from PySide6.QtWidgets import QFileDialog

        self.isl.close_island(restore_focus=False)
        directory = QFileDialog.getExistingDirectory(
            None, tr("infos.photos_dialog"), os.path.expanduser("~")
        )
        if directory:
            self.isl.infos.set_photo_dir(directory)
