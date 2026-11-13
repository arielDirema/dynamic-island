"""Cached island content must keep its scale on high-DPI displays."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

from dynamic_island.ui.components.painting import IslandPainting


@pytest.fixture(scope="module")
def qt_app():
    return QApplication.instance() or QApplication([])


def test_cached_content_uses_device_pixel_source_rect(qt_app):
    dpr = 1.25
    tw, th = 100, 50
    pm = QPixmap(int(tw * dpr) + 1, int(th * dpr) + 1)
    pm.setDevicePixelRatio(dpr)
    pm.fill(QColor("blue"))
    painter = QPainter(pm)
    painter.fillRect(QRectF(tw - 5, 0, 5, th), QColor("red"))
    painter.end()

    image = QImage(tw, th, QImage.Format.Format_ARGB32)
    image.fill(QColor("white"))
    painter = QPainter(image)
    IslandPainting._blit_content(painter, pm, tw / 2, 0, tw, th)
    painter.end()

    marker = QColor(image.pixel(tw - 2, th // 2))
    assert marker.red() > 200 and marker.blue() < 60
