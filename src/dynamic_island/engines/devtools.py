"""Developer workspace: open IDE/project, Git, GitHub (PRs, issues, CI, deployments,
notifications), Jenkins, local servers/ports, services, local builds and logs."""
import base64
import ctypes
import glob
import json
import os
import re
import subprocess
import threading
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from ctypes import wintypes

import psutil
from PySide6.QtCore import QObject, Signal

from dynamic_island.core.config.settings import settings
from dynamic_island.core.localization import translate as tr

NOWIN = 0x08000000  # CREATE_NO_WINDOW
user32 = ctypes.windll.user32

IDES = {
    "code.exe": "VS Code", "cursor.exe": "Cursor", "windsurf.exe": "Windsurf",
    "idea64.exe": "IntelliJ IDEA", "pycharm64.exe": "PyCharm", "webstorm64.exe": "WebStorm",
    "phpstorm64.exe": "PhpStorm", "rider64.exe": "Rider", "clion64.exe": "CLion", "goland64.exe": "GoLand",
    "rubymine64.exe": "RubyMine", "datagrip64.exe": "DataGrip", "studio64.exe": "Android Studio",
    "devenv.exe": "Visual Studio", "sublime_text.exe": "Sublime Text", "zed.exe": "Zed",
}
JETBRAINS = {"IntelliJ IDEA", "PyCharm", "WebStorm", "PhpStorm", "Rider", "CLion", "GoLand", "RubyMine",
             "DataGrip", "Android Studio"}
DEV_PROCS = ("node", "python", "pythonw", "java", "php", "ruby", "dotnet", "go", "nginx", "httpd", "postgres",
             "mysqld", "mariadbd", "mongod", "redis-server", "docker", "com.docker", "deno", "bun", "uvicorn",
             "gunicorn", "flask", "rails", "caddy", "vite", "esbuild", "jupyter", "ollama", "code", "idea64",
             "pycharm64", "webstorm64", "phpstorm64", "artisan", "xampp", "tomcat", "elasticsearch")
SERVICE_PAT = re.compile(r"\b(postgres\w*|mysql\w*|mariadb|mongo\w*|redis|docker|com\.docker\w*|apache\d*|nginx|"
                         r"mssql\w*|sqlserver\w*|sql server|elasticsearch|rabbitmq|jenkins|tomcat\d*|memcached|"
                         r"couchdb|neo4j|influxdb|wampapache\w*|xampp)\b", re.I)
DEV_PORTS = (set(range(3000, 3010)) | set(range(4000, 4010)) | set(range(5000, 5010)) | set(range(8000, 8100))
             | {80, 443, 1433, 3306, 4200, 5173, 5432, 5672, 6379, 8080, 8443, 8888, 9000, 9200, 27017})
ERR_RE = re.compile(r"(?<![\w-])(error|erreur|fatal|failed|failure|exception|traceback|cannot find|undefined)"
                    r"(?![\w-])", re.I)
LOG_RE = re.compile(r"\b(ERROR|CRITICAL|FATAL|Exception|Traceback|SEVERE|panic)\b")


def run(cmd, cwd=None, timeout=10):
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=timeout, creationflags=NOWIN)
        return r.returncode, r.stdout.strip()
    except Exception as e:
        return -1, str(e)


def git(path, *args):
    return run(["git", "-C", path, *args])


def _uri_to_path(uri):
    if not uri.startswith("file:///"):
        return None
    p = urllib.parse.unquote(uri[8:]).replace("/", "\\")
    p = p[:1].upper() + p[1:]
    return p if os.path.isdir(p) else None


