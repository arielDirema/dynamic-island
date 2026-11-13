"""Localization engine, catalogs, fallback, formatting and UI integration."""
import json
import logging
import subprocess
import sys
from pathlib import Path

import pytest

from dynamic_island.core.localization import (
    format_date,
    format_number,
    translate,
)
from dynamic_island.core.localization.manager import LocalizationManager
from dynamic_island.core.localization.resolver import (
    normalize_locale,
    resolve_locale,
)
from dynamic_island.ui.tabs import TABS

ROOT = Path(__file__).resolve().parents[2]
LOCALES = ROOT / "locales"
SCRIPT = ROOT / "scripts" / "validate_locales.py"


def write_catalog(root: Path, code: str, messages: dict) -> None:
    meta = {
        "language": code,
        "native_name": {"en": "English", "fr": "Français"}.get(code, code),
        "english_name": {"en": "English", "fr": "French"}.get(code, code),
        "direction": "ltr",
    }
    directory = root / code
    directory.mkdir(parents=True)
    (directory / "messages.json").write_text(
        json.dumps({"meta": meta, **messages}, ensure_ascii=False),
        encoding="utf-8",
    )


def test_english_is_the_fallback_default(monkeypatch):
    monkeypatch.setattr(
        "dynamic_island.core.localization.manager.detect_system_languages", lambda: []
    )
    manager = LocalizationManager(LOCALES, settings={})
    assert manager.language == "en"
    assert manager.translate("common.cancel") == "Cancel"


def test_external_catalogs_and_nested_keys(language):
    language("fr")
    assert translate("common.cancel") == "Annuler"
    assert translate("tabs.agenda.views.up") == "À venir"


def test_missing_key_is_reported_and_does_not_crash(manager_factory, caplog):
    manager = manager_factory("en")
    with caplog.at_level(logging.WARNING):
        assert manager.translate("missing.key") == "missing.key"
    assert "missing.key" in manager.missing_keys
    assert "Missing translation" in caplog.text


def test_french_falls_back_to_english(tmp_path):
    write_catalog(tmp_path, "en", {"only": {"english": "English only"}})
    write_catalog(tmp_path, "fr", {"present": "Présent"})
    manager = LocalizationManager(tmp_path, settings={"language": "fr"})
    assert manager.translate("only.english") == "English only"
    assert "only.english" in manager.missing_keys


def test_invalid_json_is_ignored(tmp_path, caplog):
    directory = tmp_path / "en"
    directory.mkdir()
    (directory / "messages.json").write_text("{not json", encoding="utf-8")
    with caplog.at_level(logging.ERROR):
        manager = LocalizationManager(tmp_path, settings={"language": "en"})
    assert manager.available_codes == []
    assert manager.translate("common.cancel") == "common.cancel"
    assert "invalid JSON" in caplog.text


def test_missing_locale_file_is_handled(tmp_path):
    manager = LocalizationManager(tmp_path, settings={"language": "en"})
    assert manager.available_codes == []
    assert manager.translate("common.cancel") == "common.cancel"


def test_parameterized_and_plural_messages(tmp_path):
    write_catalog(tmp_path, "en", {
        "greeting": "Hello {name}",
        "items": {"one": "{count} item", "other": "{count} items"},
    })
    write_catalog(tmp_path, "fr", {
        "greeting": "Bonjour {name}",
        "items": {"one": "{count} article", "other": "{count} articles"},
    })
    manager = LocalizationManager(tmp_path, settings={"language": "en"})
    assert manager.translate("greeting", name="Ada") == "Hello Ada"
    assert manager.translate("items", count=1) == "1 item"
    assert manager.translate("items", count=2) == "2 items"
    manager.set_language("fr", persist=False)
    assert manager.translate("items", count=0) == "0 article"
    assert manager.translate("items", count=2) == "2 articles"


def test_language_preference_is_persisted():
    preferences = {}
    manager = LocalizationManager(LOCALES, settings=preferences)
    manager.set_language("fr")
    assert preferences["language"] == "fr"
    assert LocalizationManager(LOCALES, settings=preferences).language == "fr"


