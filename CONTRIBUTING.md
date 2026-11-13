# Contributing

Contributions are welcome. Please use English for issues, pull requests, commit messages,
code, comments and technical discussions.

## Development setup

```powershell
git clone https://github.com/arielDirema/dynamic-island.git
cd dynamic-island
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m pip install pytest ruff cx_Freeze pillow
```

Run the application from source with:

```powershell
.\.venv\Scripts\python src\main.py
```

## Before opening a pull request

```powershell
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python -m ruff check src tests scripts
.\.venv\Scripts\python scripts\validate_locales.py
```

- Keep changes focused and preserve existing workflows and data formats.
- Add or update tests for behavioral changes.
- Do not weaken existing tests.
- Keep user-facing text in `locales/en/messages.json`; add translations to every supported locale.
- Do not add a runtime dependency without documenting why the standard library or Qt cannot solve
  the problem.
- Preserve compatibility with existing `%APPDATA%\DynamicIsland` data.
- Do not commit generated build output, user data, certificates or local settings.

## Localization changes

English is the canonical catalog. Every other catalog must have the same key structure and
placeholders. The validator rejects missing keys, extra keys, empty values, invalid metadata,
duplicate JSON keys, placeholder mismatches and unsupported locale identifiers.

When adding a language, copy `locales/en/messages.json` to `locales/<locale>/messages.json`, translate
all values, update the `meta` block and run the validator. No Python change is required.

## Pull requests

Describe the problem, the behavior change and how it was verified. Include screenshots for visual
changes and mention any compatibility impact. Do not include unrelated formatting or refactoring.
