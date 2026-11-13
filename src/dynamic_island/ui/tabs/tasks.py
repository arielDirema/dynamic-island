"""Tasks tab: today, all tasks, projects and quick notes."""
from PySide6.QtCore import QPointF, QRectF

from dynamic_island.core.localization import translate as tr
from dynamic_island.core.utilities.formatting import ago
from dynamic_island.models.tasks import PRIORITY_KEYS
from dynamic_island.ui.components.drawing import RIGHT
from dynamic_island.ui.themes import G, T, W, font

CONTENT_H = 372
VIEWS = [
    ("today", "tabs.tasks.views.today"),
    ("all", "tabs.tasks.views.all"),
    ("projects", "tabs.tasks.views.projects"),
    ("notes", "tabs.tasks.views.notes"),
]


class TasksTab:
    key, label_key, glyph = "tasks", "tabs.tasks", G["tasks"]

    def __init__(self, isl):
        self.isl = isl
        self.view = "today"
        self.project = None
        self.show_done = False
        self.editing_note = None

    def height(self):
        return CONTENT_H

    def set_view(self, value):
        self.view = value

    def paint(self, ui, cr):
        x0, x1 = cr.left() + 16, cr.right() - 16
        ui.segmented(QRectF(x0 - 6, cr.top(), 0, 30), VIEWS, self.view, self.set_view)
        body = QRectF(x0, cr.top() + 38, x1 - x0, cr.height() - 46)
        if self.view == "notes":
            self._notes(ui, body)
        else:
            self._tasks(ui, body)

    def _tasks(self, ui, body):
        isl = self.isl
        tasks = isl.tasks
        placeholder = tr("tasks.add_placeholder")
        if self.view == "projects" and self.project:
            placeholder = tr("tasks.add_placeholder_project", project=self.project)
        ui.field(QRectF(body.left(), body.top(), body.width(), 30), "task_add", placeholder,
                 on_submit=self._add, glyph=G["add"])
        y = body.top() + 38
        if self.view == "projects":
            x = body.left()
            for project in [None] + tasks.projects():
                label = tr("common.all") if project is None else "#" + project
                width = ui.chip_w(label)
                if x + width > body.right():
                    break
                ui.chip(QRectF(x, y, width, 22), label, project == self.project,
                        lambda project=project: setattr(self, "project", project))
                x += width + 4
            y += 30
        if self.view != "today":
            ui.text(QRectF(body.right() - 180, body.top() - 36, 130, 28), tr("tasks.show_completed"),
                    font(8), T.text2, RIGHT)
            ui.toggle(QPointF(body.right() - 22, body.top() - 22), self.show_done,
                      lambda: setattr(self, "show_done", not self.show_done))
        items = tasks.query(self.view if self.view == "today" else "all",
                            self.project if self.view == "projects" else None, self.show_done)
        lr = QRectF(body.left() - 8, y, body.width() + 16, body.bottom() - y)
        if not items:
            message = tr("tasks.all_done") if self.view == "today" else tr("tasks.none")
            ui.empty(lr, G["tasks"], message, tr("tasks.hint"))
            return

        def draw(y0):
            yy = y0
            for task in items:
                yy = self.task_row(ui, lr.left() + 4, lr.right() - 12, yy, task)
            return yy - y0
        ui.scroll("tasks_" + self.view, lr, draw)

    def _add(self, text):
        if self.view == "projects" and self.project and "#" not in text:
            text += f" #{self.project}"
        task = self.isl.tasks.quick_add(text)
        return task is not None

    def task_row(self, ui, x0, x1, y, task):
        tasks = self.isl.tasks
        r = QRectF(x0, y, x1 - x0, 40)
        if ui.visible(r):
            hover = ui.row_hover(r)
            ui.rect(r, T.layer2 if hover else T.layer, 6, T.stroke)
            priority = task.get("priority", 0)
            col = {3: T.critical, 2: T.orange, 1: T.accent}.get(priority, T.track)
            ui.checkbox(QPointF(r.left() + 18, r.center().y()), task.get("done"),
                        lambda task=task: tasks.toggle(task), col, round_=True, size=18)
            done = task.get("done")
            tx = r.left() + 36
            right = 12 + (70 if hover else 0)
            f = font(9, W.Medium)
            ui.text(QRectF(tx, r.top() + 3, r.width() - 36 - right, 18), task["title"], f,
                    T.text3 if done else T.text)
            if done:
                width = min(ui.tw(task["title"], f), r.width() - 36 - right)
                ui.p.setPen(T.text3)
                ui.p.drawLine(QPointF(tx, r.top() + 12), QPointF(tx + width, r.top() + 12))
            x = tx
            label, late = tasks.due_label(task)
            meta_y = r.top() + 22
            if label:
                ui.glyph(QPointF(x + 5, meta_y + 8), G["calendar"], 9, T.critical if late else T.text3)
                ui.text(QRectF(x + 13, meta_y, 110, 16), label, font(7.5), T.critical if late else T.text2)
                x += 18 + ui.tw(label, font(7.5)) + 8
            if task.get("remind") and not task.get("reminded"):
                ui.glyph(QPointF(x + 5, meta_y + 8), G["bell"], 9, T.text3)
                x += 16
            if priority:
                x += ui.badge(x, meta_y, tr(PRIORITY_KEYS[priority]), col) + 5
            if task.get("project"):
                x += ui.badge(x, meta_y, "#" + task["project"], T.text2) + 5
            if hover:
                ui.icon_button(QPointF(r.right() - 20, r.center().y()), G["delete"],
                               lambda task=task: tasks.delete(task), 12, T.critical, 26)
                ui.icon_button(QPointF(r.right() - 48, r.center().y()), G["flag"],
                               lambda task=task: tasks.cycle_priority(task), 12, col if priority else None, 26)
        return y + 44

    def _notes(self, ui, body):
        isl = self.isl
        tasks = isl.tasks
        half = (body.width() - 8) / 2
        placeholder = tr("tasks.note_edit_placeholder") if self.editing_note else tr("tasks.note_add_placeholder")
        ui.field(QRectF(body.left(), body.top(), half + 70, 30), "note_add", placeholder,
                 on_submit=self._save_note, glyph=G["note"])
        ui.field(QRectF(body.left() + half + 78, body.top(), half - 70, 30), "note_search",
                 tr("common.search"), glyph=G["search"])
        notes = tasks.query_notes(isl.fields.get("note_search", ""))
        lr = QRectF(body.left() - 8, body.top() + 38, body.width() + 16, body.height() - 38)
        if not notes:
            ui.empty(lr, G["note"], tr("tasks.no_notes"), tr("tasks.notes_pinned_hint"))
            return

        def draw(y0):
            column_width = (lr.width() - 30) / 2
            heights = [y0, y0]
            for note in notes:
                column = 0 if heights[0] <= heights[1] else 1
                x = lr.left() + 8 + column * (column_width + 6)
                y = heights[column]
                lines = min(6, max(1, len(note["text"]) // 34 + note["text"].count("\n") + 1))
                h = 34 + lines * 16
                r = QRectF(x, y, column_width, h)
                if ui.visible(r):
                    hover = ui.row_hover(r)
                    selected = self.editing_note is note
                    ui.rect(r, T.tint(T.caution, 28) if note.get("pinned") else (T.layer2 if hover else T.layer), 6,
                            T.accent if selected else T.stroke)
                    ui.wrap(QRectF(r.left() + 10, r.top() + 8, column_width - 20, lines * 16),
                            note["text"].replace("\n", " "), font(8.5), T.text, lines)
                    ui.text(QRectF(r.left() + 10, r.bottom() - 20, column_width - 80, 16),
                            ago(note.get("mtime", 0)), font(7), T.text3)
                    if note.get("pinned"):
                        ui.glyph(QPointF(r.right() - 14, r.bottom() - 12), G["pinned"], 10, T.orange)
                    ui.row_hit(r, lambda note=note: self._edit_note(note))
                    if hover:
                        bx = r.right() - 14
                        ui.icon_button(QPointF(bx, r.bottom() - 12), G["delete"],
                                       lambda note=note: tasks.delete_note(note), 10, T.critical, 22)
                        ui.icon_button(QPointF(bx - 24, r.bottom() - 12),
                                       G["pinned"] if note.get("pinned") else G["pin"],
                                       lambda note=note: tasks.toggle_pin_note(note), 10,
                                       T.orange if note.get("pinned") else None, 22)
                        ui.icon_button(QPointF(bx - 48, r.bottom() - 12), G["copy"],
                                       lambda note=note: self.isl.copy_text(note["text"]), 10, None, 22)
                heights[column] = y + h + 6
            return max(heights) - y0
        ui.scroll("notes", lr, draw)

    def _edit_note(self, note):
        self.editing_note = note
        self.isl.fields["note_add"] = note["text"]
        self.isl.focus("note_add")

    def _save_note(self, text):
        if self.editing_note is not None:
            self.isl.tasks.edit_note(self.editing_note, text)
            self.editing_note = None
            return True
        return self.isl.tasks.add_note(text) is not None