def recent_projects():
    """Recent VS Code and JetBrains IDE projects: [{name, path, ide, ts}]."""
    out = {}
    ws = os.path.expandvars(r"%APPDATA%\Code\User\workspaceStorage")
    for f in glob.glob(os.path.join(ws, "*", "workspace.json")):
        try:
            with open(f, encoding="utf-8") as h:
                d = json.load(h)
            p = _uri_to_path(d.get("folder", ""))
            if p:
                ts = os.path.getmtime(os.path.dirname(f))
                k = os.path.normcase(p)
                if k not in out or out[k]["ts"] < ts:
                    out[k] = {"name": os.path.basename(p.rstrip("\\")), "path": p, "ide": "VS Code", "ts": ts}
        except Exception:
            continue
    for f in glob.glob(os.path.expandvars(r"%APPDATA%\JetBrains\*\options\recentProjects.xml")):
        product = os.path.basename(os.path.dirname(os.path.dirname(f)))
        ide = next((n for n in JETBRAINS if product.lower().startswith(n.split()[0].lower().replace("intellij", "intellijidea"))), None)
        ide = ide or ("IntelliJ IDEA" if product.lower().startswith("intellij") else re.sub(r"\d.*", "", product))
        try:
            root = ET.parse(f).getroot()
            for e in root.iter("entry"):
                key = e.get("key", "").replace("$USER_HOME$", os.path.expanduser("~"))
                p = os.path.normpath(key)
                if not os.path.isdir(p):
                    continue
                ts = 0
                for opt in e.iter("option"):
                    if opt.get("name") == "activationTimestamp":
                        ts = int(opt.get("value", "0")) / 1000
                k = os.path.normcase(p)
                if k not in out or out[k]["ts"] < ts:
                    out[k] = {"name": os.path.basename(p), "path": p, "ide": ide, "ts": ts}
        except Exception:
            continue
    return sorted(out.values(), key=lambda x: -x["ts"])


def ide_windows():
    """Visible IDE windows: [(hwnd, ide, title)]."""
    res = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n == 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        try:
            exe = psutil.Process(pid.value).name().lower()
        except Exception:
            return True
        if exe in IDES:
            res.append((hwnd, IDES[exe], buf.value))
        return True

    user32.EnumWindows(cb, 0)
    return res


def project_from_title(ide, title):
    t = title.lstrip("● ").strip()
    if ide in ("VS Code", "Cursor", "Windsurf"):
        t = re.sub(r"\s+-\s+(Visual Studio Code|Cursor|Windsurf).*$", "", t)
        parts = [x.strip() for x in t.split(" - ")]
        name = parts[-1] if parts else t
        return re.sub(r"\s*\[.*\]$", "", name).replace(" (Workspace)", "")
    if ide == "Visual Studio":
        return re.sub(r"\s+-\s+Microsoft Visual Studio.*$", "", t).split(" (")[0]
    if ide in JETBRAINS:
        return re.split(r"\s+[–-]\s+", t)[0].strip()
    return t.split(" - ")[-1]


def detect_build(path):
    j = lambda *a: os.path.join(path, *a)
    if settings.get("build_cmds", {}).get(path):
        return settings["build_cmds"][path]
    if os.path.exists(j("package.json")):
        try:
            with open(j("package.json"), encoding="utf-8") as f:
                scripts = json.load(f).get("scripts", {})
            for s in ("build", "typecheck", "lint", "test"):
                if s in scripts:
                    return f"npm run {s}"
        except Exception:
            pass
    if os.path.exists(j("artisan")):
        return "php artisan test"
    if os.path.exists(j("pom.xml")):
        return "mvn -q -B compile"
    if os.path.exists(j("gradlew.bat")):
        return "gradlew.bat build -q"
    if glob.glob(j("*.sln")) or glob.glob(j("*.csproj")):
        return "dotnet build"
    if os.path.exists(j("Cargo.toml")):
        return "cargo build"
    if os.path.exists(j("go.mod")):
        return "go build ./..."
    if os.path.exists(j("pubspec.yaml")):
        return "flutter analyze"
    if os.path.exists(j("composer.json")):
        return "composer validate"
    if glob.glob(j("*.py")) or os.path.exists(j("pyproject.toml")):
        return "python -m compileall -q ."
    return None


