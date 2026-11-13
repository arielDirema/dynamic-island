"""Developer tab: open project, Git, GitHub, builds/CI/Jenkins/logs, local servers and projects."""
import os
import time

from PySide6.QtCore import QPointF, QRectF

from dynamic_island.core.config.settings import settings
from dynamic_island.core.localization import translate as tr
from dynamic_island.core.utilities.formatting import ago
from dynamic_island.ui.components.drawing import RIGHT
from dynamic_island.ui.themes import G, T, W, font

CONTENT_H = 372
VIEWS = [
    ("git", "tabs.dev.views.git"),
    ("github", "tabs.dev.views.github"),
    ("builds", "tabs.dev.views.builds"),
    ("servers", "tabs.dev.views.servers"),
    ("projects", "tabs.dev.views.projects"),
]


class DevTab:
    key, label_key, glyph = "dev", "tabs.dev", G["code"]

    def __init__(self, isl):
        self.isl = isl
        self.view = "git"
        self.confirm_kill = None

    def height(self):
        return CONTENT_H

    def set_view(self, view):
        self.view = view
        self.isl.dev.refresh()

    def paint(self, ui, cr):
        dev = self.isl.dev
        x0, x1 = cr.left() + 16, cr.right() - 16
        y = cr.top()
        r = QRectF(x0, y, x1 - x0, 62)
        ui.card(r)
        project = dev.project
        if project:
            ui.glyph(QPointF(r.left() + 20, r.top() + 20), G["code"], 15, T.accent)
            ui.text(QRectF(r.left() + 38, r.top() + 6, 220, 20), project["name"],
                    font(10.5, W.DemiBold))
            details = project.get("ide") or ""
            details += " · " + (project["path"] if project.get("path") else tr("dev.unknown_folder"))
            ui.text(QRectF(r.left() + 38, r.top() + 25, 300, 16), details, font(7.5), T.text3)
            git = dev.git
            x = r.left() + 38
            if git and git.get("branch"):
                ui.glyph(QPointF(x + 5, r.top() + 50), G["branch"], 10, T.text2)
                ui.text(QRectF(x + 13, r.top() + 42, 120, 16), git["branch"],
                        font(8, W.DemiBold), T.text)
                x += 20 + ui.tw(git["branch"], font(8, W.DemiBold)) + 6
                status_key, color = {
                    "clean": ("dev.git.status.clean", T.success),
                    "modified": ("dev.git.status.modified", T.orange),
                    "uncommitted": ("dev.git.status.uncommitted", T.caution),
                }[git["status"]]
                x += ui.badge(x, r.top() + 42, tr(status_key), color) + 5
                if git["changes"]:
                    x += ui.badge(x, r.top() + 42,
                                  tr("dev.file_count", count=git["changes"]), T.text2) + 5
                if git["ahead"]:
                    x += ui.badge(x, r.top() + 42, f"↑{git['ahead']}", T.accent) + 5
                if git["behind"]:
                    x += ui.badge(x, r.top() + 42, f"↓{git['behind']}", T.purple) + 5
            elif git and git.get("error"):
                ui.text(QRectF(x, r.top() + 42, 220, 16), git["error"], font(7.5), T.text3)
            bx = r.right() - 8
            for glyph, action in (
                (G["terminal"], dev.open_terminal),
                (G["folder"], dev.open_folder),
                (G["open"], dev.open_project),
                (G["build"], dev.start_build),
            ):
                ui.icon_button(QPointF(bx - 16, r.top() + 20), glyph, action, 13, size=30)
                bx -= 32
            if dev.git and dev.git.get("repo"):
                ui.icon_button(QPointF(bx - 16, r.top() + 20), G["github"],
                               lambda: self.isl.open_url("https://github.com/" + dev.git["repo"]),
                               13, size=30)
        else:
            ui.glyph(QPointF(r.left() + 20, r.center().y()), G["code"], 15, T.text3)
            ui.text(QRectF(r.left() + 38, r.top() + 10, r.width() - 50, 20),
                    tr("dev.no_ide"), font(10, W.DemiBold))
            ui.text(QRectF(r.left() + 38, r.top() + 30, r.width() - 50, 18),
                    tr("dev.no_ide_hint"), font(7.5), T.text3)
        y += 68
        ui.segmented(QRectF(x0 - 6, y, 0, 28), VIEWS, self.view, self.set_view)
        body = QRectF(cr.left() + 8, y + 34, cr.width() - 16, cr.bottom() - y - 40)
        getattr(self, "_" + self.view)(ui, body)

    def _git(self, ui, body):
        git = self.isl.dev.git
        if not git or not git.get("branch"):
            ui.empty(body, G["branch"], tr("dev.git.no_repository"))
            return

        def draw(y0):
            x0, x1 = body.left() + 8, body.right() - 14
            y = y0
            ui.text(QRectF(x0, y, 220, 18), tr("dev.git.recent_commits"), font(8.5, W.DemiBold))
            y += 22
            for commit, message, when, author in git["commits"]:
                ui.text(QRectF(x0, y, 60, 22), commit, font(8, W.DemiBold), T.accent)
                ui.text(QRectF(x0 + 62, y, x1 - x0 - 200, 22), message, font(8.5))
                ui.text(QRectF(x1 - 136, y, 136, 22), f"{author} · {when}",
                        font(7.5), T.text3, RIGHT)
                y += 24
            if not git["commits"]:
                ui.text(QRectF(x0, y, 300, 20), tr("dev.git.no_commits"), font(8.5), T.text3)
                y += 22
            y += 8
            ui.text(QRectF(x0, y, x1 - x0, 18),
                    tr("dev.git.changes_summary", changes=git["changes"], staged=git["staged"],
                       modified=git["modified"], untracked=git["untracked"]),
                    font(8.5), W.DemiBold)
            y += 22
            for change in git["files"]:
                code, path = change[:2], change[3:]
                color = T.success if code.strip() in ("A", "??") else (
                    T.critical if "D" in code else T.orange
                )
                ui.text(QRectF(x0, y, 26, 20), code.replace(" ", "·"), font(8, W.DemiBold), color)
                ui.text(QRectF(x0 + 30, y, x1 - x0 - 30, 20), path, font(8), T.text2)
                y += 20
            return y - y0 + 6
        ui.scroll("dev_git", body, draw)

    def _github(self, ui, body):
        dev = self.isl.dev
        x0, x1 = body.left() + 8, body.right() - 14
        has_token = bool(settings.get("github_token"))
        if not has_token:
            ui.field(QRectF(x0, body.top(), x1 - x0, 30), "gh_token",
                     tr("dev.github.token_placeholder"),
                     on_submit=lambda text: dev.set_token(text) or True,
                     glyph=G["lock"], secret=True)
            body = QRectF(body.left(), body.top() + 36, body.width(), body.height() - 36)
        if not dev.git or not dev.git.get("repo"):
            ui.empty(body, G["github"], tr("dev.github.no_repository"),
                     tr("dev.github.no_repository_hint"))
            return
        github = dev.gh
        if not github:
            ui.empty(body, G["refresh"], tr("dev.github.loading"),
                     dev.gh_err or dev.git["repo"])
            return

        def section(y, title, items, row):
            ui.text(QRectF(x0, y, 320, 18), f"{title} ({len(items)})", font(8.5, W.DemiBold))
            y += 22
            if not items:
                ui.text(QRectF(x0, y, 300, 18), tr("dev.github.nothing"), font(8), T.text3)
                return y + 24
            for item in items:
                rr = QRectF(x0 - 4, y, x1 - x0 + 8, 26)
                if ui.row_hover(rr):
                    ui.rect(rr, T.hover, 4)
                row(rr, item)
                if item.get("url"):
                    ui.row_hit(rr, lambda url=item["url"]: self.isl.open_url(url))
                y += 28
            return y + 6

        def run_row(rr, run):
            if run["status"] != "completed":
                glyph, color, status = G["refresh"], T.caution, tr("dev.github.status.running")
            elif run["conclusion"] == "success":
                glyph, color, status = G["check"], T.success, tr("dev.github.status.success")
            elif run["conclusion"] in ("failure", "timed_out"):
                glyph, color, status = G["close"], T.critical, tr("dev.github.status.failure")
            else:
                glyph, color, status = G["info"], T.text3, run["conclusion"] or ""
            ui.glyph(QPointF(rr.left() + 12, rr.center().y()), glyph, 11, color)
            ui.text(QRectF(rr.left() + 26, rr.top(), rr.width() - 200, 26),
                    f"{run['name']} — {run['title']}", font(8.5))
            ui.text(QRectF(rr.right() - 170, rr.top(), 164, 26),
                    f"{run['branch']} · {status}", font(7.5), color, RIGHT)

        def pull_row(rr, pull):
            ui.glyph(QPointF(rr.left() + 12, rr.center().y()), G["branch"], 11,
                     T.text3 if pull.get("draft") else T.success)
            ui.text(QRectF(rr.left() + 26, rr.top(), rr.width() - 140, 26),
                    f"#{pull['n']} {pull['title']}", font(8.5))
            ui.text(QRectF(rr.right() - 110, rr.top(), 104, 26), pull["user"],
                    font(7.5), T.text3, RIGHT)

        def issue_row(rr, issue):
            ui.glyph(QPointF(rr.left() + 12, rr.center().y()), G["bug"], 11, T.orange)
            ui.text(QRectF(rr.left() + 26, rr.top(), rr.width() - 160, 26),
                    f"#{issue['n']} {issue['title']}", font(8.5))
            ui.text(QRectF(rr.right() - 130, rr.top(), 124, 26),
                    ", ".join(issue["labels"]) or issue["user"], font(7.5), T.text3, RIGHT)

        def deployment_row(rr, deployment):
            color = {"success": T.success, "failure": T.critical, "error": T.critical,
                     "in_progress": T.caution}.get(deployment["state"], T.text3)
            ui.glyph(QPointF(rr.left() + 12, rr.center().y()), G["rocket"], 11, color)
            ui.text(QRectF(rr.left() + 26, rr.top(), rr.width() - 160, 26),
                    f"{deployment['env']} · {deployment['ref']}", font(8.5))
            ui.text(QRectF(rr.right() - 130, rr.top(), 124, 26), deployment["state"],
                    font(7.5), color, RIGHT)
            deployment["url"] = deployment.get("url")

        def notification_row(rr, notification):
            ui.glyph(QPointF(rr.left() + 12, rr.center().y()), G["bell"], 11, T.accent)
            ui.text(QRectF(rr.left() + 26, rr.top(), rr.width() - 180, 26),
                    notification["title"], font(8.5))
            ui.text(QRectF(rr.right() - 150, rr.top(), 144, 26),
                    notification["repo"].split("/")[-1] + " · " + notification["reason"],
                    font(7.5), T.text3, RIGHT)

        def draw(y0):
            y = y0
            ui.text(QRectF(x0, y, 300, 18), github["repo"], font(9, W.DemiBold), T.accent)
            ui.text(QRectF(x1 - 180, y, 180, 18),
                    tr("dev.github.updated", when=ago(github["time"])), font(7.5), T.text3, RIGHT)
            y += 26
            y = section(y, tr("dev.github.actions"), github["runs"][:6], run_row)
            y = section(y, tr("dev.github.pull_requests"), github["pulls"], pull_row)
            y = section(y, tr("dev.github.issues"), github["issues"], issue_row)
            if github.get("deployments"):
                y = section(y, tr("dev.github.deployments"), github["deployments"], deployment_row)
            if has_token:
                y = section(y, tr("dev.github.notifications"), github["notifications"], notification_row)
            return y - y0
        ui.scroll("dev_gh", body, draw)

    def _builds(self, ui, body):
        dev = self.isl.dev

        def draw(y0):
            x0, x1 = body.left() + 8, body.right() - 14
            y = y0
            build = dev.build
            ui.text(QRectF(x0, y, 300, 22), tr("dev.builds.local_build"), font(8.5, W.DemiBold))
            if build and build.get("running"):
                ui.button(QRectF(x1 - 90, y - 2, 90, 26), tr("common.stop"),
                          dev.stop_build, G["stop"], danger=True)
            else:
                ui.button(QRectF(x1 - 90, y - 2, 90, 26), tr("common.start"),
                          dev.start_build, G["play"], accent=True,
                          enabled=bool(dev.project and dev.project.get("path")))
            y += 30
            if build:
                if build.get("running"):
                    color = T.caution
                    status = tr("dev.builds.running", seconds=int(time.time() - build["start"]))
                elif build.get("ok"):
                    color = T.success
                    status = tr("dev.builds.success", seconds=int(build["end"] - build["start"]))
                else:
                    color = T.critical
                    status = tr("dev.builds.failure", count=len(build["errors"]))
                ui.text(QRectF(x0, y, x1 - x0, 18), f"{build.get('cmd') or ''}  ·  {status}",
                        font(8, W.DemiBold), color)
                y += 22
                lines = build["errors"][-8:] if build["errors"] else build["out"][-4:]
                for line in lines:
                    ui.text(QRectF(x0 + 6, y, x1 - x0 - 6, 18), line, font(7.5),
                            T.critical if build["errors"] else T.text2)
                    y += 18
            else:
                ui.text(QRectF(x0, y, x1 - x0, 18), tr("dev.builds.help"), font(8), T.text3)
                y += 22
            if dev.gh:
                running = [run for run in dev.gh["runs"] if run["status"] != "completed"]
                if running:
                    y += 8
                    ui.text(QRectF(x0, y, 300, 18), tr("dev.builds.ci_running"),
                            font(8.5, W.DemiBold))
                    y += 22
                    for run in running:
                        ui.glyph(QPointF(x0 + 8, y + 10), G["refresh"], 10, T.caution)
                        ui.text(QRectF(x0 + 22, y, x1 - x0 - 22, 20),
                                f"{run['name']} · {run['branch']}", font(8.5))
                        y += 22
            y += 8
            ui.text(QRectF(x0, y, 300, 18), "Jenkins", font(8.5, W.DemiBold))
            y += 22
            jenkins = dev.jenkins
            if not settings.get("jenkins", {}).get("url"):
                ui.field(QRectF(x0, y, x1 - x0, 30), "jenkins_url",
                         tr("dev.builds.jenkins_placeholder"),
                         on_submit=self._set_jenkins, glyph=G["server"])
                y += 38
            elif jenkins and jenkins.get("error"):
                ui.text(QRectF(x0, y, x1 - x0, 18), jenkins["error"], font(8), T.critical)
                y += 22
            elif jenkins:
                for job in jenkins["jobs"][:10]:
                    color_code = job["color"]
                    color = T.success if color_code.startswith("blue") else (
                        T.critical if color_code.startswith("red") else (
                            T.caution if color_code.startswith("yellow") else T.text3
                        )
                    )
                    ui.glyph(QPointF(x0 + 8, y + 10),
                             G["refresh"] if job["building"] else G["build"], 10, color)
                    ui.text(QRectF(x0 + 22, y, x1 - x0 - 160, 20), job["name"],
                            font(8.5))
                    status = tr("dev.builds.in_progress") if job["building"] else (
                        job["result"] or "—"
                    ).lower()
                    if job["number"]:
                        status += f" · #{job['number']}"
                    ui.text(QRectF(x1 - 140, y, 140, 20), status, font(7.5), color, RIGHT)
                    y += 22
            y += 8
            ui.text(QRectF(x0, y, 300, 18), tr("dev.builds.logs"), font(8.5, W.DemiBold))
            y += 22
            if not dev.logs:
                ui.text(QRectF(x0, y, x1 - x0, 18), tr("dev.builds.no_logs"),
                        font(8), T.text3)
                y += 22
            for log in dev.logs[:12]:
                ui.text(QRectF(x0, y, 110, 18), log["file"], font(7.5, W.DemiBold), T.text3)
                ui.text(QRectF(x0 + 112, y, x1 - x0 - 112, 18), log["line"],
                        font(7.5), T.critical)
                y += 18
            return y - y0 + 8
        ui.scroll("dev_builds", body, draw)

    def _set_jenkins(self, text):
        parts = text.split()
        if not parts or not parts[0].startswith("http"):
            return False
        self.isl.dev.set_jenkins(parts[0], parts[1] if len(parts) > 1 else "",
                                 parts[2] if len(parts) > 2 else "")
        return True

    def _servers(self, ui, body):
        dev = self.isl.dev

        def draw(y0):
            x0, x1 = body.left() + 8, body.right() - 14
            y = y0
            ports = [port for port in dev.ports if port["dev"]] or dev.ports[:8]
            ui.text(QRectF(x0, y, 320, 18), tr("dev.servers.active", count=len(ports)),
                    font(8.5, W.DemiBold))
            y += 22
            for port in ports:
                rr = QRectF(x0 - 4, y, x1 - x0 + 8, 30)
                if ui.row_hover(rr):
                    ui.rect(rr, T.hover, 4)
                ui.p.setPen(T.success)
                ui.p.setBrush(T.success)
                ui.p.drawEllipse(QPointF(x0 + 6, y + 15), 3.5, 3.5)
                ui.text(QRectF(x0 + 18, y, 70, 30), f":{port['port']}", font(9, W.DemiBold))
                ui.text(QRectF(x0 + 80, y, 220, 30), f"{port['name']} · PID {port['pid']}",
                        font(8), T.text2)
                confirm = self.confirm_kill == port["pid"]
                ui.button(QRectF(x1 - 174, y + 3, 84, 24), tr("common.open"),
                          lambda port=port: self.isl.open_url(f"http://localhost:{port['port']}"),
                          G["globe"])
                ui.button(QRectF(x1 - 84, y + 3, 84, 24),
                          tr("dev.servers.confirm") if confirm else tr("common.stop"),
                          lambda port=port: self._kill(port["pid"]), G["stop"], danger=True,
                          accent=confirm)
                y += 32
            y += 8
            ui.text(QRectF(x0, y, 300, 18), tr("dev.servers.development_services"),
                    font(8.5, W.DemiBold))
            y += 22
            if not dev.services:
                ui.text(QRectF(x0, y, x1 - x0, 18), tr("dev.servers.none"), font(8), T.text3)
                y += 22
            for service in dev.services:
                running = service["status"] == "running"
                pending = "pending" in service["status"]
                color = T.success if running else (T.caution if pending else T.text3)
                ui.p.setPen(color)
                ui.p.setBrush(color)
                ui.p.drawEllipse(QPointF(x0 + 6, y + 15), 3.5, 3.5)
                ui.text(QRectF(x0 + 18, y, x1 - x0 - 140, 30), service["display"], font(8.5))
                ui.button(QRectF(x1 - 96, y + 3, 96, 24),
                          tr("common.stop") if running else tr("common.start"),
                          lambda service=service: dev.service_toggle(service),
                          G["stop"] if running else G["play"], enabled=not pending)
                y += 32
            ui.text(QRectF(x0, y + 4, x1 - x0, 16), tr("dev.servers.admin_hint"),
                    font(7.5), T.text3)
            return y - y0 + 26
        ui.scroll("dev_servers", body, draw)

    def _kill(self, pid):
        if self.confirm_kill == pid:
            self.confirm_kill = None
            self.isl.dev.kill(pid)
        else:
            self.confirm_kill = pid

    def _projects(self, ui, body):
        dev = self.isl.dev
        favorites = dev.favorites
        recent = dev.recent
        favorite_items = [
            {"name": os.path.basename(path.rstrip("\\")), "path": path,
             "ide": next((item["ide"] for item in recent
                          if os.path.normcase(item["path"]) == os.path.normcase(path)), "VS Code")}
            for path in favorites
        ]
        others = [item for item in recent if item["path"] not in favorites][:25]

        def row(y, item, favorite):
            x0, x1 = body.left() + 8, body.right() - 14
            rr = QRectF(x0 - 4, y, x1 - x0 + 8, 36)
            if ui.visible(rr):
                hover = ui.row_hover(rr)
                if hover:
                    ui.rect(rr, T.hover, 4)
                ui.icon_button(QPointF(x0 + 12, y + 18), G["star_on"] if favorite else G["star"],
                               lambda path=item["path"]: dev.toggle_favorite(path), 11,
                               T.caution if favorite else T.text3, 26)
                ui.text(QRectF(x0 + 30, y + 2, x1 - x0 - 200, 18), item["name"],
                        font(9, W.DemiBold))
                ui.text(QRectF(x0 + 30, y + 18, x1 - x0 - 200, 16),
                        f"{item['ide']} · {item['path']}", font(7.5), T.text3)
                bx = x1 - 4
                for glyph, action in (
                    (G["terminal"], lambda path=item["path"]: dev.open_terminal(path)),
                    (G["open"], lambda path=item["path"], ide=item["ide"]: dev.open_project(path, ide)),
                    (G["code"], lambda path=item["path"], ide=item["ide"]: dev.select_project(path, ide)),
                ):
                    ui.icon_button(QPointF(bx - 14, y + 18), glyph, action, 12, size=28)
                    bx -= 30
                ui.row_hit(QRectF(rr.left() + 26, rr.top(), rr.width() - 126, rr.height()),
                           lambda path=item["path"], ide=item["ide"]: dev.open_project(path, ide))
            return y + 38

        def draw(y0):
            x0 = body.left() + 8
            y = y0
            ui.text(QRectF(x0, y, 300, 18), tr("dev.projects.favorites"), font(8.5, W.DemiBold))
            y += 22
            if not favorite_items:
                ui.text(QRectF(x0, y, 420, 18), tr("dev.projects.favorites_hint"),
                        font(8), T.text3)
                y += 24
            for item in favorite_items:
                y = row(y, item, True)
            y += 8
            ui.text(QRectF(x0, y, 340, 18), tr("dev.projects.recent"), font(8.5, W.DemiBold))
            y += 22
            for item in others:
                y = row(y, item, False)
            return y - y0
        ui.scroll("dev_projects", body, draw)
