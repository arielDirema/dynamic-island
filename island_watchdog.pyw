"""Run the Dynamic Island watchdog from source (see core/application/watchdog.py)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from dynamic_island.core.application.watchdog import main  # noqa: E402

main()
