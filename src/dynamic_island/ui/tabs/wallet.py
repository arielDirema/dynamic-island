"""Wallet tab: read-only Binance portfolio."""
import hashlib
import time

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainterPath, QPen

from dynamic_island.core.config.settings import settings
from dynamic_island.core.localization import format_currency, format_number, translate as tr
from dynamic_island.core.utilities.formatting import ago
from dynamic_island.ui.components.drawing import CENTER, RIGHT
from dynamic_island.ui.themes import G, T, W, font

CONTENT_H = 372
BINANCE_YELLOW = QColor(240, 185, 11)
XOF_PER_EUR = 655.957
CATEGORY_KEYS = {
    "spot": "wallet.categories.spot",
    "funding": "wallet.categories.funding",
    "earn": "wallet.categories.earn",
}


def money(value, currency="USD"):
    if value is None:
        return "–"
    return format_currency(float(value), currency)


def qty(value):
    return format_number(value, format="#,##0.########")


class WalletTab:
    key, label_key, glyph = "wallet", "tabs.wallet", "\ue8c7"

    def __init__(self, isl):
        self.isl = isl

    def height(self):
        return CONTENT_H

    @property
    def hidden(self):
        return settings.get("wallet_hide", False)

    @property
    def hide_dust(self):
        return settings.get("wallet_hide_dust", True)

    def mask(self, text):
        return "••••••" if self.hidden else text

    def paint(self, ui, cr):
        x0, x1 = cr.left() + 16, cr.right() - 16
        y = cr.top() + 2
        ui.text(QRectF(x0, y, 300, 26), tr("wallet.title"), font(10, W.DemiBold, True))
        bx = x1
        for glyph, action, active in (
            (G["refresh"], self._refresh, self.isl.wallet.loading),
            ("\ued1a" if self.hidden else "\ue7b3",
             lambda: settings.set("wallet_hide", not self.hidden), self.hidden),
        ):
            ui.icon_button(QPointF(bx - 14, y + 13), glyph, action, 12,
                           T.accent if active else None, 26)
            bx -= 30
        wallet = self.isl.wallet
        if wallet.configured and wallet.assets and wallet.to_xof(wallet.total) is not None:
            ui.text(QRectF(x0 + 100, y, bx - x0 - 110, 26),
                    "≈ " + self.mask(money(wallet.to_xof(wallet.total), "XOF")),
                    font(9, W.DemiBold), T.text2, RIGHT)
        body = QRectF(cr.left() + 8, y + 32, cr.width() - 16, cr.bottom() - y - 38)
        ui.scroll("finance", body, lambda yy: self._content(ui, body, yy))

    def _refresh(self):
        self.isl.wallet.refresh()

    def _content(self, ui, body, y0):
        x0, x1 = body.left() + 8, body.right() - 14
        y = self._binance(ui, x0, x1, y0)
        return y - y0 + 6

    def _binance(self, ui, x0, x1, y):
        wallet = self.isl.wallet
        ui.glyph(QPointF(x0 + 8, y + 11), "\ue8c7", 13, BINANCE_YELLOW)
        ui.text(QRectF(x0 + 22, y, 200, 22), "Binance", font(9.5, W.DemiBold))
        if wallet.configured:
            ui.icon_button(QPointF(x1 - 12, y + 11), G["settings"], self._forget_confirm, 11, None, 24)
        y += 28
        if not wallet.configured:
            return self._setup(ui, x0, x1, y)
        if wallet.error and not wallet.assets:
            ui.wrap(QRectF(x0, y, x1 - x0, 50), tr("wallet.binance_error", message=wallet.error),
                    font(8.5), T.critical, 3)
            return y + 56
        if not wallet.assets and wallet.loading:
            ui.text(QRectF(x0, y, x1 - x0, 20), tr("wallet.loading"), font(8.5), T.text3)
            return y + 26
        ui.text(QRectF(x0, y, 300, 34), self.mask(money(wallet.total, "USD")),
                font(18, W.DemiBold, True))
        up = wallet.change24 >= 0
        change = "+" if up else ""
        change += format_number(wallet.change24, format="#,##0.00")
        cw = ui.tw(self.mask(money(wallet.total, "USD")), font(18, W.DemiBold, True))
        ui.badge(x0 + cw + 10, y + 9, tr("wallet.change_24h", value=change),
                 T.success if up else T.critical)
        sub = (self.mask(money(wallet.to_xof(wallet.total), "XOF")) + "  ·  "
               + self.mask(money(wallet.to_eur(wallet.total), "EUR"))
               + (tr("wallet.updated", when=ago(wallet.time)) if wallet.time else ""))
        ui.text(QRectF(x0, y + 32, 420, 16), sub, font(7.5), T.text3)
        history = wallet.history
        graph = QRectF(x1 - 160, y + 4, 160, 38)
        if len(history) > 2:
            values = [point[1] for point in history[-120:]]
            low, high = min(values), max(values)
            path = QPainterPath()
            for index, value in enumerate(values):
                px = graph.left() + graph.width() * index / (len(values) - 1)
                py = graph.bottom() - (graph.height() * (value - low) / (high - low)
                                       if high > low else graph.height() / 2)
                path.moveTo(px, py) if index == 0 else path.lineTo(px, py)
            ui.p.setPen(QPen(T.success if values[-1] >= values[0] else T.critical, 1.6))
            ui.p.setBrush(Qt.BrushStyle.NoBrush)
            ui.p.drawPath(path)
        y += 56
        sums = {"spot": 0.0, "funding": 0.0, "earn": 0.0}
        for asset in wallet.assets:
            for category, source in (("spot", "spot"), ("funding", "funding"), ("earn", "earn")):
                sums[category] += asset[source] * asset["price"]
        x = x0
        for category, value in sums.items():
            if value <= 0:
                continue
            label = f"{tr(CATEGORY_KEYS[category])} {self.mask(money(value, 'USD'))}"
            width = ui.tw(label, font(7.5, W.DemiBold)) + 18
            ui.rect(QRectF(x, y, width, 22), T.layer, 4, T.stroke)
            ui.text(QRectF(x, y, width, 22), label, font(7.5, W.DemiBold), T.text2, CENTER)
            x += width + 6
        ui.text(QRectF(x1 - 150, y, 104, 22),
                tr("wallet.hide_dust", value=money(1, "USD")), font(7.5), T.text2, RIGHT)
        ui.toggle(QPointF(x1 - 22, y + 11), self.hide_dust,
                  lambda: settings.set("wallet_hide_dust", not self.hide_dust))
        y += 30
        assets = [asset for asset in wallet.assets if not (self.hide_dust and asset["value"] < 1)]
        for asset in assets:
            rr = QRectF(x0, y, x1 - x0, 42)
            if ui.visible(rr):
                if ui.row_hover(rr):
                    ui.rect(rr, T.hover, 6)
                digest = int(hashlib.md5(asset["asset"].encode()).hexdigest()[:6], 16)
                color = BINANCE_YELLOW if asset["asset"] == "BNB" else QColor.fromHsv(digest % 360, 150, 230)
                center = QPointF(rr.left() + 20, rr.center().y())
                ui.p.setPen(Qt.PenStyle.NoPen)
                ui.p.setBrush(T.tint(color, 60))
                ui.p.drawEllipse(center, 14, 14)
                ui.text(QRectF(center.x() - 14, center.y() - 14, 28, 28), asset["asset"][:4],
                        font(6.5, W.Bold), color, CENTER)
                ui.text(QRectF(rr.left() + 42, rr.top() + 3, 150, 18), asset["asset"],
                        font(9, W.DemiBold))
                ui.text(QRectF(rr.left() + 42, rr.top() + 21, 170, 16),
                        self.mask(qty(asset["amount"])), font(7.5), T.text3)
                rising = asset["change"] >= 0
                ui.text(QRectF(rr.left() + 200, rr.top() + 3, 120, 18),
                        money(asset["price"], "USD"), font(8.5), T.text2)
                if asset["asset"] not in ("USDT", "USDC", "FDUSD"):
                    change = ("+" if rising else "") + format_number(asset["change"], format="#,##0.00")
                    ui.text(QRectF(rr.left() + 200, rr.top() + 21, 120, 16),
                            tr("wallet.price_change", value=change),
                            font(7.5, W.DemiBold), T.success if rising else T.critical)
                ui.text(QRectF(rr.right() - 140, rr.top() + 3, 132, 18),
                        self.mask(money(asset["value"], "USD")), font(9, W.DemiBold), T.text, RIGHT)
                share = asset["value"] / wallet.total if wallet.total else 0
                ui.bar(QRectF(rr.right() - 100, rr.top() + 27, 92, 3), share, color)
                ui.text(QRectF(rr.right() - 160, rr.top() + 21, 56, 16),
                        tr("units.percent", value=format_number(share * 100, format="#,##0.0")),
                        font(7), T.text3, RIGHT)
            y += 44
        if not assets:
            ui.text(QRectF(x0, y, x1 - x0, 20), tr("wallet.no_assets"), font(8.5), T.text3)
            y += 24
        return y

    def _forget_confirm(self):
        last = getattr(self, "_forget_t", 0)
        if time.time() - last < 3:
            self.isl.wallet.forget()
            self.isl.fields.pop("bn_key", None)
        else:
            self._forget_t = time.time()
            self.isl.show_alert("wallet", tr("wallet.forget_title"), tr("wallet.forget_hint"),
                                T.caution, G["settings"])

    def _setup(self, ui, x0, x1, y):
        wallet = self.isl.wallet
        for step in (tr("wallet.setup.step_1"), tr("wallet.setup.step_2"), tr("wallet.setup.step_3")):
            ui.wrap(QRectF(x0, y, x1 - x0, 34), step, font(8.5), T.text2, 2)
            y += 22
        y += 4
        has_key = bool(settings.get("binance", {}).get("key"))
        ui.field(QRectF(x0, y, x1 - x0, 30), "bn_key",
                 tr("wallet.api_key_saved") if has_key else tr("wallet.api_key"),
                 on_submit=lambda text: wallet.set_key(text) or True, glyph="\ue8d7")
        y += 36
        ui.field(QRectF(x0, y, x1 - x0, 30), "bn_secret", tr("wallet.secret_key"),
                 on_submit=lambda text: wallet.set_secret(text) or True, glyph=G["lock"], secret=True)
        y += 38
        ui.button(QRectF(x0, y, 230, 28), tr("wallet.open_api_management"),
                  lambda: self.isl.open_url(tr("wallet.api_management_url")), G["open"], accent=True)
        if wallet.error:
            ui.text(QRectF(x0 + 240, y, x1 - x0 - 240, 28), wallet.error, font(8), T.critical)
        return y + 36
