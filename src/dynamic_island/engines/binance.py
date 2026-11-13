"""Binance portfolio (read-only): Spot + Funding + Earn, valued in USDT,
24-hour change and local history of the total value."""
import hashlib
import hmac
import json
import threading
import time
import urllib.parse
import urllib.error
import urllib.request

from PySide6.QtCore import QObject, Signal

from dynamic_island.core.config.settings import settings

API = "https://api.binance.com"
STABLES = {"USDT", "USDC", "FDUSD", "BUSD", "TUSD", "DAI", "USDP", "USD1"}
XOF_PER_EUR = 655.957  # fixed CFA franc / euro parity


class Binance(QObject):
    updated = Signal()

    def __init__(self):
        super().__init__()
        self.assets = []      # [{asset, amount, spot, funding, earn, price, change, value}]
        self.total = 0.0
        self.change24 = 0.0
        self.eur_usdt = None
        self.error = None
        self.time = 0
        self.loading = False
        self.visible = False
        self._offset = 0
        self._wake = threading.Event()
        threading.Thread(target=self._loop, daemon=True).start()

    @property
    def configured(self):
        c = settings.get("binance", {})
        return bool(c.get("key") and c.get("secret"))

    def set_key(self, key):
        c = dict(settings.get("binance", {}))
        c["key"] = key.strip()
        settings.set("binance", c)
        self.refresh()

    def set_secret(self, secret):
        c = dict(settings.get("binance", {}))
        c["secret"] = secret.strip()
        settings.set("binance", c)
        self.refresh()

    def forget(self):
        settings.set("binance", {})
        self.assets, self.total, self.error = [], 0.0, None
        self.updated.emit()

    @property
    def history(self):
        return settings.get("wallet_hist", [])

    def refresh(self):
        self._wake.set()

    def _public(self, path, params=None):
        url = API + path + ("?" + urllib.parse.urlencode(params) if params else "")
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "DynamicIsland"}), timeout=15) as r:
            return json.loads(r.read().decode())

    def _signed(self, method, path, params=None):
        c = settings.get("binance", {})
        p = dict(params or {})
        p["timestamp"] = int(time.time() * 1000 + self._offset)
        p["recvWindow"] = 10000
        qs = urllib.parse.urlencode(p)
        sig = hmac.new(c["secret"].encode(), qs.encode(), hashlib.sha256).hexdigest()
        url = f"{API}{path}?{qs}&signature={sig}"
        req = urllib.request.Request(url, method=method, headers={"X-MBX-APIKEY": c["key"], "User-Agent": "DynamicIsland"})
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            try:
                msg = json.loads(e.read().decode()).get("msg", str(e))
            except Exception:
                msg = str(e)
            raise RuntimeError(msg)

    def _loop(self):
        while True:
            if self.configured:
                self.loading = True
                self.updated.emit()
                try:
                    self._fetch()
                    self.error = None
                except Exception as e:
                    self.error = str(e)[:160]
                self.loading = False
                self.updated.emit()
            self._wake.wait(60 if self.visible else 300)
            self._wake.clear()

    def _fetch(self):
        srv = self._public("/api/v3/time")["serverTime"]
        self._offset = srv - time.time() * 1000
        hold = {}

        def add(asset, amount, src):
            if amount <= 0:
                return
            if asset.startswith("LD") and len(asset) > 3:  # legacy Earn balances “LDxxx” in Spot
                asset, src = asset[2:], "earn"
            h = hold.setdefault(asset, {"spot": 0.0, "funding": 0.0, "earn": 0.0})
            h[src] += amount

        acc = self._signed("GET", "/api/v3/account", {"omitZeroBalances": "true"})
        for b in acc.get("balances", []):
            add(b["asset"], float(b["free"]) + float(b["locked"]), "spot")
        try:
            for b in self._signed("POST", "/sapi/v1/asset/get-funding-asset"):
                add(b["asset"], float(b["free"]) + float(b["locked"]) + float(b.get("freeze", 0)), "funding")
        except Exception:
            pass
        for path, field in (("/sapi/v1/simple-earn/flexible/position", "totalAmount"),
                            ("/sapi/v1/simple-earn/locked/position", "amount")):
            try:
                rows = self._signed("GET", path, {"size": 100}).get("rows", [])
                for r in rows:
                    add(r["asset"], float(r.get(field, 0)), "earn")
            except Exception:
                pass

        symbols = [a + "USDT" for a in hold if a not in STABLES] + ["EURUSDT", "BTCUSDT"]
        tickers = {}
        for i in range(0, len(symbols), 80):
            chunk = symbols[i:i + 80]
            try:
                for t in self._public("/api/v3/ticker/24hr", {"symbols": json.dumps(chunk, separators=(",", ":"))}):
                    tickers[t["symbol"]] = t
            except Exception:
                for s in chunk:  # one invalid symbol fails the batch: retry them one by one
                    try:
                        t = self._public("/api/v3/ticker/24hr", {"symbol": s})
                        tickers[t["symbol"]] = t
                    except Exception:
                        pass
        btc = float(tickers["BTCUSDT"]["lastPrice"]) if "BTCUSDT" in tickers else None
        self.eur_usdt = float(tickers["EURUSDT"]["lastPrice"]) if "EURUSDT" in tickers else None
        assets = []
        for a, h in hold.items():
            amount = h["spot"] + h["funding"] + h["earn"]
            if a in STABLES:
                price, change = 1.0, 0.0
            elif a + "USDT" in tickers:
                t = tickers[a + "USDT"]
                price, change = float(t["lastPrice"]), float(t["priceChangePercent"])
            else:
                try:
                    t = self._public("/api/v3/ticker/24hr", {"symbol": a + "BTC"})
                    price, change = float(t["lastPrice"]) * (btc or 0), float(t["priceChangePercent"])
                except Exception:
                    price, change = 0.0, 0.0
            assets.append(dict(h, asset=a, amount=amount, price=price, change=change, value=amount * price))
        assets.sort(key=lambda x: -x["value"])
        total = sum(a["value"] for a in assets)
        prev = sum(a["value"] / (1 + a["change"] / 100) for a in assets if a["value"])
        self.assets = assets
        self.total = total
        self.change24 = (total - prev) / prev * 100 if prev else 0.0
        self.time = time.time()
        hist = [h for h in self.history if time.time() - h[0] < 30 * 86400]
        if not hist or time.time() - hist[-1][0] > 3000:
            hist.append([time.time(), round(total, 2)])
            settings.set("wallet_hist", hist[-800:])

    def to_xof(self, usdt):
        if not self.eur_usdt:
            return None
        return usdt / self.eur_usdt * XOF_PER_EUR

    def to_eur(self, usdt):
        return usdt / self.eur_usdt if self.eur_usdt else None
