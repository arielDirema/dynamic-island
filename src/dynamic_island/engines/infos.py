"""Information widgets: weather (Open-Meteo), world clock, news (RSS),
stocks (Yahoo Finance), favorite photos and quote of the day."""
import datetime as dt
import json
import os
import random
import threading
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QImage

from dynamic_island.core.config.settings import settings
from dynamic_island.core.localization import translate as tr
from dynamic_island.models.infos import DEFAULT_CLOCKS, DEFAULT_FEEDS, DEFAULT_STOCKS, DEFAULT_WIDGETS

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) DynamicIsland/1.0"}


def get_json(url, timeout=12):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


class Infos(QObject):
    updated = Signal()
    photo_ready = Signal(object)

    def __init__(self):
        super().__init__()
        self.weather = None
        self.weather_err = None
        self.news = []
        self.stocks = {}
        self.photo = None
        self.photo_path = None
        self._photos = []
        self._wake = threading.Event()
        threading.Thread(target=self._loop, daemon=True).start()
        threading.Thread(target=self._photo_loop, daemon=True).start()

    @property
    def widgets(self):
        return settings.get("widgets", DEFAULT_WIDGETS)

    def set_widgets(self, lst):
        settings.set("widgets", lst)

    @property
    def clocks(self):
        return [tuple(c) for c in settings.get("clocks", DEFAULT_CLOCKS)]

    @property
    def symbols(self):
        return settings.get("stocks", DEFAULT_STOCKS)

    @property
    def feeds(self):
        return settings.get("feeds", DEFAULT_FEEDS)

    @property
    def location(self):
        return settings.get("location")

    def set_city(self, name):
        def work():
            try:
                q = urllib.parse.quote(name)
                d = get_json(f"https://geocoding-api.open-meteo.com/v1/search?name={q}&count=1&language=fr")
                r = d["results"][0]
                settings.set("location", {"name": r["name"], "lat": r["latitude"], "lon": r["longitude"],
                                          "country": r.get("country", "")})
                self.refresh()
            except Exception:
                self.weather_err = f"Ville introuvable : {name}"
                self.updated.emit()
        threading.Thread(target=work, daemon=True).start()

    def set_clocks_text(self, text):
        """“Paris, New York, Tokyo” or “Lomé=Africa/Lome” → list of time zones."""
        out = []
        for part in text.split(","):
            part = part.strip()
            if not part:
                continue
            if "=" in part:
                label, tz = (x.strip() for x in part.split("=", 1))
            else:
                label, tz = part, self._tz_for(part)
            try:
                ZoneInfo(tz)
                out.append((label, tz))
            except Exception:
                continue
        if out:
            settings.set("clocks", out)
        return bool(out)

    @staticmethod
    def _tz_for(city):
        import zoneinfo
        key = city.lower().replace(" ", "")
        for tz in zoneinfo.available_timezones():
            if tz.lower().split("/")[-1] == key:
                return tz
        try:
            d = get_json("https://geocoding-api.open-meteo.com/v1/search?name="
                         + urllib.parse.quote(city) + "&count=1")
            return d["results"][0]["timezone"]
        except Exception:
            return "UTC"

    def set_symbols_text(self, text):
        syms = [s.strip().upper() for s in text.replace(";", "").split(",") if s.strip()]
        if syms:
            settings.set("stocks", syms)
            self.refresh()

    def add_feed(self, url):
        if url.startswith("http"):
            settings.set("feeds", self.feeds + [url])
            self.refresh()

    def set_photo_dir(self, path):
        settings.set("photo_dir", path)
        self._photos = []

    def refresh(self):
        self._wake.set()

    def _loop(self):
        while True:
            self._fetch_weather()
            self._fetch_stocks()
            self._fetch_news()
            self.updated.emit()
            self._wake.wait(15 * 60)
            self._wake.clear()

    def _fetch_weather(self):
        try:
            loc = self.location
            if not loc:
                d = get_json("https://ipwho.is/")
                loc = {"name": d.get("city", ""), "lat": d["latitude"], "lon": d["longitude"],
                       "country": d.get("country", ""), "auto": True}
                settings.set("location", loc)
            url = ("https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
                   "&current=temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,"
                   "wind_speed_10m,precipitation,is_day"
                   "&hourly=temperature_2m,precipitation_probability,weather_code,is_day"
                   "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,"
                   "sunrise,sunset&timezone=auto&forecast_days=6").format(**loc)
            d = get_json(url)
            now_i = 0
            times = d["hourly"]["time"]
            nowstr = dt.datetime.now().strftime("%Y-%m-%dT%H:00")
            if nowstr in times:
                now_i = times.index(nowstr)
            hourly = [{"t": times[i][11:16], "temp": d["hourly"]["temperature_2m"][i],
                       "rain": d["hourly"]["precipitation_probability"][i],
                       "code": d["hourly"]["weather_code"][i], "day": d["hourly"]["is_day"][i] == 1} for i in range(now_i, min(len(times), now_i + 12))]
            daily = []
            for i, day in enumerate(d["daily"]["time"]):
                daily.append({"date": dt.date.fromisoformat(day), "code": d["daily"]["weather_code"][i],
                              "max": d["daily"]["temperature_2m_max"][i], "min": d["daily"]["temperature_2m_min"][i],
                              "rain": d["daily"]["precipitation_probability_max"][i]})
            c = d["current"]
            self.weather = {"city": loc["name"], "temp": c["temperature_2m"], "feels": c["apparent_temperature"],
                            "hum": c["relative_humidity_2m"], "code": c["weather_code"], "is_day": c.get("is_day", 1) == 1, "wind": c["wind_speed_10m"],
                            "rain_now": hourly[0]["rain"] if hourly else None, "hourly": hourly, "daily": daily,
                            "time": time.time()}
            self.weather_err = None
        except Exception as e:
            self.weather_err = tr("infos.weather.unavailable", error=type(e).__name__)

    def _fetch_stocks(self):
        out = {}
        for s in self.symbols[:8]:
            try:
                d = get_json("https://query1.finance.yahoo.com/v8/finance/chart/"
                             + urllib.parse.quote(s) + "?range=5d&interval=1h")
                r = d["chart"]["result"][0]
                m = r["meta"]
                price = m.get("regularMarketPrice")
                prev = m.get("chartPreviousClose") or m.get("previousClose")
                closes = [c for c in (r.get("indicators", {}).get("quote", [{}])[0].get("close") or []) if c]
                out[s] = {"price": price, "change": (price - prev) / prev * 100 if price and prev else 0,
                          "cur": m.get("currency", ""), "name": m.get("shortName") or s, "spark": closes[-40:]}
            except Exception:
                continue
        if out:
            self.stocks = out

    def _fetch_news(self):
        items = []
        for url in self.feeds[:5]:
            try:
                req = urllib.request.Request(url, headers=UA)
                root = ET.fromstring(urllib.request.urlopen(req, timeout=12).read())
                src = (root.findtext("channel/title") or urllib.parse.urlparse(url).netloc).strip()
                for it in root.iter("item"):
                    title = (it.findtext("title") or "").strip()
                    link = (it.findtext("link") or "").strip()
                    if title:
                        items.append({"title": title, "link": link, "source": src[:30]})
                    if len([i for i in items if i["source"] == src[:30]]) >= 8:
                        break
            except Exception:
                continue
        if items:
            # alternate sources
            by = {}
            for i in items:
                by.setdefault(i["source"], []).append(i)
            mixed = []
            while any(by.values()):
                for k in list(by):
                    if by[k]:
                        mixed.append(by[k].pop(0))
            self.news = mixed[:16]

    def _photo_loop(self):
        while True:
            folder = settings.get("photo_dir") or os.path.join(os.path.expanduser("~"), "Pictures")
            if not self._photos:
                found = []
                for root, _dirs, files in os.walk(folder):
                    for f in files:
                        if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".bmp")):
                            found.append(os.path.join(root, f))
                    if len(found) > 2000:
                        break
                self._photos = found
            if self._photos:
                path = random.choice(self._photos)
                img = QImage(path)
                if not img.isNull():
                    img = img.scaled(480, 300, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                     Qt.TransformationMode.SmoothTransformation)
                    self.photo_path = path
                    self.photo_ready.emit(img)
            time.sleep(20)

    def world_times(self):
        out = []
        local = dt.datetime.now().astimezone()
        for label, tz in self.clocks:
            try:
                t = dt.datetime.now(ZoneInfo(tz))
            except Exception:
                continue
            diff = (t.utcoffset() - local.utcoffset()).total_seconds() / 3600
            day = "" if t.date() == local.date() else (
                tr("infos.weather.tomorrow_suffix") if t.date() > local.date()
                else tr("infos.weather.yesterday_suffix"))
            out.append((label, t, diff, day))
        return out
