"""Smartphone interaction:
- local HTTPS server (Wi-Fi only, secret token) + companion web page opened by QR code:
  file transfer PC ⇄ phone, text/clipboard sending, remote control, phone battery;
- phone notifications and calls read from Phone Link."""
import asyncio
import datetime as dt
import html
import json
import os
import re
import secrets
import socket
import ssl
import subprocess
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PySide6.QtCore import QObject, Signal

from dynamic_island.core.config import paths
from dynamic_island.core.config.settings import settings
from dynamic_island.core.localization import current_language, get_localization, translate as tr
from dynamic_island.engines.files import DOWNLOADS

APPDATA = paths.APPDATA
PORT = 8765
RECV_DIR = os.path.join(DOWNLOADS, "Téléphone")  # keep the historical folder name for existing files

PAGE = paths.resource("resources", "phone_page.html")
PHONE_LINK_IDS = ("yourphone", "phonelink", "phone link", "lien avec windows", "lien mobile", "liaison mobile")  # French names are legacy app labels
CALL_RE = re.compile(r"appel entrant|incoming call|appel de|is calling|vous appelle", re.I)


def render_page() -> str:
    """Render the companion page with the active language and its translations."""
    language = current_language()
    info = get_localization().language_info
    with open(PAGE, encoding="utf-8") as handle:
        page = handle.read()

    def replace(match):
        return html.escape(tr(match.group(1)), quote=True)

    page = re.sub(r"\{\{([\w.]+)\}\}", replace, page)
    flat = dict(get_localization().flat_catalog("en"))
    flat.update(get_localization().flat_catalog(language))
    web = {
        key: value
        for key, value in flat.items()
        if key.startswith("phone.web.") and isinstance(value, str)
    }
    payload = json.dumps(web, ensure_ascii=False).replace("</", "<\\/")
    script = (
        f"<script>window.I18N_PHONE={payload};"
        f"window.I18N_LOCALE={json.dumps(language)};"
        f"window.I18N_DIR={json.dumps(info.direction)};</script>"
    )
    page = page.replace("</head>", script + "</head>", 1)
    page = page.replace(
        '<html lang="en">',
        f'<html lang="{language}" dir="{info.direction}">',
        1,
    )
    return page


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def ensure_cert(ip):
    """Self-signed certificate (HTTPS required by the phone browser for clipboard and battery)."""
    cert, key = os.path.join(APPDATA, "phone_cert.pem"), os.path.join(APPDATA, "phone_key.pem")
    if os.path.exists(cert) and os.path.exists(key) and settings.get("phone_cert_ip") == ip:
        return cert, key
    import ipaddress
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Dynamic Island")])
    now = dt.datetime.now(dt.timezone.utc)
    c = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(k.public_key())
         .serial_number(x509.random_serial_number()).not_valid_before(now - dt.timedelta(days=1))
         .not_valid_after(now + dt.timedelta(days=3650))
         .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address(ip)),
                                                      x509.DNSName("localhost")]), False)
         .sign(k, hashes.SHA256()))
    os.makedirs(APPDATA, exist_ok=True)
    with open(key, "wb") as f:
        f.write(k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
                                serialization.NoEncryption()))
    with open(cert, "wb") as f:
        f.write(c.public_bytes(serialization.Encoding.PEM))
    settings.set("phone_cert_ip", ip)
    return cert, key


def wifi_qr():
    """Wi-Fi QR text for the current network (WIFI:T:WPA;S:…;P:…;;) or None."""
    try:
        out = subprocess.run(["netsh", "wlan", "show", "interfaces"], capture_output=True, text=True,
                             encoding="cp850", errors="replace", creationflags=0x08000000).stdout
        m = re.search(r"^\s*SSID\s*:\s*(.+)$", out, re.M)
        if not m:
            return None
        ssid = m.group(1).strip()
        prof = subprocess.run(["netsh", "wlan", "show", "profile", f"name={ssid}", "key=clear"], capture_output=True,
                              text=True, encoding="cp850", errors="replace", creationflags=0x08000000).stdout
        pm = re.search(r"(Key Content|Contenu de la cl.)\s*:\s*(.+)", prof)
        pw = pm.group(2).strip() if pm else ""
        esc = lambda s: re.sub(r"([\\;,:\"])", r"\\\1", s)
        return ssid, f"WIFI:T:{'WPA' if pw else 'nopass'};S:{esc(ssid)};P:{esc(pw)};;"
    except Exception:
        return None


