"""Compatibility launcher: run the island from source (`python src/main.py --island`)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from dynamic_island.app import main  # noqa: E402

if __name__ == "__main__":
    main()
