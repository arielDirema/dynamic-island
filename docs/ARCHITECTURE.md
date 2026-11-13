# Architecture

The application is an installable Python package (`src/dynamic_island`) with a thin source entry
point (`src/main.py`) and compatibility launchers at the repository root.

## Package tree

```text
src/
├── main.py
└── dynamic_island/
    ├── app.py                       single instance, window, icon, Qt loop
    ├── main.py                      CLI and self-test
    ├── core/
    │   ├── application/             autostart and watchdog
    │   ├── config/                  paths and persistent settings
    │   ├── localization/            loader, resolver, manager, exceptions
    │   └── utilities/               animation and shared formatting
    ├── models/                      domain metadata and translation keys
    ├── infrastructure/
    │   ├── storage/collection.py    JSON collections and synchronization
    │   └── windows_api.py           shared Win32 calls
    ├── engines/                     agenda, timers, tasks, files, media, network…
    ├── services/                    phone server and system controls
    └── ui/
        ├── windows/                 island window and layout constants
        ├── components/              drawing, painting and tray menu
        ├── tabs/                    one module per tab plus an explicit registry
        ├── themes/                  Windows 11 theme
        └── resources/               Fluent icons
locales/<language>/messages.json     external translations
resources/phone_page.html            phone page template
scripts/validate_locales.py          localization validator
tests/unit/, tests/architecture/
```

## Dependency rules

| Layer | May import |
|---|---|
| `core` | standard library, Babel, `core` |
| `models` | `core`, `models` |
| `infrastructure` | `core`, `models`, `infrastructure` |
| `engines` | `core`, `models`, `infrastructure`, `engines` |
| `services` | `core`, `models`, `infrastructure`, `engines`, `services` |
| `ui` | all internal layers |
| `app.py`, `main.py` | all internal layers |

Business logic never imports `ui`. `tests/architecture/test_layers.py` enforces these rules and
`test_cycles.py` rejects import cycles. Babel is the only third-party dependency allowed in `core`;
it provides CLDR plural selection and locale-aware number, date and currency formatting.

## Import conventions

- Internal imports are absolute: `from dynamic_island.engines.nlp import parse`.
- No historical flat imports (`import store`, `from theme import T`, `from tab_home import HomeTab`)
  remain under `src`.
- The four root launchers (`island.py`, `dynamic_island.py`, `watchdog.py`,
  `island_watchdog.pyw`) insert `src` and delegate to the package. They are compatibility
  entry points, not the primary import mechanism.
- `src/main.py` is added to `sys.path` by Python when executed as a script. Pytest adds `src` through
  `pyproject.toml` and the test conftest.

## Responsibilities

- **`core/config/paths.py`**: application root, resource paths, `%APPDATA%\DynamicIsland` and the
  selected synchronization folder.
- **`core/config/settings.py`**: persistent `settings` singleton with the existing JSON schema and
  atomic writes.
- **`core/localization/`**: external catalog discovery, dotted-key resolution, language preference,
  fallback, locale formatting, missing-key diagnostics and change notifications.
- **`infrastructure/storage/collection.py`**: `Collection`, newest-wins merge by `mtime`, tombstones,
  `sync_all` / `save_all` and the existing JSON format.
- **`models/`**: metadata and translation keys shared by engines and UI, plus localized quote content.
- **`engines/`**: business behavior and integrations.
- **`services/`**: phone HTTPS server and Windows system controls.
- **`ui/`**: window, painting, components, tabs, theme and icons. Tabs do not access storage internals.
- **`ui/tabs/__init__.py`**: explicit `TABS` and `TAB_VIEWS` registries; no dynamic tab imports.

## Localization

All user-facing text is retrieved through `dynamic_island.core.localization.translate` or
`get_value`. UI modules import it as `tr`; engine alerts use the same API.

The manager resolves messages in this order:

1. active language;
2. canonical English;
3. the translation key itself, with a warning and an entry in `missing_keys`.

Fallback and missing keys are logged once per language/key pair. The validator fails CI when a
catalog is incomplete or structurally inconsistent. Supported catalogs are discovered from
`locales/*/messages.json`; adding a language requires no Python change.

`manager.set_language()` persists the selection in `settings["language"]`, notifies subscribers and
updates the island cache, tab labels, menus and tray strings immediately. The phone page is rendered
from the active catalog on each request and reloads if the language changes while it is open.
Already displayed alerts and notifications keep their original text; newly rendered UI uses the new
language.

Date, time, number and currency formatting use Babel. Plural entries are JSON objects keyed by CLDR
categories (`one`, `other`, and additional categories where the language requires them).

## Compatibility

- User data remains in `%APPDATA%\DynamicIsland` with the same settings keys and collection formats.
  The new `language` key is additive.
- The downloads-phone folder name remains `Téléphone` to preserve existing file locations.
- French date/priority/reminder input tokens remain accepted for existing users.
- The phone page template moved to `resources/phone_page.html`; `setup_msi.py` packages it there.
- Root launchers keep the historical command names. From the repository root, `python -m
  dynamic_island…` can resolve the root `dynamic_island.py` launcher before `src/dynamic_island`;
  use `python src\main.py`, `start.bat`, the installed application, or set `src` first on
  `sys.path`. This is the only known import-name compatibility limitation.

## Packaging and verification

`setup_msi.py` builds `DynamicIsland.exe` from `src/main.py` and includes `dynamic_island`,
`locales`, `resources`, `assets` and the README. `pyproject.toml` describes Python package metadata
and pytest/ruff configuration; the official runtime distribution remains the cx_Freeze installer.

```powershell
python -m compileall -q src
python -m pytest
python -m ruff check src tests scripts
python scripts/validate_locales.py
python src/main.py --selftest
```

The self-test depends on optional Windows packages (`winrt`, `screen_brightness_control`, `icalendar`,
`recurring_ical_events`, `qrcode`). Missing packages are reported without changing user data.
