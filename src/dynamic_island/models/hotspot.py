"""Mobile hotspot metadata shared with the interface."""
import re

BAND_KEYS = {
    0: "hotspot.bands.automatic",
    1: "hotspot.bands.2_4ghz",
    2: "hotspot.bands.5ghz",
}


def wifi_qr_text(ssid, password):
    escaped = lambda value: re.sub(r"([\\;,:\"])", r"\\\1", value)
    return f"WIFI:T:WPA;S:{escaped(ssid)};P:{escaped(password)};;"
