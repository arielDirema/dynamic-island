"""Ensure the `src/dynamic_island` package takes precedence over the root launcher."""
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent / "src"
if str(SRC) in sys.path:
    sys.path.remove(str(SRC))
sys.path.insert(0, str(SRC))