def test_system_language_detection(monkeypatch):
    monkeypatch.setattr(
        "dynamic_island.core.localization.manager.detect_system_languages",
        lambda: ["fr_FR", "en_US"],
    )
    manager = LocalizationManager(LOCALES, settings={})
    assert manager.language == "fr"


def test_runtime_language_switch_notifies_listeners():
    manager = LocalizationManager(LOCALES, settings={"language": "en"})
    seen = []
    unsubscribe = manager.on_change(seen.append)
    manager.set_language("fr", persist=False)
    unsubscribe()
    manager.set_language("en", persist=False)
    assert seen == ["fr"]


def test_unicode_and_locale_formatting(language):
    language("fr")
    assert translate("common.cancel") == "Annuler"
    assert format_number(1234.5) == "1\u202f234,5"
    assert format_date(__import__("datetime").date(2026, 11, 12)) == "12 nov. 2026"

    language("en")
    assert format_number(1234.5) == "1,234.5"
    assert format_date(__import__("datetime").date(2026, 11, 12)) == "Nov 12, 2026"


def test_locale_normalization_and_resolution():
    assert normalize_locale("fr-FR") == "fr_FR"
    assert normalize_locale("pt_BR.UTF-8") == "pt_BR"
    assert resolve_locale("fr_CA", ["en", "fr"]) == "fr"
    assert resolve_locale("de", ["en", "fr"]) is None


def test_tabs_follow_the_active_language(language):
    language("en")
    assert translate(TABS[0].label_key) == "Home"
    language("fr")
    assert translate(TABS[0].label_key) == "Accueil"


def test_dynamic_key_families_are_complete(language):
    families = {
        "dev.git.status": ("clean", "modified", "uncommitted"),
        "dev.github.status": ("running", "success", "failure"),
        "launcher.kinds": ("app", "uwp", "url", "folder", "file", "ps", "py", "unknown"),
        "clipboard.tags": ("link", "email", "phone", "unknown"),
        "hotspot.bands": ("automatic", "2_4ghz", "5ghz"),
        "wallet.categories": ("spot", "funding", "earn"),
        "infos.widgets": ("weather", "clocks", "stats", "quote", "news", "stocks", "photo", "calendar"),
        "phone.web.units": ("byte", "kilobyte", "megabyte", "gigabyte"),
    }
    for code in ("en", "fr"):
        language(code)
        for prefix, values in families.items():
            for value in values:
                key = f"{prefix}.{value}"
                assert translate(key) != key, f"missing dynamic translation key {key}"


def test_phone_page_is_rendered_in_both_languages(language):
    from dynamic_island.services.phone import render_page

    language("en")
    english = render_page()
    assert "Send to PC" in english
    assert "{{" not in english
    assert 'lang="en"' in english

    language("fr")
    french = render_page()
    assert "Envoyer au PC" in french
    assert 'lang="fr"' in french


def test_shipped_catalogs_pass_the_validator():
    result = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True,
                            cwd=ROOT, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr


def _run_validator(locales: Path, source: Path, page: Path):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--locales", str(locales), "--source", str(source),
         "--page", str(page)],
        capture_output=True, text=True, cwd=ROOT, timeout=60,
    )


def test_validator_rejects_missing_and_extra_keys(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    write_catalog(tmp_path / "locales", "en", {"common": {"ok": "OK"}})
    write_catalog(tmp_path / "locales", "fr", {"common": {}, "extra": "En trop"})
    result = _run_validator(tmp_path / "locales", source, tmp_path / "missing.html")
    assert result.returncode == 1
    assert "missing key 'common.ok'" in result.stderr
    assert "extra key 'extra'" in result.stderr


def test_validator_rejects_duplicate_json_keys(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    directory = tmp_path / "locales" / "en"
    directory.mkdir(parents=True)
    (directory / "messages.json").write_text(
        '{"meta":{"language":"en","native_name":"English","english_name":"English",'
        '"direction":"ltr"},"common":{"ok":"OK","ok":"Yes"}}',
        encoding="utf-8",
    )
    result = _run_validator(tmp_path / "locales", source, tmp_path / "missing.html")
    assert result.returncode == 1
    assert "duplicate JSON key" in result.stderr



@pytest.fixture
def manager_factory():
    def create(language_code):
        return LocalizationManager(LOCALES, settings={"language": language_code})
    return create
