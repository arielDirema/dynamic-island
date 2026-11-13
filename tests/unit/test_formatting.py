"""Shared formatting: sizes, durations and relative dates."""
import pytest

from dynamic_island.core.utilities.animation import smooth, spring
from dynamic_island.core.utilities import formatting


def test_human_sizes(language):
    language("en")
    assert formatting.human(0) == "0 B"
    assert formatting.human(1000) == "1000 B"
    assert formatting.human(1024) == "1 KB"
    assert formatting.human(1536) == "1.5 KB"
    assert formatting.human(1024 ** 2) == "1 MB"
    assert formatting.human(1024 ** 3) == "1 GB"
    assert formatting.human(1024 ** 4) == "1 TB"

    language("fr")
    assert formatting.human(1000) == "1000 o"
    assert formatting.human(1024) == "1 Ko"
    assert formatting.human(1536) == "1.5 Ko"


def test_fmt_dur():
    assert formatting.fmt_dur(0) == "0:00"
    assert formatting.fmt_dur(65) == "1:05"
    assert formatting.fmt_dur(3661) == "1:01:01"
    assert formatting.fmt_dur(5, show_hours=True) == "0:00:05"
    assert formatting.fmt_dur(-3) == "0:00"


def test_fmt_minutes(language):
    language("en")
    assert formatting.fmt_minutes(0) == "0 min"
    assert formatting.fmt_minutes(59) == "59 min"
    assert formatting.fmt_minutes(60) == "1 h 00"
    assert formatting.fmt_minutes(125) == "2 h 05"

    language("fr")
    assert formatting.fmt_minutes(0) == "0 min"
    assert formatting.fmt_minutes(60) == "1 h 00"


def test_ago(language, monkeypatch):
    language("en")
    monkeypatch.setattr(formatting.time, "time", lambda: 1_000_000)
    assert formatting.ago(1_000_000 - 10) == "just now"
    assert formatting.ago(1_000_000 - 120) == "2 min ago"
    assert formatting.ago(1_000_000 - 7200) == "2 h ago"
    assert formatting.ago(1_000_000 - 90_000) == "yesterday"
    assert formatting.ago(1_000_000 - 3 * 86400) == "3 d ago"

    language("fr")
    assert formatting.ago(1_000_000 - 10) == "à l'instant"
    assert formatting.ago(1_000_000 - 120) == "il y a 2 min"
    assert formatting.ago(1_000_000 - 7200) == "il y a 2 h"
    assert formatting.ago(1_000_000 - 90_000) == "hier"
    assert formatting.ago(1_000_000 - 3 * 86400) == "il y a 3 j"


def test_until(language):
    language("en")
    assert formatting.until(10) == "now"
    assert formatting.until(5 * 60) == "in 5 min"
    assert formatting.until(2 * 3600 + 10 * 60) == "in 2 h 10"
    assert formatting.until(3 * 86400) == "in 3 d"

    language("fr")
    assert formatting.until(10) == "maintenant"
    assert formatting.until(5 * 60) == "dans 5 min"


def test_smooth_clamps_and_interpolates():
    assert smooth(-1) == 0.0
    assert smooth(0) == 0.0
    assert smooth(0.5) == 0.5
    assert smooth(1) == 1.0
    assert smooth(2) == 1.0


def test_spring_converges():
    x, velocity = 0.0, 0.0
    for _ in range(200):
        x, velocity = spring(x, velocity, 1.0, 200.0, 0.008)
    assert x == pytest.approx(1.0, abs=0.01)
