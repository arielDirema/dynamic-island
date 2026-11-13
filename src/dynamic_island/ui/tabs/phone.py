"""Phone tab: connection QR, phone state, text/file sending, clipboard sync,
notifications and calls (Phone Link)."""
import datetime as dt
import os

from PySide6.QtCore import QPointF, QRectF

from dynamic_island.core.localization import format_time, translate as tr
from dynamic_island.core.utilities.formatting import ago
from dynamic_island.ui.components.drawing import CENTER, RIGHT
from dynamic_island.ui.themes import G, T, W, font

CONTENT_H = 372


class PhoneTab:
    key, label_key, glyph = "phone", "tabs.phone", G["phone"]

    def __init__(self, isl):
        self.isl = isl
        self.show_wifi = False
        self._wifi = None

    def height(self):
        return CONTENT_H

    def toggle_wifi(self):
        self.show_wifi = not self.show_wifi
        if self.show_wifi and self._wifi is None:
            from dynamic_island.services.phone import wifi_qr
            self._wifi = wifi_qr() or False

    def paint(self, ui, cr):
        isl = self.isl
        phone = isl.phone
        phone.check_network()
        x0 = cr.left() + 16
        qc = QRectF(x0, cr.top() + 2, 196, cr.height() - 12)
        ui.card(qc)
        qr_rect = QRectF(qc.left() + 18, qc.top() + 34, 160, 160)
        if self.show_wifi:
            ui.text(QRectF(qc.left() + 12, qc.top() + 6, qc.width() - 24, 24), "Wi-Fi",
                    font(9.5, W.DemiBold))
            if self._wifi:
                ssid, text = self._wifi
                ui.qr(qr_rect, text)
                ui.text(QRectF(qc.left() + 8, qr_rect.bottom() + 6, qc.width() - 16, 18), ssid,
                        font(8.5, W.DemiBold), T.text, CENTER)
                ui.text(QRectF(qc.left() + 8, qr_rect.bottom() + 24, qc.width() - 16, 16),
                        tr("phone.scan_wifi"), font(7.5), T.text3, CENTER)
            else:
                ui.empty(qr_rect, G["wifi"], tr("phone.wifi_not_found"))
        elif phone.running:
            ui.text(QRectF(qc.left() + 12, qc.top() + 6, qc.width() - 24, 24),
                    tr("phone.connect_title"), font(9.5, W.DemiBold))
            ui.qr(qr_rect, phone.url)
            ui.text(QRectF(qc.left() + 8, qr_rect.bottom() + 6, qc.width() - 16, 16),
                    f"{phone.ip}:{8765}", font(8, W.DemiBold), T.text2, CENTER)
            ui.wrap(QRectF(qc.left() + 12, qr_rect.bottom() + 24, qc.width() - 24, 34),
                    tr("phone.same_wifi_hint"), font(7.5), T.text3, 2)
        else:
            ui.text(QRectF(qc.left() + 12, qc.top() + 6, qc.width() - 24, 24),
                    tr("phone.local_connection"), font(9.5, W.DemiBold))
            ui.empty(qr_rect, G["phone"], tr("common.disabled"), tr("phone.disabled_hint"))
            ui.button(QRectF(qc.left() + 18, qr_rect.bottom() + 8, 160, 30), tr("common.enable"),
                      phone.start, G["play"], accent=True)
        by = qc.bottom() - 36
        if phone.running and not self.show_wifi:
            ui.button(QRectF(qc.left() + 10, by, 84, 28), tr("common.stop"), phone.stop, G["stop"])
            ui.button(QRectF(qc.left() + 100, by, 86, 28), tr("phone.new_link"), phone.new_token,
                      G["refresh"])
        ui.icon_button(QPointF(qc.right() - 18, qc.top() + 17),
                       G["wifi"] if not self.show_wifi else G["phone"],
                       self.toggle_wifi, 12, T.accent if self.show_wifi else None, 26)

        rx = qc.right() + 12
        rw = cr.right() - 16 - rx
        y = cr.top() + 2
        r = QRectF(rx, y, rw, 52)
        ui.card(r)
        device = phone.device
        if device:
            online = phone.connected
            ui.glyph(QPointF(r.left() + 20, r.center().y()), G["phone"], 16,
                     T.success if online else T.text3)
            ui.text(QRectF(r.left() + 40, r.top() + 6, rw - 150, 20), device["model"],
                    font(9.5, W.DemiBold))
            ui.text(QRectF(r.left() + 40, r.top() + 26, rw - 150, 18),
                    tr("phone.connected") if online else tr("phone.seen", ago=ago(device["seen"])),
                    font(7.5), T.success if online else T.text3)
            if device.get("battery") is not None:
                battery = device["battery"]
                color = T.success if device.get("charging") else (
                    T.critical if battery <= 20 else T.text
                )
                ui.text(QRectF(r.right() - 110, r.top(), 70, 52),
                        tr("units.percent", value=battery), font(12, W.DemiBold, True), color, RIGHT)
                ui.glyph(QPointF(r.right() - 24, r.center().y()),
                         G["charging"] if device.get("charging") else G["battery"], 17, color)
        else:
            ui.glyph(QPointF(r.left() + 20, r.center().y()), G["phone"], 16, T.text3)
            ui.text(QRectF(r.left() + 40, r.top(), rw - 50, 52),
                    tr("phone.no_device") if phone.running else tr("phone.enable_connection"),
                    font(8.5), T.text2)
        y += 60
        ui.field(QRectF(rx, y, rw - 36, 30), "phone_send", tr("phone.send_placeholder"),
                 on_submit=lambda text: phone.push_text(text), glyph="\ue724")
        ui.icon_button(QPointF(rx + rw - 15, y + 15), G["clip"], self._send_clip, 12, None, 30)
        y += 38
        ui.text(QRectF(rx, y, rw - 60, 24), tr("phone.sync_clipboard"), font(8), T.text2)
        ui.toggle(QPointF(rx + rw - 22, y + 12), phone.sync_clip,
                  lambda: phone.set_sync_clip(not phone.sync_clip))
        y += 30
        file_count = len([path for path in isl.files.shelf if os.path.isfile(path)])
        ui.text(QRectF(rx, y, rw - 110, 20), tr("phone.shelf_files", count=file_count),
                font(7.5), T.text3)
        ui.link(QRectF(rx + rw - 100, y, 100, 20), tr("tabs.files.views.shelf"),
                lambda: isl.set_tab("files"), font(7.5, W.Medium))
        y += 26
        ui.text(QRectF(rx, y, rw, 18), tr("phone.notifications"), font(8.5, W.DemiBold))
        y += 22
        lr = QRectF(rx - 4, y, rw + 8, cr.bottom() - y - 10)
        notifications = phone.notifications
        if phone.notif_ok is False:
            ui.wrap(QRectF(rx, y, rw, 50), tr("phone.notification_permission"), font(8), T.text3, 3)
            return
        if not notifications:
            ui.wrap(QRectF(rx, y, rw, 60), tr("phone.link_help"), font(8), T.text3, 3)
            ui.button(QRectF(rx, y + 44, 170, 26), tr("phone.open_link"), self._open_link, G["open"])
            return

        def draw(y0):
            yy = y0
            for notification in notifications:
                rr = QRectF(lr.left() + 4, yy, lr.width() - 14, 44)
                if ui.visible(rr):
                    ui.card(rr)
                    ui.glyph(QPointF(rr.left() + 16, rr.top() + 16),
                             G["phone"] if notification["call"] else G["bell"], 11,
                             T.success if notification["call"] else T.accent)
                    ui.text(QRectF(rr.left() + 32, rr.top() + 4, rr.width() - 90, 18),
                            notification["title"], font(8.5, W.DemiBold))
                    ui.text(QRectF(rr.right() - 60, rr.top() + 4, 52, 18),
                            format_time(dt.datetime.fromtimestamp(notification["ts"])),
                            font(7.5), T.text3, RIGHT)
                    ui.text(QRectF(rr.left() + 32, rr.top() + 22, rr.width() - 40, 18),
                            notification["body"], font(8), T.text2)
                yy += 48
            return yy - y0
        ui.scroll("phone_notifs", lr, draw)

    def _send_clip(self):
        from PySide6.QtWidgets import QApplication

        text = QApplication.clipboard().text()
        if self.isl.phone.push_text(text, "clip"):
            self.isl.show_alert("phone", tr("phone.sent"), text[:60], T.accent, G["phone"], duration=1.6)

    def _open_link(self):
        import subprocess

        subprocess.Popen(["explorer.exe", "shell:AppsFolder\\Microsoft.YourPhone_8wekyb3d8bbwe!App"])