class Dev(QObject):
    updated = Signal()
    alert = Signal(str, str, str)   # kind, title, subtitle

    def __init__(self):
        super().__init__()
        self.ide = None
        self.project = None       # {name, path, ide}
        self.git = None
        self.recent = []
        self.gh = None
        self.gh_err = None
        self.jenkins = None
        self.ports = []
        self.services = []
        self.logs = []
        self.build = None
        self.visible = False
        self._seen_runs = None
        self._jenkins_colors = {}
        self._gh_t = self._jk_t = self._slow_t = 0
        self._wake = threading.Event()
        threading.Thread(target=self._loop, daemon=True).start()

    @property
    def favorites(self):
        return settings.get("dev_favorites", [])

    def toggle_favorite(self, path):
        favs = list(self.favorites)
        if path in favs:
            favs.remove(path)
        else:
            favs.append(path)
        settings.set("dev_favorites", favs)

    def set_token(self, tok):
        settings.set("github_token", tok.strip())
        self._gh_t = 0
        self._wake.set()

    def set_jenkins(self, url, user="", token=""):
        settings.set("jenkins", {"url": url.rstrip("/"), "user": user, "token": token})
        self._jk_t = 0
        self._wake.set()

    def refresh(self):
        self._gh_t = self._jk_t = self._slow_t = 0
        self._wake.set()

    def _loop(self):
        while True:
            try:
                self._detect()
            except Exception:
                pass
            now = time.time()
            if now - self._slow_t > (8 if self.visible else 30):
                self._slow_t = now
                for fn in (self._git, self._ports, self._services, self._logs):
                    try:
                        fn()
                    except Exception:
                        pass
            tok = settings.get("github_token")
            if self.git and self.git.get("repo") and now - self._gh_t > (180 if tok else 900):
                self._gh_t = now
                try:
                    self._github()
                except Exception as e:
                    self.gh_err = str(e)[:100]
            if settings.get("jenkins", {}).get("url") and now - self._jk_t > 120:
                self._jk_t = now
                try:
                    self._fetch_jenkins()
                except Exception:
                    self.jenkins = {"error": tr("dev.jenkins.unreachable")}
            self.updated.emit()
            self._wake.wait(3)
            self._wake.clear()

    def _detect(self):
        wins = ide_windows()
        fg = user32.GetForegroundWindow()
        chosen = next((w for w in wins if w[0] == fg), None)
        if chosen is None and self.project and any(w[1] == self.project["ide"] for w in wins):
            return  # keep the current project while its IDE stays open
        if chosen is None and wins:
            chosen = wins[0]
        if not self.recent or time.time() - getattr(self, "_recent_t", 0) > 60:
            self.recent = recent_projects()
            self._recent_t = time.time()
        if chosen is None:
            self.ide = None
            if self.project and not self.project.get("manual"):
                self.project = None
                self.git = None
            return
        _, ide, title = chosen
        name = project_from_title(ide, title)
        self.ide = ide
        if self.project and self.project["name"].lower() == name.lower():
            return
        path = None
        for r in self.recent:
            if r["name"].lower() == name.lower():
                path = r["path"]
                break
        if not path:
            for fav in self.favorites:
                if os.path.basename(fav.rstrip("\\")).lower() == name.lower():
                    path = fav
        self.project = {"name": name, "path": path, "ide": ide}
        self.git = None
        self.gh = None
        self._seen_runs = None
        self._slow_t = self._gh_t = 0

    def select_project(self, path, ide=None):
        self.project = {"name": os.path.basename(path.rstrip("\\")), "path": path, "ide": ide or "VS Code",
                        "manual": True}
        self.git = self.gh = None
        self._seen_runs = None
        self.refresh()

    def _git(self):
        p = self.project and self.project.get("path")
        if not p or not os.path.isdir(p):
            self.git = None
            return
        code, out = git(p, "status", "-b", "--porcelain=v1")
        if code != 0:
            self.git = {"repo": None, "error": tr("dev.git.not_repository")}
            return
        lines = out.splitlines()
        head = lines[0][3:] if lines and lines[0].startswith("##") else ""
        branch = head.split("...")[0].replace("No commits yet on ", "")
        ahead = int(m.group(1)) if (m := re.search(r"ahead (\d+)", head)) else 0
        behind = int(m.group(1)) if (m := re.search(r"behind (\d+)", head)) else 0
        files = [l for l in lines[1:] if l.strip()]
        staged = sum(1 for l in files if l[0] not in " ?")
        modified = sum(1 for l in files if l[1] in "MD")
        untracked = sum(1 for l in files if l.startswith("??"))
        _, log = git(p, "log", "-6", "--format=%h%x1f%s%x1f%ar%x1f%an")
        commits = [l.split("\x1f") for l in log.splitlines() if l.count("\x1f") == 3]
        _, url = git(p, "remote", "get-url", "origin")
        repo = None
        m = re.search(r"github\.com[:/]([^/]+)/([^/\s]+?)(?:\.git)?$", url or "")
        if m:
            repo = f"{m.group(1)}/{m.group(2)}"
        status = "clean" if not files else ("uncommitted" if staged else "modified")
        self.git = {"branch": branch or "?", "ahead": ahead, "behind": behind, "changes": len(files),
                    "staged": staged, "modified": modified, "untracked": untracked, "status": status,
                    "commits": commits, "repo": repo, "remote": url, "files": files[:30]}

    def _gh(self, path):
        tok = settings.get("github_token")
        h = {"Accept": "application/vnd.github+json", "User-Agent": "DynamicIsland",
             "X-GitHub-Api-Version": "2022-11-28"}
        if tok:
            h["Authorization"] = "Bearer " + tok
        req = urllib.request.Request("https://api.github.com" + path, headers=h)
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))

    def _github(self):
        repo = self.git["repo"]
        gh = {"repo": repo, "time": time.time()}
        gh["pulls"] = [{"n": p["number"], "title": p["title"], "user": p["user"]["login"], "url": p["html_url"],
                        "draft": p.get("draft"), "ts": p["updated_at"]}
                       for p in self._gh(f"/repos/{repo}/pulls?state=open&per_page=10")]
        gh["issues"] = [{"n": i["number"], "title": i["title"], "user": i["user"]["login"], "url": i["html_url"],
                         "labels": [l["name"] for l in i.get("labels", [])][:2]}
                        for i in self._gh(f"/repos/{repo}/issues?state=open&per_page=15")
                        if "pull_request" not in i][:10]
        runs = self._gh(f"/repos/{repo}/actions/runs?per_page=8").get("workflow_runs", [])
        gh["runs"] = [{"id": r["id"], "name": r["name"], "branch": r["head_branch"], "status": r["status"],
                       "conclusion": r["conclusion"], "url": r["html_url"], "title": r.get("display_title", ""),
                       "ts": r["created_at"]} for r in runs]
        seen = {r["id"] for r in gh["runs"] if r["status"] == "completed"}
        if self._seen_runs is not None:
            for r in gh["runs"]:
                if r["status"] == "completed" and r["id"] not in self._seen_runs:
                    if r["conclusion"] == "failure":
                        self.alert.emit("ci_fail", tr("dev.alerts.ci_failed"), f"{r['name']} · {r['branch']}")
                    elif r["conclusion"] == "success":
                        self.alert.emit("ci_ok", tr("dev.alerts.ci_success"), f"{r['name']} · {r['branch']}")
        self._seen_runs = seen | (self._seen_runs or set())
        try:
            deps = self._gh(f"/repos/{repo}/deployments?per_page=5")
            gh["deployments"] = []
            for d in deps[:4]:
                st = self._gh(f"/repos/{repo}/deployments/{d['id']}/statuses?per_page=1")
                gh["deployments"].append({"env": d["environment"], "ref": d["ref"], "ts": d["created_at"],
                                          "state": st[0]["state"] if st else "pending",
                                          "url": (st[0].get("environment_url") or st[0].get("target_url")) if st else None})
        except Exception:
            gh["deployments"] = []
        gh["notifications"] = []
        if settings.get("github_token"):
            try:
                gh["notifications"] = [{"title": n["subject"]["title"], "type": n["subject"]["type"],
                                        "repo": n["repository"]["full_name"], "reason": n["reason"],
                                        "url": n["repository"]["html_url"]}
                                       for n in self._gh("/notifications?per_page=15")]
            except Exception:
                pass
        self.gh = gh
        self.gh_err = None

    def _fetch_jenkins(self):
        cfg = settings.get("jenkins", {})
        url = cfg["url"] + "/api/json?tree=jobs[name,color,url,lastBuild[number,result,building,timestamp,duration]]"
        h = {"User-Agent": "DynamicIsland"}
        if cfg.get("user"):
            h["Authorization"] = "Basic " + base64.b64encode(f"{cfg['user']}:{cfg.get('token', '')}".encode()).decode()
        with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=15) as r:
            d = json.loads(r.read().decode("utf-8"))
        jobs = []
        for j in d.get("jobs", []):
            color = j.get("color", "")
            lb = j.get("lastBuild") or {}
            jobs.append({"name": j["name"], "color": color, "url": j.get("url"), "building": color.endswith("_anime"),
                         "result": lb.get("result"), "number": lb.get("number")})
            old = self._jenkins_colors.get(j["name"])
            if old is not None and old.startswith(("blue", "notbuilt")) and color.startswith("red"):
                self.alert.emit("ci_fail", tr("dev.alerts.jenkins_failed"), j["name"])
            self._jenkins_colors[j["name"]] = color
        self.jenkins = {"jobs": jobs}

    def _ports(self):
        seen, out = set(), []
        for c in psutil.net_connections("tcp"):
            if c.status != "LISTEN" or not c.pid or c.pid == 4:
                continue
            port = c.laddr.port
            if port in seen:
                continue
            try:
                name = psutil.Process(c.pid).name()
            except Exception:
                continue
            low = name.lower().replace(".exe", "")
            dev = low.startswith(DEV_PROCS) or port in DEV_PORTS
            if low in ("svchost", "lsass", "wininit", "services", "spoolsv", "system"):
                continue
            seen.add(port)
            out.append({"port": port, "pid": c.pid, "name": name, "dev": dev,
                        "local": c.laddr.ip in ("127.0.0.1", "::1", "0.0.0.0", "::")})
        out.sort(key=lambda x: (not x["dev"], x["port"]))
        self.ports = out

    def _services(self):
        out = []
        try:
            for s in psutil.win_service_iter():
                try:
                    n, dn = s.name(), s.display_name()
                    if SERVICE_PAT.search(n) or SERVICE_PAT.search(dn):
                        out.append({"name": n, "display": dn, "status": s.status()})
                except Exception:
                    continue
        except Exception:
            pass
        self.services = out[:12]

    def _logs(self):
        p = self.project and self.project.get("path")
        if not p or not os.path.isdir(p):
            self.logs = []
            return
        files = []
        for pat in ("*.log", "logs/*.log", "log/*.log", "storage/logs/*.log", "var/log/*.log", "tmp/*.log"):
            files += glob.glob(os.path.join(p, pat))
        files = sorted(files, key=os.path.getmtime, reverse=True)[:3]
        out = []
        for f in files:
            try:
                with open(f, "rb") as h:
                    h.seek(max(0, os.path.getsize(f) - 65536))
                    lines = h.read().decode("utf-8", "replace").splitlines()
                for l in lines:
                    if LOG_RE.search(l):
                        out.append({"file": os.path.basename(f), "line": l.strip()[:300], "mtime": os.path.getmtime(f)})
            except Exception:
                continue
        self.logs = out[-20:][::-1]

    def start_build(self):
        p = self.project and self.project.get("path")
        if not p or (self.build and self.build.get("running")):
            return
        cmd = detect_build(p)
        if not cmd:
            self.build = {"running": False, "cmd": None, "ok": False,
                      "errors": [tr("dev.builds.no_command")],
                          "out": [], "start": time.time(), "end": time.time(), "project": self.project["name"]}
            return
        b = {"running": True, "cmd": cmd, "start": time.time(), "out": [], "errors": [], "ok": None,
             "project": self.project["name"]}
        self.build = b

        def work():
            try:
                proc = subprocess.Popen(cmd, cwd=p, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        text=True, encoding="utf-8", errors="replace", creationflags=NOWIN)
                b["proc"] = proc
                for line in proc.stdout:
                    line = line.rstrip()
                    if not line:
                        continue
                    b["out"].append(line)
                    b["out"] = b["out"][-200:]
                    if ERR_RE.search(line) and not re.search(r"\b0 (errors?|erreurs?)\b", line, re.I):
                        b["errors"].append(line[:300])
                code = proc.wait()
                b["ok"] = code == 0
            except Exception as e:
                b["ok"] = False
                b["errors"].append(str(e))
            b["running"] = False
            b["end"] = time.time()
            n = len(b["errors"])
            if b["ok"]:
                self.alert.emit("build_ok", tr("dev.alerts.build_success"),
                        f"{b['project']} · {int(b['end'] - b['start'])} s")
            else:
                self.alert.emit("build_fail", tr("dev.alerts.build_failed"),
                        tr("dev.builds.error_count", project=b['project'], count=n))
            self.updated.emit()

        threading.Thread(target=work, daemon=True).start()

    def stop_build(self):
        b = self.build
        if b and b.get("running") and b.get("proc"):
            run(["taskkill", "/F", "/T", "/PID", str(b["proc"].pid)])

    def open_project(self, path=None, ide=None):
        path = path or (self.project and self.project.get("path"))
        if not path:
            return
        ide = ide or (self.project and self.project.get("ide")) or "VS Code"
        if ide in JETBRAINS:
            exe = {"IntelliJ IDEA": "idea64.exe", "PyCharm": "pycharm64.exe", "WebStorm": "webstorm64.exe",
                   "PhpStorm": "phpstorm64.exe", "Rider": "rider64.exe", "CLion": "clion64.exe",
                   "GoLand": "goland64.exe", "DataGrip": "datagrip64.exe",
                   "Android Studio": "studio64.exe"}.get(ide)
            cands = glob.glob(rf"C:\Program Files\JetBrains\*\bin\{exe}") + \
                glob.glob(os.path.expandvars(rf"%LOCALAPPDATA%\Programs\*\bin\{exe}")) + \
                glob.glob(rf"C:\Program Files\Android\*\bin\{exe}")
            if cands:
                subprocess.Popen([sorted(cands)[-1], path], creationflags=NOWIN)
                return
        subprocess.Popen(f'code "{path}"', shell=True, creationflags=NOWIN)

    def open_terminal(self, path=None):
        path = path or (self.project and self.project.get("path")) or os.path.expanduser("~")
        try:
            subprocess.Popen(["wt.exe", "-d", path])
        except Exception:
            subprocess.Popen(["powershell.exe", "-NoExit", "-Command", f"Set-Location '{path}'"],
                             creationflags=0x00000010)

    def open_folder(self, path=None):
        path = path or (self.project and self.project.get("path"))
        if path:
            os.startfile(path)

    def kill(self, pid):
        try:
            psutil.Process(pid).terminate()
        except Exception:
            pass
        self._slow_t = 0
        self._wake.set()

    def service_toggle(self, svc):
        action = "stop" if svc["status"] == "running" else "start"
        ctypes.windll.shell32.ShellExecuteW(None, "runas", "cmd.exe", f'/c net {action} "{svc["name"]}"', None, 0)
        svc["status"] = "stop_pending" if action == "stop" else "start_pending"
        self._slow_t = time.time() - 5
