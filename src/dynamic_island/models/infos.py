"""Information-widget metadata, defaults and localized quotes."""
import datetime as dt

from dynamic_island.core.localization import get_value

WIDGETS = (
    ("weather", "infos.widgets.weather"),
    ("clocks", "infos.widgets.clocks"),
    ("stats", "infos.widgets.stats"),
    ("quote", "infos.widgets.quote"),
    ("news", "infos.widgets.news"),
    ("stocks", "infos.widgets.stocks"),
    ("photo", "infos.widgets.photo"),
    ("calendar", "infos.widgets.calendar"),
)
DEFAULT_WIDGETS = ["weather", "clocks", "stats", "quote", "news", "stocks", "photo", "calendar"]
DEFAULT_CLOCKS = [("Paris", "Europe/Paris"), ("New York", "America/New_York"), ("Tokyo", "Asia/Tokyo")]
DEFAULT_STOCKS = ["AAPL", "MSFT", "BTC-USD", "EURUSD=X"]
DEFAULT_FEEDS = ["https://www.france24.com/fr/rss", "https://www.lemonde.fr/rss/une.xml"]

WMO_KEYS = {
    0: "weather.wmo.clear",
    1: "weather.wmo.mostly_clear",
    2: "weather.wmo.partly_cloudy",
    3: "weather.wmo.overcast",
    45: "weather.wmo.fog",
    48: "weather.wmo.rime_fog",
    51: "weather.wmo.light_drizzle",
    53: "weather.wmo.drizzle",
    55: "weather.wmo.heavy_drizzle",
    61: "weather.wmo.light_rain",
    63: "weather.wmo.rain",
    65: "weather.wmo.heavy_rain",
    66: "weather.wmo.freezing_rain",
    67: "weather.wmo.freezing_rain",
    71: "weather.wmo.light_snow",
    73: "weather.wmo.snow",
    75: "weather.wmo.heavy_snow",
    77: "weather.wmo.snow_grains",
    80: "weather.wmo.showers",
    81: "weather.wmo.showers",
    82: "weather.wmo.heavy_showers",
    85: "weather.wmo.snow_showers",
    86: "weather.wmo.snow_showers",
    95: "weather.wmo.thunderstorm",
    96: "weather.wmo.thunderstorm_hail",
    99: "weather.wmo.thunderstorm_hail",
}


def quote_of_day():
    """Return the quote for today in the active language."""
    quotes = get_value("content.quotes", [])
    if not quotes:
        return "", ""
    index = dt.date.today().toordinal() % len(quotes)
    item = quotes[index]
    if isinstance(item, (list, tuple)) and len(item) >= 2:
        return item[0], item[1]
    return str(item), ""
