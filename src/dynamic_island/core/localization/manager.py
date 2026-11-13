"""Central localization manager: language selection, fallback, formatting, notifications."""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any, Callable

from dynamic_island.core.localization.exceptions import UnsupportedLanguageError
from dynamic_island.core.localization.loader import Catalog, LanguageInfo, discover_catalogs
from dynamic_island.core.localization.resolver import (
    detect_system_languages,
    flatten_messages,
    format_currency,
    format_date,
    format_datetime,
    format_day_name,
    format_month_name,
    format_number,
    format_percent,
    format_time,
    resolve_locale,
    resolve_message,
    weekday_names,
)

LOGGER = logging.getLogger(__name__)
RELOAD_EMPTY_WARNING = "No locale catalogs are available; translation keys will be displayed."


class LocalizationManager:
    """Thread-safe translation manager backed by external JSON catalogs."""

    def __init__(
        self,
        locales_root: str | Path,
        *,
        default_language: str = "en",
        settings: Any = None,
        logger: logging.Logger | None = None,
    ):
        self.locales_root = Path(locales_root)
        self.default_language = default_language
        self._settings = settings
        self._logger = logger or LOGGER
        self._lock = threading.RLock()
        self._listeners: list[Callable[[str], None]] = []
        self._warned: set[tuple[str, str, str]] = set()
        self._missing: set[str] = set()
        self._catalogs: dict[str, Catalog] = {}
        self._flat: dict[str, dict[str, Any]] = {}
        self._language = default_language
        self._loaded_once = False
        self.reload(persist_choice=False)

    def reload(self, persist_choice: bool = False) -> None:
        """Reload all locale files, keeping the current language when possible."""
        with self._lock:
            catalogs = discover_catalogs(self.locales_root)
            flat = {
                code: flatten_messages(catalog.messages)
                for code, catalog in catalogs.items()
            }
            self._catalogs = catalogs
            self._flat = flat
            self._warned.clear()
            self._missing.clear()
            if not catalogs:
                self._logger.warning(RELOAD_EMPTY_WARNING)
                self._language = self.default_language
                return
            available = list(catalogs)
            if self._loaded_once:
                current = resolve_locale(self._language, available)
                if current is None:
                    current = self._initial_language(available)
            else:
                current = self._initial_language(available)
                self._loaded_once = True
            self._language = current
            if persist_choice:
                self._persist(current)

    def _initial_language(self, available: list[str]) -> str:
        preferred = self._preferred_language()
        resolved = resolve_locale(preferred, available)
        if resolved:
            return resolved
        if preferred:
            self._logger.warning("Stored language %r is unavailable; using system/default language", preferred)
        for candidate in detect_system_languages():
            resolved = resolve_locale(candidate, available)
            if resolved:
                return resolved
        resolved = resolve_locale(self.default_language, available)
        if resolved:
            return resolved
        return available[0]

    def _preferred_language(self) -> str | None:
        if self._settings is None:
            return None
        try:
            value = self._settings.get("language")
        except (AttributeError, TypeError):
            return None
        return value if isinstance(value, str) else None

    def _persist(self, language: str) -> None:
        if self._settings is None:
            return
        try:
            if hasattr(self._settings, "set"):
                self._settings.set("language", language)
            else:
                self._settings["language"] = language
        except (AttributeError, OSError, TypeError, ValueError) as exc:
            self._logger.warning("Could not persist language %r: %s", language, exc)

    @property
    def language(self) -> str:
        with self._lock:
            return self._language

    @property
    def language_info(self) -> LanguageInfo:
        with self._lock:
            catalog = self._catalogs.get(self._language)
            if catalog is not None:
                return catalog.info
            return LanguageInfo(self._language, self._language, self._language)

    @property
    def available_languages(self) -> list[LanguageInfo]:
        with self._lock:
            return [catalog.info for _, catalog in sorted(self._catalogs.items())]

    @property
    def available_codes(self) -> list[str]:
        return [info.code for info in self.available_languages]

    def set_language(self, language: str, *, persist: bool = True) -> LanguageInfo:
        """Switch the active language and notify UI listeners."""
        with self._lock:
            resolved = resolve_locale(language, list(self._catalogs))
            if resolved is None:
                raise UnsupportedLanguageError(language, list(self._catalogs))
            self._language = resolved
            if persist:
                self._persist(resolved)
            listeners = list(self._listeners)
            info = self._catalogs[resolved].info
        for listener in listeners:
            try:
                listener(resolved)
            except Exception:  # noqa: BLE001 - one broken UI listener must not break switching
                self._logger.exception("A language-change listener failed")
        return info

    def on_change(self, callback: Callable[[str], None]) -> Callable[[], None]:
        """Register a language-change callback and return an unsubscribe function."""
        with self._lock:
            self._listeners.append(callback)

        def unsubscribe() -> None:
            with self._lock:
                if callback in self._listeners:
                    self._listeners.remove(callback)

        return unsubscribe

    def _lookup(self, key: str, params: dict[str, Any] | None = None) -> Any:
        with self._lock:
            language = self._language
            catalogs = self._flat
            default = self.default_language
            text, fallback, missing = resolve_message(catalogs, language, default, key, params)
            if missing:
                self._missing.add(key)
                marker = ("missing", language, key)
                if marker not in self._warned:
                    self._warned.add(marker)
                    self._logger.warning(
                        "Missing translation %r for %r (and fallback %r)", key, language, default
                    )
                return key
            if fallback:
                self._missing.add(key)
                marker = ("fallback", language, key)
                if marker not in self._warned:
                    self._warned.add(marker)
                    self._logger.warning(
                        "Missing translation %r for %r; using %r", key, language, fallback
                    )
            return text

    def translate(self, key: str, **params: Any) -> str:
        """Translate a key with optional formatting parameters."""
        value = self._lookup(key, params or None)
        return value if isinstance(value, str) else str(value)

    def get_value(self, key: str, default: Any = None) -> Any:
        """Return a structured catalog value (for example a list of quotes)."""
        with self._lock:
            for language in (self._language, self.default_language):
                value = self._flat.get(language, {}).get(key)
                if value is not None:
                    if language != self._language:
                        self._missing.add(key)
                        marker = ("fallback", self._language, key)
                        if marker not in self._warned:
                            self._warned.add(marker)
                            self._logger.warning(
                                "Missing structured translation %r for %r; using %r",
                                key, self._language, language,
                            )
                    return value
        self._missing.add(key)
        self._logger.warning("Missing structured translation %r", key)
        return default

    @property
    def missing_keys(self) -> list[str]:
        with self._lock:
            return sorted(self._missing)

    def clear_missing_keys(self) -> None:
        with self._lock:
            self._missing.clear()

    def flat_catalog(self, language: str) -> dict[str, Any]:
        with self._lock:
            return dict(self._flat.get(language, {}))

    def format_number(self, value: float | int, **kwargs: Any) -> str:
        return format_number(value, self.language, **kwargs)

    def format_currency(self, value: float | int, currency: str) -> str:
        return format_currency(value, currency, self.language)

    def format_percent(self, value: float | int) -> str:
        return format_percent(value, self.language)

    def format_date(self, value: Any, format: str = "medium") -> str:
        return format_date(value, self.language, format)

    def format_time(self, value: Any, format: str = "short") -> str:
        return format_time(value, self.language, format)

    def format_datetime(self, value: Any, format: str = "medium") -> str:
        return format_datetime(value, self.language, format)

    def format_day_name(self, value: Any, width: str = "wide") -> str:
        return format_day_name(value, self.language, width)

    def format_month_name(self, value: Any, width: str = "wide") -> str:
        return format_month_name(value, self.language, width)

    def weekday_names(self, width: str = "short") -> list[str]:
        return weekday_names(self.language, width)
