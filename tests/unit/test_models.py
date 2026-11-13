"""Localized domain metadata shared between engines and UI."""
from dynamic_island.models import clipboard, hotspot, infos, tasks


def test_clipboard_catalog():
    assert clipboard.CATEGORIES[0] == ("all", "clipboard.categories.all")
    assert dict(clipboard.CATEGORIES)["pinned"] == "clipboard.categories.pinned"
    assert clipboard.KIND_LABEL_KEYS["email"] == "clipboard.kinds.email"
    assert clipboard.TAG_KEYS["numéro"] == "clipboard.tags.phone"


def test_task_and_hotspot_labels():
    assert tasks.PRIORITY_KEYS == {
        0: "",
        1: "tasks.priority.low",
        2: "tasks.priority.medium",
        3: "tasks.priority.high",
    }
    assert hotspot.BAND_KEYS[0] == "hotspot.bands.automatic"
    assert hotspot.wifi_qr_text("My network", "secret;1") == (
        r"WIFI:T:WPA;S:My network;P:secret\;1;;"
    )


def test_info_catalog_and_quote(language):
    language("en")
    assert ("weather", "infos.widgets.weather") in infos.WIDGETS
    assert infos.WMO_KEYS[0] == "weather.wmo.clear"
    quote, author = infos.quote_of_day()
    assert isinstance(quote, str) and quote
    assert isinstance(author, str) and author
    quotes = infos.get_value("content.quotes")
    assert [quote, author] in quotes
