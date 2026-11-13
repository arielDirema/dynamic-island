"""Validate external locale catalogs and translation keys used by the source.

Usage:
    python scripts/validate_locales.py
    python scripts/validate_locales.py --locales locales --source src

The command exits with status 1 when a critical localization problem is found,
which makes it suitable for CI.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from babel import Locale  # noqa: E402
from babel.core import UnknownLocaleError  # noqa: E402

from dynamic_island.core.localization.loader import REQUIRED_META  # noqa: E402
from dynamic_island.core.localization.resolver import (  # noqa: E402
    flatten_messages,
    placeholders,
)

SOURCE_KEY_PATTERN = re.compile(
    r"\b(?:translate|get_value|tr|t)\(\s*[\"']([^\"']+)[\"']"
)
HTML_KEY_PATTERN = re.compile(
    r"\{\{([\w.]+)\}\}|I18N_PHONE\[\s*[\"']([\w.]+)[\"']\s*\]"
)
VALID_LOCALE = re.compile(r"^[a-z]{2,3}(?:_[A-Z]{2})?$")


class ValidationError(Exception):
    pass


def _no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def load_json(path: Path) -> dict[str, object]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValidationError(f"cannot read {path}: {exc}") from exc
    try:
        data = json.loads(text, object_pairs_hook=_no_duplicates)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"{path}: invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValidationError(f"{path}: the root must be an object")
    return data


def validate_meta(path: Path, data: dict[str, object]) -> str:
    meta = data.get("meta")
    if not isinstance(meta, dict):
        raise ValidationError(f"{path}: missing 'meta' object")
    missing = [key for key in REQUIRED_META if not isinstance(meta.get(key), str) or not meta.get(key)]
    if missing:
        raise ValidationError(f"{path}: missing metadata: {', '.join(missing)}")
    code = str(meta["language"])
    if not VALID_LOCALE.fullmatch(code) or path.parent.name != code:
        raise ValidationError(f"{path}: locale identifier {code!r} does not match its directory")
    try:
        Locale.parse(code, sep="_")
    except (UnknownLocaleError, ValueError) as exc:
        raise ValidationError(f"{path}: unsupported locale identifier {code!r}") from exc
    if str(meta["direction"]).lower() not in {"ltr", "rtl"}:
        raise ValidationError(f"{path}: meta.direction must be 'ltr' or 'rtl'")
    return code


def leaf_forms(value: object) -> list[object]:
    if isinstance(value, dict):
        return [item for item in value.values()]
    return [value]


def value_placeholders(value: object) -> set[str]:
    result: set[str] = set()
    for form in leaf_forms(value):
        if isinstance(form, str):
            result |= placeholders(form)
    return result


def validate_catalog(path: Path, data: dict[str, object]) -> dict[str, object]:
    flat = flatten_messages(data)
    for key, value in flat.items():
        for form in leaf_forms(value):
            if isinstance(form, str) and not form.strip():
                raise ValidationError(f"{path}: empty translation for {key!r}")
            if not isinstance(form, (str, list)):
                raise ValidationError(f"{path}: unsupported value for {key!r}")
    return flat


def source_keys(source: Path) -> set[str]:
    keys: set[str] = set()
    if not source.is_dir():
        return keys
    for path in source.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        keys.update(SOURCE_KEY_PATTERN.findall(text))
    return keys


def page_keys(page: Path) -> set[str]:
    if not page.is_file():
        return set()
    keys: set[str] = set()
    for match in HTML_KEY_PATTERN.finditer(page.read_text(encoding="utf-8")):
        keys.add(match.group(1) or match.group(2))
    return keys


def validate(locales: Path, source: Path, page: Path, canonical: str) -> int:
    errors: list[str] = []
    if not locales.is_dir():
        print(f"ERROR: locales directory not found: {locales}", file=sys.stderr)
        return 1
    files: dict[str, Path] = {}
    for directory in sorted(locales.iterdir()):
        if not directory.is_dir():
            continue
        path = directory / "messages.json"
        if not path.is_file():
            errors.append(f"{directory}: missing messages.json")
            continue
        files[directory.name] = path
    if canonical not in files:
        print(f"ERROR: canonical locale {canonical!r} is missing", file=sys.stderr)
        return 1
    catalogs: dict[str, dict[str, object]] = {}
    for code, path in files.items():
        try:
            data = load_json(path)
            actual = validate_meta(path, data)
            if actual != code:
                errors.append(f"{path}: metadata language {actual!r} != directory {code!r}")
                continue
            catalogs[code] = validate_catalog(path, data)
        except ValidationError as exc:
            errors.append(str(exc))
    if canonical not in catalogs:
        print("\n".join(f"ERROR: {error}" for error in errors), file=sys.stderr)
        return 1

    reference = catalogs[canonical]
    for code, catalog in sorted(catalogs.items()):
        if code == canonical:
            continue
        missing = sorted(set(reference) - set(catalog))
        extra = sorted(set(catalog) - set(reference))
        for key in missing:
            errors.append(f"{code}: missing key {key!r}")
        for key in extra:
            errors.append(f"{code}: extra key {key!r}")
        for key in sorted(set(reference) & set(catalog)):
            expected = value_placeholders(reference[key])
            actual = value_placeholders(catalog[key])
            if expected != actual:
                errors.append(
                    f"{code}: placeholder mismatch for {key!r}: expected {sorted(expected)}, got {sorted(actual)}"
                )

    used = source_keys(source) | page_keys(page)
    for key in sorted(used - set(reference)):
        errors.append(f"source: translation key {key!r} is missing from {canonical}")

    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    print(f"Locales: {', '.join(sorted(catalogs))}")
    for code, catalog in sorted(catalogs.items()):
        missing = len(set(reference) - set(catalog))
        print(f"  {code}: {len(catalog)} keys, {missing} missing")
    print(f"Source keys: {len(used)} referenced, {len(used & set(reference))} resolved")
    if errors:
        print(f"FAILED: {len(errors)} localization problem(s)", file=sys.stderr)
        return 1
    print("OK: localization catalogs are consistent")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--locales", type=Path, default=ROOT / "locales")
    parser.add_argument("--source", type=Path, default=SRC)
    parser.add_argument("--page", type=Path, default=ROOT / "resources" / "phone_page.html")
    parser.add_argument("--canonical", default="en")
    args = parser.parse_args()
    return validate(args.locales, args.source, args.page, args.canonical)


if __name__ == "__main__":
    raise SystemExit(main())
