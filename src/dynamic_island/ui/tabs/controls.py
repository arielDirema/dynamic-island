"""Controls tab: Windows 11-style quick settings."""
import time

from PySide6.QtCore import QPointF, QRectF, QTimer

from dynamic_island.core.localization import translate as tr
from dynamic_island.services import system
from dynamic_island.ui.components.drawing import CENTER, RIGHT
from dynamic_island.ui.themes import G, T, W, font

APP_ROW = 30
HOTSPOT, LAN, EYE, EYE_OFF = chr(0xE88A), chr(0xE968), chr(0xE7B3), chr(0xED1A)


class ControlsTab:
    key, label_key, glyph = "controls", "tabs.controls", G["controls"]

    def __init__(self, isl):
        self.isl = isl
        self.picker = False
        self.confirm = None
        self.apps = []
        self.outputs = []
        self.panel = None          # "wifi" | "bt": detailed panel
        self.wifi_expand = None    # network whose password is being entered
        self.forget = None
        self.hs_edit = False       # hotspot name/password edition
        self.hs_show_pw = False
        self.hs_block = None       # block confirmation

    def height(self):
        if self.panel:
            return 372
        rows = len(self.outputs) if self.picker else len(self.apps)
        rows = max(1, min(4, rows))
        return 8 + 2 * 66 + 8 + 76 + 26 + rows * APP_ROW + 8 + 30 + 8

    def on_open(self):
        # after the opening animation: audio enumeration (COM) takes ~60 ms
        QTimer.singleShot(260, self.refresh)

    def refresh(self, brightness=True):
        isl = self.isl
        self.apps = isl.audio.apps()
        if self.picker:
            self.outputs = isl.audio.outputs()
        if brightness:
            isl.bright.request_refresh()

    def open_panel(self, which):
        self.panel = which
        self.wifi_expand = None
        self.isl.scrolls.pop("net_panel", None)
        if which == "wifi":
            self.isl.net.scan_wifi()
        elif which == "bt":
            self.isl.net.refresh_bt()
        elif which == "hotspot":
            self.isl.hotspot.visible = True
            self.isl.hotspot.refresh()
        elif which == "lan":
            self.isl.hotspot.scan_lan()

    def close_panel(self):
        self.panel = None
        self.isl.hotspot.visible = False
        self.hs_edit = False
        if self.isl.focus_field == "wifi_pw":
            self.isl.unfocus(restore=False)

    def _wifi_click(self, network):
        net = self.isl.net
        if net.wifi_cur.get("ssid") == network["ssid"] or net.wifi_busy:
            return
        if network["open"] or net.known(network["ssid"]):
            net.connect_wifi(network)
        else:
            self.wifi_expand = network["ssid"]
            self.isl.fields["wifi_pw"] = ""
            self.isl.focus("wifi_pw")

    def _wifi_password(self, network, password):
        if len(password) < 8:
            self.isl.show_alert("wifi", tr("controls.wifi.password_too_short"),
                                tr("controls.wifi.password_minimum"), T.critical, G["wifi"])
            return False
        self.isl.net.connect_wifi(network, password)
        self.wifi_expand = None
        self.isl.unfocus(restore=False)
        return True

    def _forget(self, ssid):
        if self.forget and self.forget[0] == ssid and time.time() - self.forget[1] < 3:
            self.forget = None
            self.isl.net.forget_wifi(ssid)
        else:
            self.forget = (ssid, time.time())

    @staticmethod
    def _bars(ui, center, signal, color):
        """Four Windows-style signal bars."""
        count = 1 if signal < 30 else 2 if signal < 55 else 3 if signal < 80 else 4
        for index in range(4):
            height = 4 + index * 3
            ui.rect(QRectF(center.x() - 8 + index * 4.5, center.y() + 7 - height, 3, height),
                    color if index < count else T.tint(color, 60), 1)

    def _panel(self, ui, cr):
        if self.panel == "hotspot":
            return self._hotspot_panel(ui, cr)
        if self.panel == "lan":
            return self._lan_panel(ui, cr)
        isl = self.isl
        net = isl.net
        x0, x1 = cr.left() + 16, cr.right() - 16
        y = cr.top() + 4
        wifi = self.panel == "wifi"
        ui.icon_button(QPointF(x0 + 12, y + 14), G["left"], self.close_panel, 12, None, 28)
        ui.text(QRectF(x0 + 32, y, 200, 28), "Wi-Fi" if wifi else "Bluetooth",
                font(11, W.DemiBold, True))
        radio_on = bool(isl.wifi if wifi else isl.bt)
        busy = net.wifi_scanning if wifi else net.bt_loading
        if busy:
            ui.text(QRectF(x1 - 210, y, 110, 28), tr("controls.scanning"), font(8), T.text3, RIGHT)
        else:
            ui.icon_button(QPointF(x1 - 86, y + 14), G["refresh"],
                           net.scan_wifi if wifi else net.refresh_bt, 11, None, 26)
        ui.toggle(QPointF(x1 - 24, y + 14), radio_on,
                  lambda: isl.toggle_radio("wifi" if wifi else "bluetooth"))
        body = QRectF(cr.left() + 8, y + 36, cr.width() - 16, cr.bottom() - y - 76)
        if not radio_on:
            ui.empty(body, G["wifi"] if wifi else G["bt"],
                     tr("controls.radio_disabled", name="Wi-Fi" if wifi else "Bluetooth"),
                     tr("controls.radio_disabled_hint"))
        elif wifi:
            ui.scroll("net_panel", body, lambda yy: self._wifi_list(ui, body, yy))
        else:
            ui.scroll("net_panel", body, lambda yy: self._bt_list(ui, body, yy))
        fy = cr.bottom() - 36
        if wifi:
            ui.button(QRectF(x0, fy, 170, 28), tr("controls.wifi.settings"),
                      lambda: isl.open_url("ms-settings:network-wifi"), G["settings"])
            ui.text(QRectF(x0 + 180, fy, x1 - x0 - 180, 28), tr("controls.wifi.hidden_hint"),
                    font(7.5), T.text3)
        else:
            ui.button(QRectF(x0, fy, 170, 28), tr("controls.bluetooth.add_device"),
                      lambda: isl.open_url("ms-settings:bluetooth"), G["add"], accent=True)
            ui.text(QRectF(x0 + 180, fy, x1 - x0 - 180, 28), tr("controls.bluetooth.connect_hint"),
                    font(7.5), T.text3)

    def _wifi_list(self, ui, body, y0):
        net = self.isl.net
        x0, x1 = body.left() + 8, body.right() - 14
        y = y0
        current = net.wifi_cur.get("ssid")
        networks = list(net.wifi)
        if current and not any(network["ssid"] == current for network in networks):
            networks.insert(0, {"ssid": current, "auth": "", "signal": net.wifi_cur.get("signal") or 0,
                                "open": False})
        networks.sort(key=lambda network: (network["ssid"] != current,
                                           not net.known(network["ssid"]), -network["signal"]))
        if not networks:
            message = tr("controls.wifi.searching") if net.wifi_scanning else tr("controls.wifi.none")
            ui.text(QRectF(x0, y + 10, x1 - x0, 20), message, font(9), T.text3, CENTER)
            return 40
        for network in networks:
            ssid = network["ssid"]
            connected = ssid == current
            expanded = self.wifi_expand == ssid
            height = 88 if expanded else 46
            r = QRectF(x0, y, x1 - x0, height)
            if ui.visible(r):
                hover = ui.row_hover(QRectF(r.left(), r.top(), r.width(), 46))
                ui.rect(r, T.layer2 if (hover or expanded or connected) else T.layer, 6,
                        T.accent if connected else T.stroke)
                color = T.accent if connected else T.text
                self._bars(ui, QPointF(r.left() + 22, r.top() + 23), network["signal"], color)
                if not network["open"]:
                    ui.glyph(QPointF(r.left() + 30, r.top() + 31), G["lock"], 8, T.text2)
                ui.text(QRectF(r.left() + 46, r.top() + 5, r.width() - 190, 18), ssid,
                        font(9, W.DemiBold))
                if net.wifi_busy == ssid:
                    subtitle, subtitle_color = tr("controls.wifi.connecting"), T.accent
                elif connected:
                    subtitle, subtitle_color = tr("controls.wifi.connected",
                                                  value=network["signal"]), T.success
                elif net.known(ssid):
                    security = tr("controls.wifi.open") if network["open"] else tr("controls.wifi.secured")
                    subtitle, subtitle_color = tr("controls.wifi.saved", security=security), T.text3
                else:
                    subtitle = (tr("controls.wifi.open_unsecured") if network["open"]
                                else network["auth"] or tr("controls.wifi.secured"))
                    subtitle_color = T.text3
                ui.text(QRectF(r.left() + 46, r.top() + 24, r.width() - 190, 16), subtitle,
                        font(7.5), subtitle_color)
                if connected:
                    ui.button(QRectF(r.right() - 112, r.top() + 9, 102, 28),
                              tr("controls.wifi.disconnect"), net.disconnect_wifi)
                else:
                    ui.row_hit(QRectF(r.left(), r.top(), r.width() - (90 if hover else 0), 46),
                               lambda network=network: self._wifi_click(network))
                    if hover and not expanded and not net.wifi_busy:
                        if net.known(ssid):
                            confirming = bool(self.forget and self.forget[0] == ssid
                                              and time.time() - self.forget[1] < 3)
                            ui.button(QRectF(r.right() - 182, r.top() + 9, 82, 28),
                                      tr("common.confirm") if confirming else tr("controls.wifi.forget"),
                                      lambda ssid=ssid: self._forget(ssid), danger=True)
                        ui.button(QRectF(r.right() - 94, r.top() + 9, 84, 28),
                                  tr("controls.wifi.connect"),
                                  lambda network=network: self._wifi_click(network), accent=True)
                if expanded:
                    ui.field(QRectF(r.left() + 46, r.top() + 48, r.width() - 160, 30), "wifi_pw",
                             tr("controls.wifi.password_placeholder"),
                             on_submit=lambda text, network=network: self._wifi_password(network, text),
                             glyph=G["lock"], secret=True)
                    ui.button(QRectF(r.right() - 106, r.top() + 49, 96, 28),
                              tr("controls.wifi.connect"),
                              lambda network=network: self._wifi_password(
                                  network, self.isl.fields.get("wifi_pw", "")), accent=True)
            y += height + 6
        return y - y0

    def _bt_list(self, ui, body, y0):
        net = self.isl.net
        x0, x1 = body.left() + 8, body.right() - 14
        y = y0
        devices = net.bt
        if not devices:
            message = (tr("controls.bluetooth.loading") if net.bt_loading
                       else tr("controls.bluetooth.none"))
            ui.text(QRectF(x0, y + 10, x1 - x0, 20), message, font(9), T.text3, CENTER)
            return 40
        icons = {"audio": G["headphone"], "phone": G["phone"], "input": G["keyboard"],
                 "computer": chr(0xE7F8)}
        for device in devices:
            r = QRectF(x0, y, x1 - x0, 46)
            if ui.visible(r):
                hover = ui.row_hover(r)
                connected = device["connected"]
                ui.rect(r, T.layer2 if (hover or connected) else T.layer, 6,
                        T.accent if connected else T.stroke)
                icon = icons.get(device["kind"], G["bt"])
                ui.glyph(QPointF(r.left() + 22, r.center().y()), icon, 15,
                         T.accent if connected else T.text2)
                ui.text(QRectF(r.left() + 46, r.top() + 5, r.width() - 180, 18),
                        device["name"], font(9, W.DemiBold))
                if net.bt_busy == device["address"]:
                    subtitle, subtitle_color = (
                        tr("controls.bluetooth.disconnecting") if connected
                        else tr("controls.bluetooth.connecting")
                    ), T.accent
                elif connected:
                    subtitle, subtitle_color = tr("controls.bluetooth.connected"), T.success
                elif device.get("off"):
                    subtitle, subtitle_color = tr("controls.bluetooth.disconnected_from_island"), T.text3
                else:
                    subtitle, subtitle_color = tr("controls.bluetooth.paired_not_connected"), T.text3
                kind = {
                    "audio": tr("controls.bluetooth.kind.audio"),
                    "phone": tr("controls.bluetooth.kind.phone"),
                    "input": tr("controls.bluetooth.kind.input"),
                    "computer": tr("controls.bluetooth.kind.computer"),
                }.get(device["kind"], tr("controls.bluetooth.kind.device"))
                ui.text(QRectF(r.left() + 46, r.top() + 24, r.width() - 180, 16),
                        tr("controls.bluetooth.summary", status=subtitle, kind=kind),
                        font(7.5), subtitle_color)
                if device["kind"] == "audio" and device["address"] and not net.bt_busy:
                    ui.button(QRectF(r.right() - 112, r.top() + 9, 102, 28),
                              tr("controls.wifi.disconnect") if connected
                              else tr("controls.wifi.connect"),
                              lambda device=device: net.bt_toggle(device), accent=not connected)
            y += 52
        return y - y0

    def _hs_header(self, ui, cr, title, right=None):
        x0, x1 = cr.left() + 16, cr.right() - 16
        y = cr.top() + 4
        ui.icon_button(QPointF(x0 + 12, y + 14), G["left"], self.close_panel, 12, None, 28)
        ui.text(QRectF(x0 + 32, y, 360, 28), title, font(11, W.DemiBold, True))
        if right:
            right(x1, y)
        return y + 36

    def _hs_save(self):
        fields = self.isl.fields
        name, password = fields.get("hs_name", "").strip(), fields.get("hs_pw", "").strip()
        if password and len(password) < 8:
            self.isl.show_alert("hotspot", tr("controls.hotspot.password_too_short"),
                                tr("controls.hotspot.password_minimum"), T.critical, HOTSPOT)
            return False
        self.isl.hotspot.configure(ssid=name or None, password=password or None)
        self.hs_edit = False
        self.isl.unfocus(restore=False)
        return True

    def _hs_block(self, client):
        if self.hs_block == client["mac"]:
            self.hs_block = None
            self.isl.hotspot.block(client)
        else:
            self.hs_block = client["mac"]

    def _hotspot_panel(self, ui, cr):
        isl = self.isl
        hotspot = isl.hotspot
        x0, x1 = cr.left() + 16, cr.right() - 16

        def right(xr, yy):
            if hotspot.busy or hotspot.state == "transition":
                ui.text(QRectF(xr - 190, yy, 140, 28), tr("controls.hotspot.please_wait"),
                        font(8), T.text3, RIGHT)
            ui.toggle(QPointF(xr - 24, yy + 14), hotspot.state == "on", hotspot.toggle)
        y = self._hs_header(ui, cr, tr("controls.hotspot.title"), right)
        on = hotspot.state == "on"
        # network card: name, password, band and connection QR
        card = QRectF(x0, y, x1 - x0, 124)
        ui.card(card)
        qr_width = 108 if (on and hotspot.password) else 0
        if qr_width:
            from dynamic_island.models.hotspot import wifi_qr_text
            ui.qr(QRectF(card.right() - qr_width - 8, card.top() + 8, qr_width, qr_width),
                  wifi_qr_text(hotspot.ssid, hotspot.password))
        cx = card.left() + 14
        content_width = card.width() - 28 - qr_width - (10 if qr_width else 0)
        if self.hs_edit:
            ui.field(QRectF(cx, card.top() + 10, content_width, 30), "hs_name",
                     hotspot.ssid or tr("controls.hotspot.network_name"), glyph=HOTSPOT,
                     on_submit=lambda text: self._hs_save())
            ui.field(QRectF(cx, card.top() + 46, content_width, 30), "hs_pw",
                     tr("controls.hotspot.new_password"), glyph=G["lock"],
                     secret=not self.hs_show_pw, on_submit=lambda text: self._hs_save())
            ui.button(QRectF(cx, card.top() + 86, 110, 28), tr("common.save"),
                      self._hs_save, G["check"], accent=True)
            ui.button(QRectF(cx + 118, card.top() + 86, 90, 28), tr("common.cancel"),
                      lambda: setattr(self, "hs_edit", False))
            from dynamic_island.engines.hotspot import random_password
            ui.button(QRectF(cx + 216, card.top() + 86, 170, 28),
                      tr("controls.hotspot.generate_password"),
                      lambda: (isl.fields.__setitem__("hs_pw", random_password()),
                               setattr(self, "hs_show_pw", True)), G["refresh"])
        else:
            ui.text(QRectF(cx, card.top() + 8, content_width, 18),
                    tr("controls.hotspot.network_name"), font(7.5), T.text3)
            ui.text(QRectF(cx, card.top() + 24, content_width, 22),
                    hotspot.ssid or "—", font(11, W.DemiBold))
            ui.text(QRectF(cx, card.top() + 50, content_width, 18),
                    tr("controls.hotspot.password"), font(7.5), T.text3)
            password = hotspot.password if self.hs_show_pw else "•" * min(12, len(hotspot.password or ""))
            ui.text(QRectF(cx, card.top() + 66, content_width - 40, 22), password or "—",
                    font(10, W.Medium))
            ui.icon_button(
                QPointF(cx + min(content_width - 20, ui.tw(password, font(10, W.Medium)) + 20),
                        card.top() + 77),
                EYE_OFF if self.hs_show_pw else EYE,
                lambda: setattr(self, "hs_show_pw", not self.hs_show_pw), 11, None, 24,
            )
            from dynamic_island.models.hotspot import BAND_KEYS
            bx = cx
            for band, label_key in BAND_KEYS.items():
                label = tr(label_key)
                width = ui.chip_w(label)
                ui.chip(QRectF(bx, card.top() + 94, width, 22), label, hotspot.band == band,
                        lambda band=band: hotspot.configure(band=band))
                bx += width + 4
            ui.button(QRectF(bx + 8, card.top() + 93, 92, 24), tr("common.edit"),
                      self._hs_start_edit, G["edit"])
        y += 132
        if hotspot.error and not on:
            ui.wrap(QRectF(x0, y, x1 - x0, 34), hotspot.error, font(8), T.critical, 2)
            y += 36
        elif not on:
            ui.text(QRectF(x0, y, x1 - x0, 18), tr("controls.hotspot.disabled_hint"),
                    font(8), T.text3)
            y += 22
        body = QRectF(cr.left() + 8, y, cr.width() - 16, cr.bottom() - y - 40)
        ui.scroll("hs_list", body, lambda yy: self._hs_devices(ui, body, yy))
        fy = cr.bottom() - 34
        ui.button(QRectF(x0, fy, 220, 28), tr("controls.hotspot.settings"),
                  lambda: isl.open_url("ms-settings:network-mobilehotspot"), G["settings"])
        ui.text(QRectF(x0 + 230, fy, x1 - x0 - 230, 28), tr("controls.hotspot.block_hint"),
                font(7.5), T.text3)

    def _hs_start_edit(self):
        self.hs_edit = True
        self.isl.fields["hs_name"] = self.isl.hotspot.ssid
        self.isl.fields["hs_pw"] = ""
        self.isl.focus("hs_name")

    def _hs_devices(self, ui, body, y0):
        hotspot = self.isl.hotspot
        x0, x1 = body.left() + 8, body.right() - 14
        y = y0
        ui.text(QRectF(x0, y, 340, 18),
                tr("controls.hotspot.connected_devices", count=len(hotspot.clients),
                   maximum=hotspot.max_clients), font(8.5, W.DemiBold))
        y += 22
        if not hotspot.clients:
            ui.text(QRectF(x0, y, x1 - x0, 18),
                    tr("controls.hotspot.no_devices") if hotspot.state == "on" else "—",
                    font(8), T.text3)
            y += 22
        for client in hotspot.clients:
            r = QRectF(x0, y, x1 - x0, 42)
            if ui.visible(r):
                ui.card(r)
                ui.glyph(QPointF(r.left() + 20, r.center().y()), G["phone"], 13,
                         T.critical if client["blocked"] else T.accent)
                ui.text(QRectF(r.left() + 40, r.top() + 4, r.width() - 190, 18),
                        client["name"], font(9, W.DemiBold))
                ui.text(QRectF(r.left() + 40, r.top() + 22, r.width() - 190, 16),
                        f"{client['ip'] or tr('controls.hotspot.ip_pending')} · {client['mac']}",
                        font(7.5), T.text3)
                confirming = self.hs_block == client["mac"]
                ui.button(QRectF(r.right() - 120, r.top() + 7, 110, 28),
                          tr("common.confirm") if confirming else tr("controls.hotspot.block"),
                          lambda client=client: self._hs_block(client),
                          G["close"] if not confirming else None, danger=not confirming,
                          accent=confirming)
            y += 46
        blocked = hotspot.blocked
        if blocked:
            y += 6
            ui.text(QRectF(x0, y, 300, 18), tr("controls.hotspot.blocked_devices", count=len(blocked)),
                    font(8.5, W.DemiBold))
            y += 22
            for client in blocked:
                ui.glyph(QPointF(x0 + 10, y + 11), G["close"], 10, T.critical)
                ui.text(QRectF(x0 + 24, y, x1 - x0 - 140, 22),
                        f"{client['name']} · {client['mac']}", font(8), T.text2)
                ui.link(QRectF(x1 - 80, y, 80, 22), tr("controls.hotspot.unblock"),
                        lambda mac=client["mac"]: hotspot.unblock(mac), font(8, W.Medium))
                y += 24
        return y - y0 + 4

    def _lan_panel(self, ui, cr):
        isl = self.isl
        hotspot = isl.hotspot
        x0, x1 = cr.left() + 16, cr.right() - 16

        def right(xr, yy):
            if hotspot.lan_scanning:
                ui.text(QRectF(xr - 170, yy, 160, 28), tr("controls.lan.scanning"),
                        font(8), T.text3, RIGHT)
            else:
                ui.icon_button(QPointF(xr - 14, yy + 14), G["refresh"], hotspot.scan_lan, 11, None, 26)
        ssid = isl.net.wifi_cur.get("ssid")
        title = tr("controls.lan.title")
        if ssid:
            title += f" · {ssid}"
        y = self._hs_header(ui, cr, title, right)
        info = hotspot.lan_info
        if info.get("net"):
            ui.text(QRectF(x0, y - 6, x1 - x0, 18),
                    tr("controls.lan.network_info", network=info["net"], ip=info.get("ip")),
                    font(7.5), T.text3)
            y += 16
        body = QRectF(cr.left() + 8, y, cr.width() - 16, cr.bottom() - y - 40)

        def draw(y0):
            yy = y0
            if not hotspot.lan:
                message = tr("controls.lan.scanning") if hotspot.lan_scanning else tr("controls.lan.none")
                ui.text(QRectF(x0, yy + 10, x1 - x0, 20), message, font(9), T.text3, CENTER)
                return 40
            icons = {"router": LAN, "self": chr(0xE7F8), "device": G["phone"]}
            for device in hotspot.lan:
                r = QRectF(body.left() + 8, yy, body.width() - 22, 42)
                if ui.visible(r):
                    ui.card(r)
                    color = T.accent if device["kind"] != "device" else T.text2
                    ui.glyph(QPointF(r.left() + 20, r.center().y()), icons[device["kind"]], 13, color)
                    label = {"router": tr("controls.lan.router"),
                             "self": tr("controls.lan.this_computer")}.get(device["kind"])
                    name = device["name"] or tr("controls.lan.unknown_device")
                    ui.text(QRectF(r.left() + 40, r.top() + 4, r.width() - 160, 18),
                            name + (f" · {label}" if label else ""), font(9, W.DemiBold))
                    ui.text(QRectF(r.left() + 40, r.top() + 22, r.width() - 160, 16),
                            f"{device['ip']} · {device['mac']}", font(7.5), T.text3)
                    if device["kind"] == "router":
                        ui.button(QRectF(r.right() - 140, r.top() + 7, 130, 28),
                                  tr("controls.lan.administer"),
                                  lambda ip=device["ip"]: isl.open_url(f"http://{ip}"), G["open"])
                yy += 46
            return yy - y0
        ui.scroll("lan_list", body, draw)
        ui.wrap(QRectF(x0, cr.bottom() - 36, x1 - x0, 32), tr("controls.lan.block_hint"),
                font(7.5), T.text3, 2)

    def toggle_picker(self):
        self.picker = not self.picker
        self.isl.scrolls.pop("ctl_list", None)
        if self.picker:
            self.outputs = self.isl.audio.outputs()

    def choose_output(self, device_id):
        isl = self.isl
        isl.audio.set_output(device_id)
        isl.out_id = isl.audio.default_id()
        isl.vol = isl.audio.volume()
        self.picker = False

    def do_sleep(self):
        if self.confirm and self.confirm > time.time():
            self.confirm = None
            self.isl.close_island(restore_focus=False)
            QTimer.singleShot(400, system.sleep_pc)
        else:
            self.confirm = time.time() + 3

    def do_lock(self):
        self.isl.close_island(restore_focus=False)
        system.lock_pc()

    def paint(self, ui, cr):
        isl = self.isl
        if self.panel:
            return self._panel(ui, cr)
        x0, x1 = cr.left() + 16, cr.right() - 16
        y = cr.top() + 4
        columns = 6
        gap = 7
        tile_width = (x1 - x0 - gap * (columns - 1)) / columns
        mic_on = isl.audio.mic_available() and not isl.audio.mic_muted()
        confirming = self.confirm and self.confirm > time.time()
        headphones = isl.headphones()
        tiles = [
            (G["wifi"], (isl.net.wifi_cur.get("ssid") if isl.wifi else None) or "Wi-Fi", bool(isl.wifi),
             lambda: isl.toggle_radio("wifi"), False, isl.wifi is not None, None,
             lambda: self.open_panel("wifi")),
            (G["bt"], (next((device["name"] for device in isl.net.bt
                             if device["connected"] and device["kind"] == "audio"), None)
                       if isl.bt else None) or "Bluetooth", bool(isl.bt),
             lambda: isl.toggle_radio("bluetooth"), False, isl.bt is not None, None,
             lambda: self.open_panel("bt")),
            (G["plane"], tr("controls.tiles.airplane"), isl.airplane_on(), isl.toggle_airplane,
             False, True, None),
            (G["night"], tr("controls.tiles.night_light"), isl.night, isl.toggle_night,
             False, isl.night_ok, None),
            (G["moon"], tr("controls.tiles.do_not_disturb"), isl.dnd.on, isl.dnd.toggle,
             False, True, None),
            (G["mic"], tr("controls.tiles.microphone") if mic_on else tr("controls.tiles.microphone_muted"),
             mic_on, isl.audio.toggle_mic, not mic_on, isl.audio.mic_available(), None),
            (G["cam"], tr("controls.tiles.camera") if isl.cam_allowed else tr("controls.tiles.camera_blocked"),
             isl.cam_allowed, isl.toggle_camera, not isl.cam_allowed, True, None),
            (G["headphone"] if headphones else G["speaker"], tr("controls.tiles.audio_output"),
             self.picker, self.toggle_picker, False, True, None),
            (G["lock"], tr("controls.tiles.lock"), False, self.do_lock, False, True, None),
            (G["power"], tr("controls.tiles.confirm") if confirming else tr("controls.tiles.sleep"),
             bool(confirming), self.do_sleep, False, True, T.critical),
            (HOTSPOT, tr("controls.tiles.hotspot"), isl.hotspot.state == "on",
             isl.hotspot.toggle, False,
             isl.hotspot.state is not None or isl.hotspot.error is not None, None,
             lambda: self.open_panel("hotspot")),
            (LAN, tr("controls.tiles.network_devices"), False,
             lambda: self.open_panel("lan"), False, True, None),
        ]
        tiles = tiles[:2] + [tiles[10], tiles[11]] + tiles[2:10]
        for index, tile in enumerate(tiles):
            glyph, label, on, action, slash, enabled, color = tile[:7]
            r = QRectF(x0 + (index % columns) * (tile_width + gap),
                       y + (index // columns) * 66, tile_width, 62)
            ui.tile(r, glyph, label, on, action, slash, enabled, color,
                    more=tile[7] if len(tile) > 7 else None)
        y += 2 * 66 + 8

        sx0, sx1 = x0 + 40, x1 - 50
        volume = 0 if isl.muted else isl.vol
        ui.icon_button(QPointF(x0 + 14, y + 16), G["mute"] if isl.muted else G["vol"],
                       isl.audio.toggle_mute, 14, T.text, 30)
        ui.slider(QRectF(sx0, y + 6, sx1 - sx0, 20), volume, isl.audio.set_volume)
        ui.text(QRectF(sx1 + 8, y, 42, 32), f"{volume * 100:.0f}",
                font(9, W.DemiBold), T.text, RIGHT)
        y += 38
        brightness = isl.bright.value
        ui.glyph(QPointF(x0 + 14, y + 16), G["sun"], 14,
                 T.text if brightness is not None else T.disabled)
        if brightness is not None:
            ui.slider(QRectF(sx0, y + 6, sx1 - sx0, 20), brightness / 100,
                      lambda value: isl.bright.set(value * 100))
            ui.text(QRectF(sx1 + 8, y, 42, 32), f"{brightness:.0f}",
                    font(9, W.DemiBold), T.text, RIGHT)
        else:
            ui.text(QRectF(sx0, y, sx1 - sx0, 32), tr("controls.brightness_unavailable"),
                    font(8.5), T.text3)
        y += 38

        title = tr("controls.choose_output") if self.picker else tr("controls.app_volume")
        ui.text(QRectF(x0, y, 320, 20), title, font(8.5, W.DemiBold))
        y += 24
        rows = self.outputs if self.picker else self.apps
        count = max(1, min(4, len(rows)))
        lr = QRectF(x0 - 6, y, x1 - x0 + 12, count * APP_ROW)
        if not rows:
            ui.text(QRectF(x0, y, 420, APP_ROW), tr("controls.no_audio_app"), font(8.5), T.text3)
        else:
            def draw(y0):
                yy = y0
                for item in rows:
                    rr = QRectF(lr.left(), yy, lr.width() - 8, APP_ROW - 2)
                    if self.picker:
                        device_id, name = item
                        current = device_id == isl.out_id
                        if current or ui.row_hover(rr):
                            ui.rect(rr, T.layer2 if current else T.hover, 4)
                        if current:
                            ui.rect(QRectF(rr.left(), rr.top() + 8, 3, rr.height() - 16), T.accent, 1.5)
                        ui.text(QRectF(rr.left() + 14, yy, rr.width() - 50, APP_ROW), name,
                                font(8.5), T.text if current else T.text2)
                        if current:
                            ui.glyph(QPointF(rr.right() - 16, rr.center().y()), G["check"], 11, T.accent)
                        ui.row_hit(rr, lambda device_id=device_id: self.choose_output(device_id))
                    else:
                        app = item
                        ui.text(QRectF(rr.left() + 8, yy, 130, APP_ROW), app["name"],
                                font(8.5), T.text if not app["muted"] else T.text3)
                        ui.slider(QRectF(rr.left() + 150, yy + 5, rr.width() - 200, 20),
                                  0 if app["muted"] else app["volume"],
                                  lambda value, app=app: system.Audio.set_app_volume(app, value))
                        ui.icon_button(QPointF(rr.right() - 16, rr.center().y()),
                                       G["mute"] if app["muted"] else G["vol"],
                                       lambda app=app: system.Audio.toggle_app_mute(app), 11, None, 24)
                    yy += APP_ROW
                return yy - y0
            ui.scroll("ctl_list", lr, draw)
        y += count * APP_ROW + 8

        x = x0
        for label, on in ((tr("controls.status.caps_lock"), isl.caps),
                          (tr("controls.status.num_lock"), isl.num)):
            f = font(7.5, W.DemiBold)
            width = ui.tw(label, f) + 26
            rr = QRectF(x, y, width, 24)
            ui.rect(rr, T.layer, 4, T.stroke)
            ui.p.setPen(T.success if on else T.track)
            ui.p.setBrush(T.success if on else T.layer)
            ui.p.drawEllipse(QPointF(rr.left() + 11, rr.center().y()), 3.5, 3.5)
            ui.text(rr.adjusted(19, 0, 0, 0), label, f, T.text if on else T.text2)
            x += width + 6
        if isl.battery:
            percent, plugged = isl.battery
            label = tr("units.percent", value=percent)
            if plugged:
                label += " · " + tr("controls.status.charging")
            f = font(7.5, W.DemiBold)
            width = ui.tw(label, f) + 30
            rr = QRectF(x, y, width, 24)
            ui.rect(rr, T.layer, 4, T.stroke)
            ui.glyph(QPointF(rr.left() + 12, rr.center().y()),
                     G["charging"] if plugged else G["battery"], 12,
                     T.success if plugged else T.text2)
            ui.text(rr.adjusted(22, 0, 0, 0), label, f, T.text)
            x += width + 6
        ui.glyph(QPointF(x + 12, y + 12), G["headphone"] if headphones else G["speaker"],
                 12, T.text2)
        ui.text(QRectF(x + 24, y, x1 - x - 24, 24),
                isl.audio.device_name or tr("controls.no_output"), font(8), T.text2)
