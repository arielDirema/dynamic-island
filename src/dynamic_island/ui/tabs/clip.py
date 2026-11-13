"""Clipboard tab: searchable clipboard history."""
import os

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QImage, QPainterPath, QPixmap

from dynamic_island.core.localization import translate as tr
from dynamic_island.core.utilities.formatting import ago
from dynamic_island.models.clipboard import CATEGORIES, KIND_LABEL_KEYS, TAG_KEYS
from dynamic_island.ui.themes import G, T, W, font

CONTENT_H = 372
ROW = 50


class ClipTab:
    key, label_key, glyph = "clip", "tabs.clip", G["clip"]

    def __init__(self, isl):
        self.isl = isl
        self.category = "all"
        self.sel = 0
        self.thumbs = {}
        self._cache = (None, [])
        self.version = 0
        isl.clip.changed.connect(self._changed)

    def _changed(self):
        self.version += 1

    def height(self):
        return CONTENT_H

    def items(self):
        key = (self.isl.fields.get("clip_search", ""), self.category, self.version)
        if self._cache[0] != key:
            self._cache = (key, self.isl.clip.query(key[0], self.category))
            self.sel = min(self.sel, max(0, len(self._cache[1]) - 1))
        return self._cache[1]

    def _reset(self, *_):
        self.sel = 0
        self.isl.scrolls.pop("clip", None)

    def set_cat(self, key):
        self.category = key
        self._reset()

    def key_event(self, event):
        key = event.key()
        items = self.items()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if items:
                self.isl.paste_item(items[self.sel])
            return True
        if key == Qt.Key.Key_Down:
            self.sel = min(len(items) - 1, self.sel + 1)
            self._ensure()
            return True
        if key == Qt.Key.Key_Up:
            self.sel = max(0, self.sel - 1)
            self._ensure()
            return True
        if key == Qt.Key.Key_Delete and items:
            self.isl.clip.delete(items[self.sel])
            return True
        if key == Qt.Key.Key_Tab:
            keys = [category[0] for category in CATEGORIES]
            self.set_cat(keys[(keys.index(self.category) + 1) % len(keys)])
            return True
        return False

    def _ensure(self):
        current, target = self.isl.scrolls.get("clip", (0.0, 0.0))
        top = self.sel * ROW
        height = CONTENT_H - 80
        if top < target:
            target = top
        elif top + ROW > target + height:
            target = top + ROW - height
        self.isl.scrolls["clip"] = (current, target)

    def paint(self, ui, cr):
        isl = self.isl
        x0, x1 = cr.left() + 16, cr.right() - 16
        ui.field(QRectF(x0, cr.top(), x1 - x0, 32), "clip_search",
                 tr("clipboard.search_placeholder"), glyph=G["search"], on_change=self._reset,
                 on_submit=lambda text: (isl.paste_item(self.items()[self.sel]) if self.items() else None) or False)
        x, y = x0, cr.top() + 40
        for key, label_key in CATEGORIES:
            label = tr(label_key)
            width = ui.chip_w(label)
            ui.chip(QRectF(x, y, width, 24), label, key == self.category,
                    lambda key=key: self.set_cat(key))
            x += width + 4
        lr = QRectF(cr.left() + 8, cr.top() + 72, cr.width() - 16, cr.height() - 80)
        items = self.items()
        if not items:
            message = tr("clipboard.no_results") if isl.fields.get("clip_search") else tr("clipboard.empty")
            ui.empty(lr, G["clip"], message, tr("clipboard.hint"))
            return

        def draw(y0):
            first = max(0, int((lr.top() - y0) // ROW))
            last = min(len(items), first + int(lr.height() // ROW) + 2)
            for index in range(first, last):
                self.row(ui, QRectF(lr.left(), y0 + index * ROW + 2, lr.width() - 8, ROW - 4),
                         items[index], index)
            return len(items) * ROW
        ui.scroll("clip", lr, draw)

    def thumb(self, item):
        name = item.get("image")
        if name not in self.thumbs:
            image = QImage(self.isl.clip.image_path(item))
            pixmap = None
            if not image.isNull():
                side = min(image.width(), image.height())
                image = image.copy((image.width() - side) // 2, (image.height() - side) // 2, side, side)
                pixmap = QPixmap.fromImage(image.scaled(72, 72, Qt.AspectRatioMode.IgnoreAspectRatio,
                                                        Qt.TransformationMode.SmoothTransformation))
            self.thumbs[name] = pixmap
        return self.thumbs[name]

    def row(self, ui, row, item, index):
        isl = self.isl
        hover = ui.row_hover(row)
        selected = isl.focus_field == "clip_search" and index == self.sel
        if hover or selected:
            ui.rect(row, T.layer2 if selected else T.hover, 6)
        if selected:
            ui.rect(QRectF(row.left(), row.top() + 12, 3, row.height() - 24), T.accent, 1.5)
        ui.row_hit(row, lambda: isl.paste_item(item))
        kind = item["kind"]
        ib = QRectF(row.left() + 10, row.top() + 6, 34, 34)
        if kind == "image":
            pixmap = self.thumb(item)
            clip = QPainterPath()
            clip.addRoundedRect(ib, 4, 4)
            ui.p.save()
            ui.p.setClipPath(clip, Qt.ClipOperation.IntersectClip)
            if pixmap:
                ui.p.drawPixmap(ib.toRect(), pixmap)
            else:
                ui.p.fillRect(ib, T.layer2)
            ui.p.restore()
        else:
            glyph, color = {"link": (G["link"], T.accent), "email": (G["mail"], T.success),
                            "phone": (G["phone"], T.success), "files": (G["folder"], T.caution)}.get(
                kind, (G["doc"], T.text2))
            ui.rect(ib, T.tint(color, 40), 4)
            ui.glyph(ib.center(), glyph, 14, color)
        tx = row.left() + 54
        tw = row.right() - tx - (96 if hover else 12)
        if kind == "files":
            names = [os.path.basename(path) or path for path in item["files"]]
            title = names[0] + (f"  (+{len(names) - 1})" if len(names) > 1 else "")
        else:
            title = " ".join(item.get("text", "").split())
        ui.text(QRectF(tx, row.top() + 6, tw, 18), title, font(9, W.Medium))
        sub = tr(KIND_LABEL_KEYS.get(kind, "clipboard.kinds.unknown")) + " · " + ago(item["time"])
        if item.get("tags"):
            tags = ", ".join(tr(TAG_KEYS.get(tag, "clipboard.tags.unknown")) for tag in item["tags"])
            sub += " · " + tr("clipboard.contains", tags=tags)
        sx = tx
        if item.get("pinned"):
            ui.glyph(QPointF(tx + 6, row.top() + 33), G["pinned"], 10, T.orange)
            sx += 16
        ui.text(QRectF(sx, row.top() + 25, tw - (sx - tx), 16), sub, font(7.5), T.text2)
        if hover:
            bx = row.right() - 18
            for glyph, fn, color in ((G["delete"], lambda: isl.clip.delete(item), T.critical),
                                     (G["pinned"] if item.get("pinned") else G["pin"],
                                      lambda: isl.clip.toggle_pin(item),
                                      T.orange if item.get("pinned") else None),
                                     (G["copy"], lambda: isl.copy_item(item), None)):
                ui.icon_button(QPointF(bx, row.center().y()), glyph, fn, 12, color, 28)
                bx -= 30
