"""Package imports, compilation of every module and absence of legacy flat imports."""
import ast
import subprocess
import sys
import textwrap
from pathlib import Path

from dynamic_island.ui.tabs import TABS

SRC = Path(__file__).resolve().parents[2] / "src"
PACKAGE = SRC / "dynamic_island"
LEGACY = {
    "store", "paths", "theme", "ui", "icons", "nlp", "system", "network", "hotspot",
    "media", "agenda", "timers", "tasks", "infos", "binance", "devtools", "launcher",
    "files", "clipboard", "phone", "island", "watchdog", "tab_agenda", "tab_clip",
    "tab_controls", "tab_dev", "tab_files", "tab_home", "tab_infos", "tab_launcher",
    "tab_phone", "tab_tasks", "tab_timers", "tab_wallet",
}
# Modules whose import requires winrt (Windows APIs) in the test environment.
WINRT_MODULES = {"dynamic_island.app", "dynamic_island.engines.media", "dynamic_island.ui.windows.island"}


def _module_name(path: Path) -> str:
    rel = path.relative_to(SRC).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _python_files():
    return sorted(SRC.rglob("*.py"))


def test_package_resolves_to_src():
    import dynamic_island

    assert Path(dynamic_island.__file__).resolve() == (PACKAGE / "__init__.py").resolve()
    assert dynamic_island.__version__


def test_all_source_files_compile():
    for path in _python_files():
        compile(path.read_text(encoding="utf-8"), str(path), "exec")


def test_every_module_imports():
    import importlib

    modules = sorted({_module_name(p) for p in _python_files()})
    for name in modules:
        if name in WINRT_MODULES:
            continue
        importlib.import_module(name)


def test_no_legacy_flat_imports():
    offenders = []
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            for name in names:
                if name.split(".", 1)[0] in LEGACY:
                    offenders.append(f"{path}:{node.lineno}: {name}")
    assert not offenders, "\n".join(offenders)


def test_tab_registry_is_explicit_and_complete():
    assert [tab.key for tab in TABS] == [
        "home", "agenda", "timers", "tasks", "launcher", "files",
        "phone", "infos", "wallet", "dev", "controls", "clip",
    ]
    from dynamic_island.ui.tabs import TAB_VIEWS

    assert set(TAB_VIEWS) == {tab.key for tab in TABS}
    assert TAB_VIEWS["agenda"] == ["up", "week", "month", "accounts"]
    assert TAB_VIEWS["timers"] == ["timers", "pomo", "sw", "alarms", "stats"]


def test_tab_warmup_uses_registry_instead_of_dynamic_import():
    text = (PACKAGE / "ui" / "components" / "painting.py").read_text(encoding="utf-8")
    assert "TAB_VIEWS.get(key" in text
    assert '__import__("tab_' not in text


def test_application_shell_imports_with_winrt_stub():
    """Verify the complete window/app graph without installing the winrt packages."""
    code = textwrap.dedent(
        f"""
        import sys, types
        sys.path.insert(0, {str(SRC)!r})

        names = [
            "winrt", "winrt.windows", "winrt.windows.media",
            "winrt.windows.media.control", "winrt.windows.storage",
            "winrt.windows.storage.streams",
        ]
        for name in names:
            sys.modules[name] = types.ModuleType(name)
        control = sys.modules["winrt.windows.media.control"]
        control.GlobalSystemMediaTransportControlsSessionManager = object
        control.GlobalSystemMediaTransportControlsSessionPlaybackStatus = object
        streams = sys.modules["winrt.windows.storage.streams"]
        streams.Buffer = object
        streams.InputStreamOptions = object

        from dynamic_island import app
        from dynamic_island.ui.components.painting import IslandPainting
        from dynamic_island.ui.tabs import TABS
        from dynamic_island.ui.windows.island import Island

        assert callable(app.main)
        assert issubclass(Island, IslandPainting)
        assert hasattr(IslandPainting, "paintEvent")
        assert len(TABS) == 12
        print("application shell OK")
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "application shell OK" in result.stdout