class Phone(QObject):
    changed = Signal()
    alert = Signal(str, str, str, str)       # kind, title, subtitle, data
    text_received = Signal(str)              # text received from the phone → PC clipboard
    remote = Signal(str, str)                # action, argument
    message = Signal(str)                    # full text of a phone notification (SMS…)

    def __init__(self, files):
        super().__init__()
        self.files = files
        self.server = None
        self.ip = lan_ip()
        self.token = settings.get("phone_token") or secrets.token_urlsafe(12)
        settings.set("phone_token", self.token)
        self.device = None          # {model, battery, charging, seen}
        self.outbox = []            # texts sent to the phone
        self.notifications = []     # phone notifications (Phone Link)
        self.notif_ok = None
        self.sync_clip = settings.get("phone_sync_clip", False)
        self._seen_notifs = set()
        self._first_notif = True
        threading.Thread(target=self._notif_thread, daemon=True).start()
        if settings.get("phone_server", False):
            self.start()

    @property
    def running(self):
        return self.server is not None

    @property
    def url(self):
        return f"https://{self.ip}:{PORT}/?t={self.token}"

    def start(self):
        if self.server:
            return True
        self.ip = lan_ip()
        try:
            cert, key = ensure_cert(self.ip)
            srv = ThreadingHTTPServer(("0.0.0.0", PORT), self._handler())
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(cert, key)
            srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
            srv.daemon_threads = True
            self.server = srv
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            settings.set("phone_server", True)
            self.changed.emit()
            return True
        except Exception as e:
            self.alert.emit("phone_err", tr("phone.server_error"), str(e)[:80], "")
            return False

    def stop(self):
        if self.server:
            srv, self.server = self.server, None
            threading.Thread(target=srv.shutdown, daemon=True).start()
        settings.set("phone_server", False)
        self.changed.emit()

    def check_network(self):
        """If the IP address changes (another Wi-Fi network, hotspot…), restart the server."""
        if time.time() - getattr(self, "_net_t", 0) < 8:
            return
        self._net_t = time.time()
        ip = lan_ip()
        if ip != self.ip:
            self.ip = ip
            if self.server:
                srv, self.server = self.server, None
                srv.shutdown()
                srv.server_close()
                self.start()
            self.changed.emit()

    def new_token(self):
        self.token = secrets.token_urlsafe(12)
        settings.set("phone_token", self.token)
        self.device = None
        self.changed.emit()

    def set_sync_clip(self, on):
        self.sync_clip = on
        settings.set("phone_sync_clip", on)

    def push_text(self, text, kind="text"):
        text = text.strip()
        if not text:
            return False
        self.outbox.insert(0, {"id": secrets.token_hex(4), "text": text[:20000], "kind": kind, "ts": time.time()})
        self.outbox = self.outbox[:30]
        self.changed.emit()
        return True

    @property
    def connected(self):
        return bool(self.device and time.time() - self.device["seen"] < 60)

    def _handler(self):
        phone = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _auth(self, q):
                tok = self.headers.get("X-Token") or q.get("t", [""])[0]
                return secrets.compare_digest(tok, phone.token)

            def _send(self, code, body=b"", ctype="application/json", extra=None):
                if isinstance(body, (dict, list)):
                    body = json.dumps(body).encode()
                elif isinstance(body, str):
                    body = body.encode()
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                for k, v in (extra or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                u = urllib.parse.urlparse(self.path)
                q = urllib.parse.parse_qs(u.query)
                if not self._auth(q):
                    return self._send(403, tr("phone.invalid_link"), "text/plain; charset=utf-8")
                if u.path == "/":
                    return self._send(200, render_page(), "text/html; charset=utf-8")
                if u.path == "/api/poll":
                    since = float(q.get("since", ["0"])[0])
                    shelf = [{"i": i, "name": os.path.basename(p), "size": os.path.getsize(p) if os.path.isfile(p) else 0}
                             for i, p in enumerate(phone.files.shelf) if os.path.isfile(p)]
                    return self._send(200, {"texts": [t for t in phone.outbox if t["ts"] > since][:30],
                                            "files": shelf, "now": time.time(), "pc": socket.gethostname(),
                                            "lang": current_language()})
                if u.path == "/f":
                    i = int(q.get("i", ["-1"])[0])
                    shelf = [p for p in phone.files.shelf if os.path.isfile(p)]
                    if not 0 <= i < len(shelf):
                        return self._send(404, b"")
                    p = shelf[i]
                    size = os.path.getsize(p)
                    name = urllib.parse.quote(os.path.basename(p))
                    self.send_response(200)
                    self.send_header("Content-Type", "application/octet-stream")
                    self.send_header("Content-Length", str(size))
                    self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{name}")
                    self.end_headers()
                    with open(p, "rb") as f:
                        while chunk := f.read(1 << 16):
                            self.wfile.write(chunk)
                    return
                self._send(404, b"")

            def do_POST(self):
                u = urllib.parse.urlparse(self.path)
                q = urllib.parse.parse_qs(u.query)
                if not self._auth(q):
                    return self._send(403, b"")
                n = int(self.headers.get("Content-Length", "0"))
                if u.path == "/api/upload":
                    name = os.path.basename(q.get("name", [tr("phone.file_fallback")])[0]) or tr("phone.file_fallback")
                    os.makedirs(RECV_DIR, exist_ok=True)
                    path = os.path.join(RECV_DIR, name)
                    base, ext = os.path.splitext(path)
                    k = 1
                    while os.path.exists(path):
                        path = f"{base} ({k}){ext}"
                        k += 1
                    left = n
                    with open(path, "wb") as f:
                        while left > 0:
                            chunk = self.rfile.read(min(1 << 16, left))
                            if not chunk:
                                break
                            f.write(chunk)
                            left -= len(chunk)
                    phone.files.add_to_shelf([path])
                    phone.alert.emit("phone_file", tr("phone.file_received"), os.path.basename(path), path)
                    return self._send(200, {"ok": True})
                data = json.loads(self.rfile.read(n) or b"{}")
                if u.path == "/api/state":
                    ua = self.headers.get("User-Agent", "")
                    match = re.search(r"Android [\d.]+; ([^;)]+)", ua) or re.search(r"(iPhone|iPad)", ua)
                    model = (match.group(1).replace(" Build", "").strip() if match else tr("phone.phone"))
                    if model in ("K",):
                        model = "Android"
                    phone.device = {"model": model, "battery": data.get("battery"), "charging": data.get("charging"),
                                    "seen": time.time()}
                    phone.changed.emit()
                    return self._send(200, {"ok": True})
                if u.path == "/api/text":
                    txt = str(data.get("text", ""))[:20000]
                    if txt.strip():
                        phone.text_received.emit(txt)
                    return self._send(200, {"ok": True})
                if u.path == "/api/remote":
                    phone.remote.emit(str(data.get("a", "")), str(data.get("arg", ""))[:2000])
                    return self._send(200, {"ok": True})
                self._send(404, b"")
        return H

    def _notif_thread(self):
        asyncio.run(self._notif_loop())

    async def _notif_loop(self):
        try:
            from winrt.windows.ui.notifications import KnownNotificationBindings, NotificationKinds
            from winrt.windows.ui.notifications.management import UserNotificationListener
            lst = UserNotificationListener.current
            st = await lst.request_access_async()
            self.notif_ok = int(st) == 1
        except Exception:
            self.notif_ok = False
            return
        while True:
            try:
                ns = await lst.get_notifications_async(NotificationKinds.TOAST)
                items = []
                for n in ns:
                    try:
                        ai = n.app_info
                        name = ai.display_info.display_name if ai else ""
                        aumid = (ai.app_user_model_id if ai else "") or ""
                        if not any(k in (name + " " + aumid).lower() for k in PHONE_LINK_IDS):
                            continue
                        b = n.notification.visual.get_binding(KnownNotificationBindings.toast_generic)
                        texts = [t.text for t in b.get_text_elements()] if b else []
                        texts = [t for t in texts if t]
                        ts = n.creation_time.timestamp() if n.creation_time else time.time()
                        items.append({"id": n.id, "title": texts[0] if texts else name,
                                      "body": " · ".join(texts[1:3]), "ts": ts, "full": " ".join(texts),
                                      "call": bool(CALL_RE.search(" ".join(texts)))})
                    except Exception:
                        continue
                items.sort(key=lambda x: -x["ts"])
                for it in items:
                    if it["id"] not in self._seen_notifs:
                        self._seen_notifs.add(it["id"])
                        if time.time() - it["ts"] < 3 * 86400:
                            self.message.emit(it["full"])
                        if not self._first_notif and time.time() - it["ts"] < 120:
                            kind = "phone_call" if it["call"] else "phone_notif"
                            self.alert.emit(kind, it["title"], it["body"], "")
                self._first_notif = False
                if items != self.notifications:
                    self.notifications = items[:30]
                    self.changed.emit()
            except Exception:
                pass
            await asyncio.sleep(2)
