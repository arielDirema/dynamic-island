"""Launcher tab: application search, favorites, groups, recent apps,
custom shortcuts, PowerShell and Python scripts."""
import re
import time
import webbrowser

from PySide6.QtCore import QPointF, QRectF, Qt

from dynamic_island.core.localization import translate as tr
from dynamic_island.ui.components.drawing import CENTER, RIGHT
from dynamic_island.ui.themes import G, T, W, font

CONTENT_H = 372
STOP, MINI, APP, APPS = chr(0xE71A), chr(0xE921), chr(0xE71D), chr(0xE7C4)
KIND_KEYS = {
    "app": "launcher.kinds.app",
    "uwp": "launcher.kinds.uwp",
    "url": "launcher.kinds.url",
    "folder": "launcher.kinds.folder",
    "file": "launcher.kinds.file",
    "ps": "launcher.kinds.ps",
    "py": "launcher.kinds.py",
}
KIND_G = {
    "url": G["globe"], "folder": G["folder"], "file": G["doc"], "ps": G["terminal"],
    "py": G["code"], "uwp": "\uE71D", "app": "\uE71D",
}


class LauncherTab:
    key, label_key, glyph = "launcher", "tabs.launcher", "\uE8FC"

    def __init__(self, isl):
        self.isl = isl
        self.sel = 0
        self.view = "home"
        self.confirm_kill = None

    def height(self):
        return CONTENT_H

    def results(self):
        query = self.isl.fields.get("launch_search", "").strip()
        if not query or query.startswith(("+", ">", "ps:", "py:")):
            return []
        return self.isl.launcher.search(query, 10)

    def set_view(self, view):
        self.view = view
        self.sel = 0
        self.isl.launcher.running_visible = view == "running"
        if view == "running":
            self.isl.launcher.refresh_running()

    def running_filtered(self):
        query = self.isl.fields.get("launch_search", "").strip().lower()
        apps = self.isl.launcher.running
        if not query:
            return apps
        return [group for group in apps
                if query in group["name"].lower()
                or any(query in window["title"].lower() for window in group["windows"])]

    def _submit(self, text):
        launcher = self.isl.launcher
        value = text.strip()
        if self.view == "running":
            apps = self.running_filtered()
            if apps:
                self.show(apps[min(self.sel, len(apps) - 1)]["windows"][0]["hwnd"])
                return True
            return False
        lowered = value.lower()
        if value.startswith("+"):
            result = launcher.parse_add(value)
            self.isl.show_alert("launch",
                                tr("launcher.added") if result else tr("launcher.add_failed"),
                                (result or {}).get("name", value),
                                T.success if result else T.critical, G["add"])
            return result is not None
        if value.startswith(">") or lowered.startswith("ps:"):
            launcher.run_powershell(re.sub(r"^(ps:|>)\s*", "", value, flags=re.I))
            return True
        if lowered.startswith("py:"):
            launcher.launch({"name": value, "target": value, "kind": "py"})
            return True
        if re.match(r"^(https?://|www\.)\S+$", value) or (
            re.match(r"^[\w-]+(\.[\w-]+)+(/\S*)?$", value) and " " not in value
        ):
            webbrowser.open(value if value.startswith("http") else "https://" + value)
            self.isl.close_island(restore_focus=False)
            return True
        results = self.results()
        if results:
            self.run(results[min(self.sel, len(results) - 1)])
            return True
        return False

    def key_event(self, event):
        results = self.running_filtered() if self.view == "running" else self.results()
        if event.key() == Qt.Key.Key_Down and results:
            self.sel = min(len(results) - 1, self.sel + 1)
            return True
        if event.key() == Qt.Key.Key_Up and results:
            self.sel = max(0, self.sel - 1)
            return True
        return False

    def run(self, item):
        if self.isl.launcher.launch(item):
            if item.get("kind") != "ps":
                self.isl.close_island(restore_focus=False)
            self.isl.fields["launch_search"] = ""

    def paint(self, ui, cr):
        isl = self.isl
        x0, x1 = cr.left() + 16, cr.right() - 16
        placeholder = tr("launcher.filter_placeholder") if self.view == "running" else \
            tr("launcher.search_placeholder")
        ui.field(QRectF(x0, cr.top(), x1 - x0, 32), "launch_search", placeholder,
                 on_submit=self._submit, glyph=G["search"],
                 on_change=lambda *_: setattr(self, "sel", 0))
        count = len(isl.launcher.running)
        running_label = tr("launcher.views.running_count", count=count) if count else \
            tr("launcher.views.running")
        ui.segmented(
            QRectF(x0 - 6, cr.top() + 38, 0, 28),
            [("home", tr("launcher.views.home")), ("running", running_label)],
            self.view, self.set_view, translate_labels=False,
        )
        body = QRectF(cr.left() + 8, cr.top() + 72, cr.width() - 16, cr.height() - 78)
        query = isl.fields.get("launch_search", "").strip()
        if self.view == "running":
            self._running(ui, body)
        elif query:
            self._search(ui, body, query)
        else:
            ui.scroll("launcher", body, lambda y: self._home(ui, body, y))

    def show(self, hwnd):
        self.isl.close_island(restore_focus=False)
        self.isl.launcher.show_window(hwnd)

    def _kill(self, group):
        confirm = self.confirm_kill
        if confirm and confirm[0] == group["key"] and time.time() - confirm[1] < 3:
            self.confirm_kill = None
            self.isl.launcher.kill_app(group)
            self.isl.show_alert("launch", tr("launcher.stopped", name=group["name"]),
                                tr("launcher.forced_close"), T.critical, STOP)
        else:
            self.confirm_kill = (group["key"], time.time())

    def _running(self, ui, body):
        launcher = self.isl.launcher
        apps = self.running_filtered()
        if not apps:
            ui.empty(body, APPS,
                     tr("launcher.no_running") if not launcher.running else tr("launcher.no_results"),
                     tr("launcher.running_hint"))
            return

        def draw(y0):
            x0, x1 = body.left() + 4, body.right() - 12
            y = y0
            for index, group in enumerate(apps):
                r = QRectF(x0, y, x1 - x0, 46)
                window_count = len(group["windows"])
                if ui.visible(r):
                    hover = ui.row_hover(r)
                    selected = index == self.sel and self.isl.focus_field == "launch_search"
                    ui.rect(r, T.layer2 if (hover or selected) else T.layer, 6, T.stroke)
                    if selected:
                        ui.rect(QRectF(r.left(), r.top() + 13, 3, 20), T.accent, 1.5)
                    ui.file_icon(QRectF(r.left() + 12, r.top() + 10, 26, 26), group["exe"], APP)
                    confirming = bool(self.confirm_kill and self.confirm_kill[0] == group["key"]
                                      and time.time() - self.confirm_kill[1] < 3)
                    right = 136 if (hover or confirming) else 70
                    ui.text(QRectF(r.left() + 48, r.top() + 5, r.width() - 56 - right, 18),
                            group["name"], font(9.5, W.DemiBold))
                    subtitle = (group["windows"][0]["title"] if window_count == 1
                                else tr("launcher.window_count", count=window_count))
                    ui.text(QRectF(r.left() + 48, r.top() + 24, r.width() - 56 - right, 16),
                            subtitle, font(7.5), T.text3)
                    ui.row_hit(QRectF(r.left(), r.top(), r.width() - right, r.height()),
                               lambda hwnd=group["windows"][0]["hwnd"]: self.show(hwnd))
                    if confirming:
                        ui.button(QRectF(r.right() - 132, r.top() + 9, 122, 28),
                                  tr("launcher.confirm_force_stop"),
                                  lambda group=group: self._kill(group), STOP, accent=True)
                    elif hover:
                        bx = r.right() - 18
                        for glyph, action, color in (
                            (STOP, lambda group=group: self._kill(group), T.critical),
                            (G["close"], lambda group=group: launcher.close_app(group), None),
                            (MINI, lambda group=group: [launcher.minimize_window(window["hwnd"])
                                                        for window in group["windows"]], None),
                            (G["open"], lambda hwnd=group["windows"][0]["hwnd"]: self.show(hwnd), None),
                        ):
                            ui.icon_button(QPointF(bx, r.center().y()), glyph, action, 11, color, 26)
                            bx -= 30
                    else:
                        ui.text(QRectF(r.right() - 76, r.top(), 66, 46),
                                tr("units.megabyte", value=f"{group['mem'] / 2 ** 20:.0f}"),
                                font(7.5), T.text3, RIGHT)
                y += 50
                if window_count > 1:  # each application window (browser windows, documents…)
                    for window in group["windows"]:
                        wr = QRectF(x0 + 30, y, x1 - x0 - 30, 28)
                        if ui.visible(wr):
                            hover = ui.row_hover(wr)
                            if hover:
                                ui.rect(wr, T.hover, 4)
                            ui.rect(QRectF(wr.left() - 12, wr.top() + 13, 6, 1.5), T.stroke2, 0)
                            ui.text(QRectF(wr.left() + 4, wr.top(),
                                           wr.width() - (100 if hover else 70), 28),
                                    window["title"], font(8),
                                    T.text3 if window["min"] else T.text2)
                            if window["min"] and not hover:
                                ui.badge(wr.right() - 64, wr.top() + 6, tr("launcher.minimized"),
                                         T.text3)
                            ui.row_hit(QRectF(wr.left(), wr.top(),
                                              wr.width() - (90 if hover else 0), wr.height()),
                                       lambda hwnd=window["hwnd"]: self.show(hwnd))
                            if hover:
                                bx = wr.right() - 14
                                for glyph, action in (
                                    (G["close"], lambda hwnd=window["hwnd"]: launcher.close_window(hwnd)),
                                    (MINI, lambda hwnd=window["hwnd"]: launcher.minimize_window(hwnd)),
                                    (G["open"], lambda hwnd=window["hwnd"]: self.show(hwnd)),
                                ):
                                    ui.icon_button(QPointF(bx, wr.center().y()), glyph, action, 10, None, 22)
                                    bx -= 26
                        y += 30
                    y += 4
            ui.text(QRectF(x0, y + 2, x1 - x0, 16), tr("launcher.footer_help"), font(7), T.text3)
            return y - y0 + 22
        ui.scroll("running", body, draw)

    def _icon(self, ui, rect, item):
        if (item.get("kind") in ("app", "folder", "file")
                or (item.get("kind") == "py"
                    and not item["target"].lower().startswith("py:"))):
            ui.file_icon(rect, item["target"], KIND_G.get(item.get("kind")))
        else:
            ui.rect(rect, T.tint(T.accent, 40), 6)
            ui.glyph(rect.center(), KIND_G.get(item.get("kind"), "\uE71D"),
                     rect.height() * 0.5, T.accent)

    def _search(self, ui, body, query):
        launcher = self.isl.launcher
        y = body.top()
        x0, x1 = body.left() + 8, body.right() - 8
        if query.startswith("+"):
            ui.wrap(QRectF(x0, y, x1 - x0, 80), tr("launcher.add_help"),
                    font(8.5), T.text2, 4)
            return
        if query.startswith(">") or query.lower().startswith("ps:"):
            ui.text(QRectF(x0, y, x1 - x0, 20), tr("launcher.ps_help"), font(8.5), T.text2)
            ui.text(QRectF(x0, y + 22, x1 - x0, 20),
                    re.sub(r"^(ps:|>)\s*", "", query, flags=re.I), font(9, W.DemiBold))
            self._output(ui, QRectF(x0, y + 52, x1 - x0, body.bottom() - y - 52))
            return
        results = self.results()
        if not results:
            ui.empty(body, G["search"], tr("launcher.no_apps"), tr("launcher.no_apps_hint"))
            return
        favorites = {item["target"] for item in launcher.items}
        for index, item in enumerate(results):
            r = QRectF(body.left(), y, body.width(), 38)
            selected = index == self.sel
            hover = ui.hovering(r)
            if selected or hover:
                ui.rect(r, T.layer2 if selected else T.hover, 6)
            if selected:
                ui.rect(QRectF(r.left(), r.top() + 10, 3, 18), T.accent, 1.5)
            self._icon(ui, QRectF(r.left() + 12, r.top() + 7, 24, 24), item)
            ui.text(QRectF(r.left() + 46, r.top(), r.width() - 180, 38), item["name"],
                    font(9.5, W.Medium))
            ui.text(QRectF(r.right() - 170, r.top(), 120, 38),
                    tr(KIND_KEYS.get(item.get("kind"), "launcher.kinds.unknown")),
                    font(7.5), T.text3, RIGHT)
            ui.hit(r, lambda item=item: self.run(item))
            favorite = item["target"] in favorites
            ui.icon_button(QPointF(r.right() - 22, r.center().y()),
                           G["star_on"] if favorite else G["star"],
                           (lambda item=item: launcher.add_app_favorite(item)) if not favorite
                           else (lambda: None),
                           12, T.caution if favorite else None, 26)
            y += 40

    def _home(self, ui, body, y0):
        launcher = self.isl.launcher
        x0, x1 = body.left() + 8, body.right() - 12
        y = y0
        ui.section(x0, y, x1 - x0, tr("launcher.favorites"), tr("launcher.add_shortcut"),
                   lambda: self._prefill("+ "))
        y += 24
        items = launcher.items
        if not items:
            ui.text(QRectF(x0, y, x1 - x0, 18), tr("launcher.favorites_hint"), font(8), T.text3)
            y += 26
        columns, gap = 7, 6
        column_width = (x1 - x0 - gap * (columns - 1)) / columns
        for index, item in enumerate(items):
            r = QRectF(x0 + (index % columns) * (column_width + gap),
                       y + (index // columns) * 74, column_width, 68)
            if ui.visible(r):
                hover = ui.row_hover(r)
                ui.rect(r, T.layer2 if hover else T.layer, 6, T.stroke)
                self._icon(ui, QRectF(r.center().x() - 14, r.top() + 9, 28, 28), item)
                ui.text(QRectF(r.left() + 4, r.top() + 42, r.width() - 8, 18),
                        item["name"], font(7.5), T.text, CENTER)
                ui.row_hit(r, lambda item=item: self.run(item))
                if hover:
                    ui.icon_button(QPointF(r.right() - 10, r.top() + 10), G["close"],
                                   lambda item=item: launcher.remove_item(item), 8, None, 18)
        if items:
            y += ((len(items) - 1) // columns + 1) * 74 + 4
        ui.section(x0, y, x1 - x0, tr("launcher.groups"), tr("launcher.create_group"),
                   lambda: self._prefill("+ group "))
        y += 24
        if not launcher.groups:
            ui.text(QRectF(x0, y, x1 - x0, 18), tr("launcher.groups_hint"), font(8), T.text3)
            y += 26
        items_by_id = {item["id"]: item for item in items}
        for group in launcher.groups:
            r = QRectF(x0, y, x1 - x0, 36)
            if ui.visible(r):
                ui.card(r)
                ui.glyph(QPointF(r.left() + 18, r.center().y()), "\uE8A9", 13, T.accent)
                ui.text(QRectF(r.left() + 36, r.top(), 140, 36), group["name"],
                        font(9, W.DemiBold))
                x = r.left() + 180
                for item_id in group["items"][:8]:
                    if item_id in items_by_id:
                        self._icon(ui, QRectF(x, r.top() + 8, 20, 20), items_by_id[item_id])
                        x += 24
                ui.button(QRectF(r.right() - 104, r.top() + 5, 70, 26), tr("common.start"),
                          lambda group=group: (launcher.run_group(group),
                                               self.isl.close_island(restore_focus=False)),
                          G["play"], accent=True)
                ui.icon_button(QPointF(r.right() - 16, r.center().y()), G["delete"],
                               lambda group=group: launcher.remove_group(group), 11,
                               T.critical, 24)
            y += 40
        y += 4
        ui.section(x0, y, x1 - x0, tr("launcher.recently_used"))
        y += 24
        recent = launcher.recent_apps[:7]
        if not recent:
            ui.text(QRectF(x0, y, x1 - x0, 18), tr("common.loading"), font(8), T.text3)
            y += 24
        for index, item in enumerate(recent):
            r = QRectF(x0 + index * (column_width + gap), y, column_width, 68)
            if ui.visible(r):
                hover = ui.row_hover(r)
                ui.rect(r, T.layer2 if hover else T.layer, 6, T.stroke)
                self._icon(ui, QRectF(r.center().x() - 14, r.top() + 9, 28, 28), item)
                ui.text(QRectF(r.left() + 4, r.top() + 42, r.width() - 8, 18),
                        item["name"], font(7.5), T.text, CENTER)
                ui.row_hit(r, lambda item=item: self.run(item))
        if recent:
            y += 76
        if launcher.last_output:
            y += 4
            y += self._output(ui, QRectF(x0, y, x1 - x0, 140))
        return y - y0 + 6

    def _output(self, ui, r):
        output = self.isl.launcher.last_output
        if not output:
            return 0
        ui.card(r)
        color = T.caution if output["ok"] is None else (
            T.success if output["ok"] else T.critical
        )
        ui.glyph(QPointF(r.left() + 16, r.top() + 15), G["terminal"], 11, color)
        ui.text(QRectF(r.left() + 30, r.top() + 4, r.width() - 110, 22),
                "PS> " + output["cmd"], font(8, W.DemiBold))
        ui.icon_button(QPointF(r.right() - 44, r.top() + 15), G["copy"],
                       lambda: self.isl.copy_text(output["out"]), 10, None, 22)
        ui.icon_button(QPointF(r.right() - 18, r.top() + 15), G["close"],
                       lambda: setattr(self.isl.launcher, "last_output", None), 10, None, 22)
        lines = output["out"].splitlines()[-int((r.height() - 34) // 15):]
        f = font(7.5)
        for index, line in enumerate(lines):
            ui.text(QRectF(r.left() + 12, r.top() + 28 + index * 15, r.width() - 24, 15),
                    line, f, T.text2)
        return r.height() + 6

    def _prefill(self, text):
        self.isl.fields["launch_search"] = text
        self.isl.focus("launch_search")
