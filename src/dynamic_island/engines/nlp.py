"""Natural-language quick entry in English and French:
“Meeting tomorrow 2:30 pm”, “Call Paul Monday !high #work”,
“Marie's birthday 03/12”, “Dentist on the 5th at 9am for 30 min”."""
import datetime as dt
import re

from babel.dates import get_day_names, get_month_names

PRIORITY_TOKENS = {
    "!high": 3, "!urgent": 3, "!haute": 3, "!élevée": 3, "!elevee": 3, "!!!": 3,
    "!medium": 2, "!moyenne": 2, "!!": 2,
    "!low": 1, "!faible": 1, "!basse": 1, "!": 1,
}  # French tokens remain for existing user input
BIRTHDAY_RE = re.compile(r"\b(anniv(ersaire)?|birthday|geburtstag)\b", re.I)


def _day_names(locale: str) -> list[str]:
    names = get_day_names("wide", locale=locale)
    return [names[index] for index in range(7)]


DAYS = {name.lower(): index for locale in ("en", "fr") for index, name in enumerate(_day_names(locale))}
MONTHS = {
    get_month_names("wide", locale=locale)[month].lower(): month
    for locale in ("en", "fr")
    for month in range(1, 13)
}
DAY_PATTERN = "|".join(sorted((re.escape(name) for name in DAYS), key=len, reverse=True))
MONTH_PATTERN = "|".join(sorted((re.escape(name) for name in MONTHS), key=len, reverse=True))


