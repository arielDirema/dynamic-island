"""Shared pytest fixtures."""
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture
def language():
    """Switch the global localization manager without touching user settings."""
    from dynamic_island.core.localization import current_language, set_language

    previous = current_language()

    def use(code):
        set_language(code, persist=False)

    yield use
    set_language(previous, persist=False)

