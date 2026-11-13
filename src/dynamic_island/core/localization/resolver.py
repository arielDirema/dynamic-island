"""Key resolution, plural selection, locale detection and locale-aware formatting."""
from __future__ import annotations

import locale as stdlib_locale
import os
import re
from datetime import date, datetime, time
from string import Formatter
from typing import Any

from babel import Locale
from babel.dates import (
    format_date as babel_format_date,
    format_datetime as babel_format_datetime,
    format_time as babel_format_time,
    get_day_names,
)
from babel.numbers import (
    format_currency as babel_format_currency,
    format_decimal,
    format_percent as babel_format_percent,
)

PLURAL_CATEGORIES = frozenset({"zero", "one", "two", "few", "many", "other"})
_LOCALE_PATTERN = re.compile(r"^[A-Za-z]{2,3}(?:[-_][A-Za-z]{2})?$")
_PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)(?:![rsa])?(?::[^}]*)?\}")


def normalize_locale(code: str | None) -> str | None:
    """Normalize a locale identifier to ``ll`` or ``ll_RR`` form."""
    if not code:
        return None
    value = code.strip().replace("-", "_").split(".", 1)[0].split("@", 1)[0]
    if not _LOCALE_PATTERN.fullmatch(value):
        return None
    parts = value.split("_")
    if len(parts) == 2:
        return f"{parts[0].lower()}_{parts[1].upper()}"
    return parts[0].lower()


def resolve_locale(requested: str | None, available: list[str]) -> str | None:
    """Return the best available locale for a user or system preference.

    Priority: exact match, language-only match, then the first regional variant
    of the same language.
    """
    normalized = normalize_locale(requested)
    if not normalized:
        return None
    if normalized in available:
        return normalized
    language = normalized.split("_", 1)[0]
    if language in available:
        return language
    for candidate in available:
        if candidate.split("_", 1)[0] == language:
            return candidate
    return None


def detect_system_languages() -> list[str]:
    """Return candidate UI languages without importing a GUI toolkit."""
    candidates: list[str] = []
    try:
        import ctypes

        language_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        windows_name = stdlib_locale.windows_locale.get(language_id)
        if windows_name:
            candidates.append(windows_name)
    except (AttributeError, OSError):
        pass
    for variable in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(variable)
        if value:
            candidates.extend(value.split(":"))
    try:
        current = stdlib_locale.getlocale()[0]
        if current:
            candidates.append(current)
    except (ValueError, TypeError):
        pass
    result: list[str] = []
    for candidate in candidates:
        normalized = normalize_locale(candidate)
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def is_plural_entry(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and bool(value)
        and set(value).issubset(PLURAL_CATEGORIES)
        and all(isinstance(item, str) for item in value.values())
    )


def flatten_messages(messages: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    """Flatten a catalog into dot-separated keys, leaving plural objects intact."""
    flat: dict[str, Any] = {}
    for key, value in messages.items():
        if not prefix and key == "meta":
            continue
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict) and not is_plural_entry(value):
            flat.update(flatten_messages(value, full_key))
        else:
            flat[full_key] = value
    return flat


def placeholders(template: str) -> set[str]:
    """Return named placeholders used by a format string."""
    return {name for _, name, _, _ in Formatter().parse(template) if name}


def _plural_text(value: dict[str, str], language: str, count: Any) -> str:
    try:
        category = Locale.parse(language).plural_form(count)
    except (ValueError, TypeError):
        category = "other"
    if category in value:
        return value[category]
    return value.get("other", "")


def resolve_message(
    catalogs: dict[str, dict[str, Any]],
    language: str,
    default_language: str,
    key: str,
    params: dict[str, Any] | None = None,
) -> tuple[str, str | None, bool]:
    """Resolve a message.

    Returns ``(text, fallback_language, missing)``. The caller decides how to log
    the fallback or missing key. Missing keys return the key itself, never an
    exception.
    """
    params = params or {}
    selected: Any = None
    fallback: str | None = None
    for candidate in (language, default_language):
        value = catalogs.get(candidate, {}).get(key)
        if value is None:
            continue
        if isinstance(value, dict):
            if "count" not in params:
                value = value.get("other")
            else:
                value = _plural_text(value, candidate, params["count"])
        if isinstance(value, str) and value:
            selected = value
            fallback = candidate if candidate != language else None
            break
    if selected is None:
        return key, None, True
    if params:
        try:
            selected = selected.format(**params)
        except (KeyError, IndexError, ValueError):
            return selected, fallback, False
    return selected, fallback, False


def format_number(value: float | int, language: str, **kwargs: Any) -> str:
    return format_decimal(value, locale=language, **kwargs)


def format_currency(value: float | int, currency: str, language: str) -> str:
    return babel_format_currency(value, currency, locale=language)


def format_percent(value: float | int, language: str) -> str:
    return babel_format_percent(value, locale=language)


def format_date(value: date | datetime, language: str, format: str = "medium") -> str:
    return babel_format_date(value, format=format, locale=language)


def format_time(value: time | datetime, language: str, format: str = "short") -> str:
    return babel_format_time(value, format=format, locale=language)


def format_datetime(value: datetime, language: str, format: str = "medium") -> str:
    return babel_format_datetime(value, format=format, locale=language)


def format_day_name(value: date | datetime, language: str, width: str = "wide") -> str:
    return babel_format_date(value, format="EEEE" if width == "wide" else "EEE", locale=language)


def format_month_name(value: date | datetime, language: str, width: str = "wide") -> str:
    return babel_format_date(value, format="MMMM" if width == "wide" else "MMM", locale=language)


def weekday_names(language: str, width: str = "short") -> list[str]:
    """Return Monday-to-Sunday weekday names for a locale."""
    names = get_day_names(width=width, locale=language)
    return [names[index] for index in range(7)]