def parse(text, now=None):
    """Return dict(title, date, time, duration, priority, project, birthday)."""
    now = now or dt.datetime.now()
    text = " " + text.strip() + " "
    out = {"date": None, "time": None, "duration": None, "priority": 0, "project": None, "birthday": False}

    def cut(match):
        nonlocal text
        text = text[:match.start()] + " " + text[match.end():]

    for token, value in sorted(PRIORITY_TOKENS.items(), key=lambda item: -len(item[0])):
        match = re.search(r"(?<!\S)" + re.escape(token) + r"(?!\S)", text, re.I)
        if match:
            out["priority"] = value
            cut(match)
            break
    match = re.search(r"(?<!\S)#([\w-]+)", text)
    if match:
        out["project"] = match.group(1)
        cut(match)
    if BIRTHDAY_RE.search(text):
        out["birthday"] = True
    match = re.search(r"\b(?:pendant|for)\s+(\d+)\s*(h|hours?|heures?|min|minutes?)\b", text, re.I)
    if match:
        count = int(match.group(1))
        out["duration"] = count * 60 if match.group(2).lower().startswith("h") else count
        cut(match)
    match = re.search(
        r"\b(?:at\s+|à\s+)?(\d{1,2})(?:\s*[:h]\s*(\d{2})?\s*(am|pm)?|\s*(am|pm))\b",
        text, re.I,
    )
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        meridiem = (match.group(3) or match.group(4) or "").lower()
        if meridiem:
            hour = hour % 12 + (12 if meridiem == "pm" else 0)
        if hour < 24:
            out["time"] = dt.time(hour, minute)
            cut(match)
    today = now.date()
    match = re.search(r"\b(aujourd'hui|auj|ce soir|today|tonight)\b", text, re.I)
    if match:
        out["date"] = today
        if match.group(1).lower() in ("ce soir", "tonight") and not out["time"]:
            out["time"] = dt.time(20, 0)
        cut(match)
    if not out["date"]:
        match = re.search(r"\b(après[- ]demain|day after tomorrow)\b", text, re.I)
        if match:
            out["date"] = today + dt.timedelta(days=2)
            cut(match)
    if not out["date"]:
        match = re.search(r"\b(demain|tomorrow)\b", text, re.I)
        if match:
            out["date"] = today + dt.timedelta(days=1)
            cut(match)
    if not out["date"]:
        match = re.search(
            r"\b(?:dans\s+(\d+)\s*(jours?|j|semaines?)|in\s+(\d+)\s*(days?|weeks?))\b",
            text, re.I,
        )
        if match:
            count = int(match.group(1) or match.group(3))
            unit = (match.group(2) or match.group(4)).lower()
            days = count * 7 if unit.startswith(("s", "w")) else count
            out["date"] = today + dt.timedelta(days=days)
            cut(match)
    if not out["date"]:
        match = re.search(r"\b(?:le\s+)?(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{2,4}))?\b", text)
        if match:
            day, month = int(match.group(1)), int(match.group(2))
            year = int(match.group(3)) if match.group(3) else today.year
            if year < 100:
                year += 2000
            try:
                date = dt.date(year, month, day)
                if not match.group(3) and date < today:
                    date = date.replace(year=year + 1)
                out["date"] = date
                cut(match)
            except ValueError:
                pass
    if not out["date"]:
        # French order: “12 mars”; English order: “March 12” or “12 March”.
        match = re.search(r"\b(?:le\s+|on\s+)?(\d{1,2})\s+(" + MONTH_PATTERN + r")\b", text, re.I)
        if match:
            day, month_name = int(match.group(1)), match.group(2).lower()
            date = dt.date(today.year, MONTHS[month_name], day)
            if date < today:
                date = date.replace(year=today.year + 1)
            out["date"] = date
            cut(match)
    if not out["date"]:
        match = re.search(r"\b(" + MONTH_PATTERN + r")\s+(\d{1,2})(?:st|nd|rd|th)?\b", text, re.I)
        if match:
            day, month_name = int(match.group(2)), match.group(1).lower()
            date = dt.date(today.year, MONTHS[month_name], day)
            if date < today:
                date = date.replace(year=today.year + 1)
            out["date"] = date
            cut(match)
    if not out["date"]:
        match = re.search(
            r"\b(?:ce\s+|prochain\s+|next\s+)?(" + DAY_PATTERN + r")(?:\s+prochain)?\b",
            text, re.I,
        )
        if match:
            weekday = DAYS[match.group(1).lower()]
            delta = (weekday - today.weekday()) % 7 or 7
            out["date"] = today + dt.timedelta(days=delta)
            cut(match)
    if not out["date"]:
        match = re.search(r"\b(?:le\s+|on\s+the\s+)(\d{1,2})(?:st|nd|rd|th)?\b", text, re.I)
        if match:
            day = int(match.group(1))
            try:
                date = today.replace(day=day)
                if date < today:
                    date = (today.replace(day=1) + dt.timedelta(days=32)).replace(day=day)
                out["date"] = date
                cut(match)
            except ValueError:
                pass
    if out["time"] and not out["date"]:
        out["date"] = today if dt.datetime.combine(today, out["time"]) > now else today + dt.timedelta(days=1)

    title = re.sub(r"\s+", " ", text).strip(" ,-")
    title = re.sub(r"\b(le|à|pour|at|for|on)$", "", title, flags=re.I).strip()
    out["title"] = title[:1].upper() + title[1:] if title else ""
    return out


def parse_duration(text):
    """'25', '10m', '1h30', '90s', '1:30' -> seconds (None if invalid)."""
    value = text.strip().lower().replace(" ", "")
    if not value:
        return None
    match = re.fullmatch(r"(\d+)(?:s|sec|secondes?|seconds?)", value)
    if match:
        return int(match.group(1)) or None
    match = re.fullmatch(r"(\d+):(\d{1,2})(?::(\d{1,2}))?", value)
    if match:
        hours, minutes, seconds = match.groups()
        return (int(hours) * 3600 + int(minutes) * 60 + int(seconds) if seconds
                else int(hours) * 60 + int(minutes))
    match = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)(?:m|min|minutes?)?)?(?:(\d+)s)?", value)
    if match and any(match.groups()):
        hours, minutes, seconds = (int(part) if part else 0 for part in match.groups())
        total = hours * 3600 + minutes * 60 + seconds
        return total or None
    return None
