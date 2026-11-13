"""Discovery and loading of external JSON message catalogs."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dynamic_island.core.localization.exceptions import CatalogError

LOGGER = logging.getLogger(__name__)
MESSAGES_FILE = "messages.json"
REQUIRED_META = ("language", "native_name", "english_name", "direction")


@dataclass(frozen=True)
class LanguageInfo:
    """Public metadata used by the language selector."""

    code: str
    native_name: str
    english_name: str
    direction: str = "ltr"


@dataclass(frozen=True)
class Catalog:
    """One locale directory and its raw message tree."""

    info: LanguageInfo
    messages: dict[str, Any]
    path: Path


def read_json(path: Path) -> dict[str, Any]:
    """Read a UTF-8 JSON object, converting low-level failures to CatalogError."""
    try:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except json.JSONDecodeError as exc:
        raise CatalogError(f"{path}: invalid JSON: {exc}") from exc
    except OSError as exc:
        raise CatalogError(f"{path}: cannot read catalog: {exc}") from exc
    if not isinstance(data, dict):
        raise CatalogError(f"{path}: the catalog root must be a JSON object")
    return data


def load_catalog(path: Path) -> Catalog:
    """Load one messages.json file and validate its required metadata."""
    data = read_json(path)
    meta = data.get("meta")
    if not isinstance(meta, dict):
        raise CatalogError(f"{path}: missing required 'meta' object")
    missing = [key for key in REQUIRED_META if not isinstance(meta.get(key), str) or not meta.get(key)]
    if missing:
        raise CatalogError(f"{path}: missing required metadata: {', '.join(missing)}")
    directory_code = path.parent.name
    code = str(meta["language"])
    if code != directory_code:
        raise CatalogError(
            f"{path}: meta.language is {code!r} but the directory is {directory_code!r}"
        )
    direction = str(meta["direction"]).lower()
    if direction not in {"ltr", "rtl"}:
        raise CatalogError(f"{path}: meta.direction must be 'ltr' or 'rtl'")
    info = LanguageInfo(
        code=code,
        native_name=str(meta["native_name"]),
        english_name=str(meta["english_name"]),
        direction=direction,
    )
    return Catalog(info=info, messages=data, path=path)


def discover_catalogs(locales_root: Path) -> dict[str, Catalog]:
    """Load every valid locale directory below locales_root.

    A broken locale is logged and skipped so one bad translation file cannot prevent
    the application from starting. The validator reports the same files as errors.
    """
    catalogs: dict[str, Catalog] = {}
    if not locales_root.is_dir():
        LOGGER.error("Locales directory not found: %s", locales_root)
        return catalogs
    for directory in sorted(locales_root.iterdir()):
        if not directory.is_dir():
            continue
        messages = directory / MESSAGES_FILE
        if not messages.is_file():
            LOGGER.warning("Ignoring locale directory without %s: %s", MESSAGES_FILE, directory)
            continue
        try:
            catalog = load_catalog(messages)
        except CatalogError as exc:
            LOGGER.error("Ignoring invalid locale %s: %s", directory.name, exc)
            continue
        if catalog.info.code in catalogs:
            LOGGER.error("Duplicate locale identifier %s in %s", catalog.info.code, directory)
            continue
        catalogs[catalog.info.code] = catalog
    if not catalogs:
        LOGGER.error("No valid locale catalogs found in %s", locales_root)
    return catalogs
