"""Files tab: shelf (drag and drop), downloads, recent files and favorite folders."""
import os
import time

from PySide6.QtCore import QPointF, QRectF

from dynamic_island.core.localization import translate as tr
from dynamic_island.core.utilities.formatting import ago, fmt_dur, human
from dynamic_island.engines.files import DOWNLOADS
from dynamic_island.ui.components.drawing import CENTER, RIGHT
from dynamic_island.ui.themes import G, T, W, font

CONTENT_H = 372
VIEWS = [
    ("shelf", "tabs.files.views.shelf"),
    ("downloads", "tabs.files.views.downloads"),
    ("recent", "tabs.files.views.recent"),
    ("favorites", "tabs.files.views.favorites"),
]


class FilesTab:
    key, label_key, glyph = "files", "tabs.files", G["folder"]

    def __init__(self, isl):
        self.isl = isl
        self.view = "shelf"
        self.pick = None   # "copy" | "move": destination picker mode

    def height(self):
        return CONTENT_H

    def set_view(self, view):
        self.view = view
        self.pick = None

    def paint(self, ui, cr):
        x0 = cr.left() + 16
        ui.segmented(QRectF(x0 - 6, cr.top(), 0, 30), VIEWS, self.view, self.set_view)
        count = len(self.isl.files.downloads)
        if count:
            fa = font(8.5, W.DemiBold)
            bx = (x0 - 6 + ui.tw(tr(VIEWS[0][1]), fa) + 22 + 2
                  + ui.tw(tr(VIEWS[1][1]), fa) + 16)
            ui.badge(bx, cr.top() + 2, str(count), T.accent)
        body = QRectF(cr.left() + 16, cr.top() + 38, cr.width() - 32, cr.height() - 46)
        getattr(self, "_" + self.view)(ui, body)

    def file_row(self, ui, x0, x1, y, path, subtitle, actions, height=40):
        r = QRectF(x0, y, x1 - x0, height)
        if not ui.visible(r):
            return y + height + 2
        hover = ui.row_hover(r)
        if hover:
            ui.rect(r, T.hover, 6)
        ui.file_icon(QRectF(r.left() + 8, r.top() + (height - 26) / 2, 26, 26), path)
        right = 10 + (len(actions) * 30 if hover else 0)
        ui.text(QRectF(r.left() + 44, r.top() + 3, r.width() - 50 - right, 18),
                os.path.basename(path.rstrip("\\")) or path, font(9, W.Medium))
        ui.text(QRectF(r.left() + 44, r.top() + 20, r.width() - 50 - right, 16), subtitle,
                font(7.5), T.text3)
        ui.drag_row(QRectF(r.left(), r.top(), r.width() - right, height), [path],
                    lambda path=path: self.isl.files.open(path))
        if hover:
            bx = r.right() - 18
            for glyph, action, color in actions:
                ui.icon_button(QPointF(bx, r.center().y()), glyph, action, 12, color, 26)
                bx -= 30
        return y + height + 2

    def _destinations(self, ui, body, paths):
        files = self.isl.files
        key = "files.move_count" if self.pick == "move" else "files.copy_count"
        ui.text(QRectF(body.left(), body.top(), body.width(), 20),
                tr(key, count=len(paths)), font(9, W.DemiBold))
        ui.button(QRectF(body.right() - 80, body.top() - 2, 80, 26), tr("common.cancel"),
                  lambda: setattr(self, "pick", None))
        y = body.top() + 30
        for directory in files.favorites:
            y = self.file_row(ui, body.left() - 4, body.right() + 4, y, directory, directory, [])
            ui.hit(QRectF(body.left(), y - 42, body.width(), 40),
                   lambda directory=directory: self._do(paths, directory))
        ui.button(QRectF(body.left(), y + 6, 160, 28), tr("files.other_folder"),
                  lambda: self._other(paths), G["folder"])

    def _do(self, paths, destination):
        self.isl.files.transfer(paths, destination, move=self.pick == "move")
        self.pick = None

    def _other(self, paths):
        from PySide6.QtWidgets import QFileDialog

        mode = self.pick
        self.isl.close_island(restore_focus=False)
        directory = QFileDialog.getExistingDirectory(
            None, tr("files.choose_destination"), os.path.expanduser("~")
        )
        if directory:
            self.isl.files.transfer(paths, directory, move=mode == "move")
        self.pick = None

    def _shelf(self, ui, body):
        files = self.isl.files
        shelf = files.shelf
        if self.pick:
            return self._destinations(ui, body, shelf)
        drop = self.isl.drop_hover
        if not shelf or drop:
            r = body.adjusted(0, 4, 0, -4)
            ui.rect(r, T.tint(T.accent, 30) if drop else T.layer, 8, T.accent if drop else T.stroke2)
            ui.empty(r, G["download"] if "download" in G else "\ue896",
                     tr("files.drop_here") if drop else tr("files.drag_here"),
                     tr("files.shelf_hint"))
            return
        x = body.left()
        for label, glyph, action, danger in (
            (tr("files.copy_to"), G["copy"], lambda: setattr(self, "pick", "copy"), False),
            (tr("files.move_to"), "\ue8de", lambda: setattr(self, "pick", "move"), False),
            (tr("common.clipboard"), G["clip"], lambda: self.isl.copy_files(shelf), False),
            (tr("common.clear"), G["delete"], files.clear_shelf, True),
        ):
            width = ui.tw(label, font(8.5, W.Medium)) + 40
            ui.button(QRectF(x, body.top(), width, 28), label, action, glyph, danger=danger)
            x += width + 6
        ui.text(QRectF(body.right() - 160, body.top(), 160, 28),
                tr("files.item_count", count=len(shelf)), font(8), T.text3, RIGHT)
        lr = QRectF(body.left() - 8, body.top() + 36, body.width() + 16, body.height() - 36)

        def draw(y0):
            y = y0
            for path in shelf:
                size = human(os.path.getsize(path)) if os.path.isfile(path) else tr("common.folder")
                y = self.file_row(ui, lr.left() + 4, lr.right() - 12, y, path,
                                  f"{size} · {os.path.dirname(path)}",
                                  [(G["close"], lambda path=path: files.remove_from_shelf(path), None),
                                   (G["folder"], lambda path=path: files.reveal(path), None),
                                   (G["open"], lambda path=path: files.open(path), None)])
            ui.text(QRectF(lr.left() + 8, y + 4, lr.width() - 16, 16), tr("files.shelf_tip"),
                    font(7.5), T.text3)
            return y - y0 + 26
        ui.scroll("shelf", lr, draw)

    def _downloads(self, ui, body):
        files = self.isl.files

        def draw(y0):
            x0, x1 = body.left(), body.right() - 10
            y = y0
            ui.text(QRectF(x0, y, 300, 18), tr("files.in_progress"), font(8.5, W.DemiBold))
            y += 22
            if not files.downloads:
                ui.text(QRectF(x0, y, 400, 18), tr("files.no_downloads"), font(8), T.text3)
                y += 24
            for download in files.downloads:
                r = QRectF(x0, y, x1 - x0, 58)
                ui.card(r)
                ui.file_icon(QRectF(r.left() + 10, r.top() + 10, 24, 24), download["target"])
                ui.text(QRectF(r.left() + 44, r.top() + 6, r.width() - 160, 18),
                        download["name"], font(9, W.Medium))
                if download["total"]:
                    fraction = download["size"] / download["total"]
                    ui.text(QRectF(r.right() - 110, r.top() + 6, 100, 18),
                            tr("units.percent", value=f"{fraction * 100:.0f}"),
                            font(10, W.DemiBold), T.accent, RIGHT)
                    ui.bar(QRectF(r.left() + 44, r.top() + 28, r.width() - 56, 4), fraction)
                    eta = tr("files.eta_remaining", eta=fmt_dur(download["eta"])) if download["eta"] else ""
                    subtitle = tr("files.download_progress", done=human(download["size"]),
                                  total=human(download["total"]),
                                  speed=tr("units.per_second", value=human(download["speed"])),
                                  eta=eta)
                else:
                    progress = (time.time() * 1.5) % 1
                    ui.bar(QRectF(r.left() + 44, r.top() + 28, r.width() - 56, 4), 0)
                    ui.rect(QRectF(r.left() + 44 + (r.width() - 116) * progress, r.top() + 28, 60, 4),
                            T.accent, 2)
                    if download["speed"] > 0:
                        subtitle = tr("files.progress_unknown", size=human(download["size"]),
                                      speed=tr("units.per_second", value=human(download["speed"])))
                    else:
                        subtitle = tr("files.progress_paused", size=human(download["size"]))
                ui.text(QRectF(r.left() + 44, r.top() + 36, r.width() - 56, 16),
                        f"{download['browser']} · {subtitle}", font(7.5), T.text2)
                y += 64
            y += 6
            ui.text(QRectF(x0, y, 300, 18), tr("files.recently_downloaded"), font(8.5, W.DemiBold))
            ui.link(QRectF(x1 - 120, y, 120, 18), tr("files.open_folder"),
                    lambda: files.open(DOWNLOADS))
            y += 22
            try:
                completed = sorted(
                    (os.path.join(DOWNLOADS, name) for name in os.listdir(DOWNLOADS)
                     if not name.lower().endswith((".crdownload", ".part", ".tmp", ".partial"))),
                    key=os.path.getmtime, reverse=True,
                )[:12]
            except OSError:
                completed = []
            for path in completed:
                size = human(os.path.getsize(path)) if os.path.isfile(path) else tr("common.folder")
                y = self.file_row(ui, x0 - 4, x1, y, path,
                                  f"{size} · {ago(os.path.getmtime(path))}",
                                  [(G["add"], lambda path=path: files.add_to_shelf([path]), None),
                                   (G["folder"], lambda path=path: files.reveal(path), None)])
            return y - y0
        ui.scroll("downloads", QRectF(body.left() - 4, body.top(), body.width() + 8, body.height()), draw)

    def _recent(self, ui, body):
        files = self.isl.files
        items = files.recent
        if not items:
            ui.empty(body, G["history"], tr("files.no_recent"))
            return

        def draw(y0):
            y = y0
            for item in items:
                y = self.file_row(ui, body.left() - 4, body.right() - 10, y, item["path"],
                                  f"{ago(item['mtime'])} · {os.path.dirname(item['path'])}",
                                  [(G["add"], lambda path=item["path"]: files.add_to_shelf([path]), None),
                                   (G["folder"], lambda path=item["path"]: files.reveal(path), None)])
            return y - y0
        ui.scroll("recent_files", QRectF(body.left() - 4, body.top(), body.width() + 8, body.height()), draw)

    def _favorites(self, ui, body):
        files = self.isl.files
        favorites = files.favorites
        ui.button(QRectF(body.left(), body.top(), 190, 28), tr("files.add_folder"),
                  self._add_favorite, G["add"])
        ui.text(QRectF(body.left() + 200, body.top(), body.width() - 200, 28),
                tr("files.shortcut_hint"), font(7.5), T.text3)
        columns = 4
        gap = 8
        column_width = (body.width() - gap * (columns - 1)) / columns
        for index, directory in enumerate(favorites):
            r = QRectF(body.left() + (index % columns) * (column_width + gap),
                       body.top() + 38 + (index // columns) * 78, column_width, 70)
            hover = ui.hovering(r)
            ui.rect(r, T.layer2 if hover else T.layer, 6, T.stroke)
            ui.file_icon(QRectF(r.center().x() - 14, r.top() + 10, 28, 28), directory)
            ui.text(QRectF(r.left() + 6, r.top() + 44, r.width() - 12, 18),
                    os.path.basename(directory.rstrip("\\")) or directory,
                    font(8, W.Medium), T.text, CENTER)
            ui.drag_row(r, [directory], lambda directory=directory: files.open(directory))
            if hover:
                ui.icon_button(QPointF(r.right() - 13, r.top() + 13), G["close"],
                               lambda directory=directory: files.remove_favorite(directory), 9, None, 20)
                ui.icon_button(QPointF(r.left() + 13, r.top() + 13), G["link"],
                               lambda directory=directory: self._shortcut(directory), 9, None, 20)

    def _add_favorite(self):
        from PySide6.QtWidgets import QFileDialog

        self.isl.close_island(restore_focus=False)
        directory = QFileDialog.getExistingDirectory(None, tr("files.favorite_folder"),
                                                     os.path.expanduser("~"))
        if directory:
            self.isl.files.add_favorite(os.path.normpath(directory))

    def _shortcut(self, directory):
        shortcut = self.isl.files.desktop_shortcut(directory)
        self.isl.show_alert("files",
                            tr("files.shortcut_created") if shortcut else tr("files.shortcut_failed"),
                            os.path.basename(directory), T.success if shortcut else T.critical, G["link"])
