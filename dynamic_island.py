"""Compatibility entry point for the installed application (see src/main.py)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from dynamic_island.main import main  # noqa: E402

if __name__ == "__main__":
    main()
