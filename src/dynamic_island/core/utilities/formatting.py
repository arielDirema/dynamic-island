"""Shared formatting helpers for sizes, durations and relative times."""
import time

from dynamic_island.core.localization import translate

_SIZE_UNITS = ("byte", "kilobyte", "megabyte", "gigabyte", "terabyte")


def human(n):
    """Format a byte count with localized unit names."""
    value = float(n or 0)
    for index, unit in enumerate(_SIZE_UNITS):
        if value < 1024 or unit == "terabyte":
            if unit == "byte":
                rendered = f"{value:.0f}"
            else:
                rendered = f"{value:.1f}"
                if rendered.endswith(".0"):
                    rendered = rendered[:-2]
            return translate(f"units.{unit}", value=rendered)
        value /= 1024


def fmt_dur(sec, show_hours=False):
    sec = max(0, int(round(sec)))
    h, m, s = sec // 3600, sec % 3600 // 60, sec % 60
    if h or show_hours:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def fmt_minutes(minutes):
    minutes = int(minutes)
    if minutes < 60:
        return translate("units.minutes", count=minutes)
    return translate("units.hours_minutes", hours=minutes // 60, minutes=minutes % 60)


def ago(ts):
    elapsed = time.time() - ts
    if elapsed < 60:
        return translate("time.just_now")
    if elapsed < 3600:
        return translate("time.minutes_ago", count=int(elapsed // 60))
    if elapsed < 86400:
        return translate("time.hours_ago", count=int(elapsed // 3600))
    if elapsed < 172800:
        return translate("time.yesterday")
    return translate("time.days_ago", count=int(elapsed // 86400))


def until(sec):
    """Format a future delay, for example 'in 5 min' or 'in 2 h 10'."""
    sec = int(sec)
    if sec < 60:
        return translate("time.now")
    minutes = sec // 60
    if minutes < 60:
        return translate("time.in_minutes", count=minutes)
    hours = minutes // 60
    if hours < 24:
        return translate("time.in_hours", hours=hours, minutes=minutes % 60)
    return translate("time.in_days", count=hours // 24)
