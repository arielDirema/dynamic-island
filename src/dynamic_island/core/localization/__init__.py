"""Public API for translations, language selection and locale-aware formatting."""
from __future__ import annotations

from typing import Any, Callable

from dynamic_island.core.config import paths
from dynamic_island.core.config.settings import settings
from dynamic_island.core.localization.exceptions import (
    CatalogError,
    LocalizationError,
    UnsupportedLanguageError,
)
from dynamic_island.core.localization.loader import LanguageInfo
from dynamic_island.core.localization.manager import LocalizationManager

_LOCALIZATION: LocalizationManager | None = None


def get_localization() -> LocalizationManager:
    """Return the process-wide localization manager."""
    global _LOCALIZATION
    if _LOCALIZATION is None:
        _LOCALIZATION = LocalizationManager(paths.resource("locales"), settings=settings)
    return _LOCALIZATION


def translate(key: str, **params: Any) -> str:
    """Translate a dotted key for the active language."""
    return get_localization().translate(key, **params)


def get_value(key: str, default: Any = None) -> Any:
    """Return a structured translation value (lists, objects)."""
    return get_localization().get_value(key, default)


def set_language(language: str, *, persist: bool = True) -> LanguageInfo:
    """Switch the application language and persist the choice."""
    return get_localization().set_language(language, persist=persist)


def current_language() -> str:
    return get_localization().language


def language_info() -> LanguageInfo:
    return get_localization().language_info


def available_languages() -> list[LanguageInfo]:
    return get_localization().available_languages


def on_language_changed(callback: Callable[[str], None]) -> Callable[[], None]:
    return get_localization().on_change(callback)


def reload_localization() -> None:
    get_localization().reload()


def format_number(value: float | int, **kwargs: Any) -> str:
    return get_localization().format_number(value, **kwargs)


def format_currency(value: float | int, currency: str) -> str:
    return get_localization().format_currency(value, currency)


def format_percent(value: float | int) -> str:
    return get_localization().format_percent(value)


def format_date(value: Any, format: str = "medium") -> str:
    return get_localization().format_date(value, format)


def format_time(value: Any, format: str = "short") -> str:
    return get_localization().format_time(value, format)


def format_datetime(value: Any, format: str = "medium") -> str:
    return get_localization().format_datetime(value, format)


def format_day_name(value: Any, width: str = "wide") -> str:
    return get_localization().format_day_name(value, width)


def format_month_name(value: Any, width: str = "wide") -> str:
    return get_localization().format_month_name(value, width)


def weekday_names(width: str = "short") -> list[str]:
    return get_localization().weekday_names(width)


__all__ = [
    "CatalogError",
    "LanguageInfo",
    "LocalizationError",
    "LocalizationManager",
    "UnsupportedLanguageError",
    "available_languages",
    "current_language",
    "format_currency",
    "format_date",
    "format_datetime",
    "format_day_name",
    "format_month_name",
    "format_number",
    "format_percent",
    "format_time",
    "get_localization",
    "get_value",
    "language_info",
    "on_language_changed",
    "reload_localization",
    "set_language",
    "translate",
    "weekday_names",
]
