"""Layer boundaries: core → stdlib, models, engines, services, UI."""
import ast
import sys
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[2] / "src" / "dynamic_island"

ALLOWED = {
    "core": {"core"},
    "models": {"core", "models"},
    "infrastructure": {"core", "models", "infrastructure"},
    "engines": {"core", "models", "infrastructure", "engines"},
    "services": {"core", "models", "infrastructure", "engines", "services"},
    "ui": {"core", "models", "infrastructure", "engines", "services", "ui"},
    "top": {"core", "models", "infrastructure", "engines", "services", "ui", "top"},
}


def _module_name(path):
    rel = path.relative_to(PACKAGE).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _layer(parts):
    if not parts:
        return "top"
    if parts[0] in ALLOWED:
        return parts[0]
    return "top"


def _imports(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        modules = []
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules = [node.module]
        for module in modules:
            if module == "dynamic_island" or module.startswith("dynamic_island."):
                yield node.lineno, tuple(module.split(".")[1:])


def _source_layer(path):
    rel = path.relative_to(PACKAGE)
    return _layer(tuple(rel.with_suffix("").parts))


def test_internal_imports_respect_layers():
    violations = []
    for path in sorted(PACKAGE.rglob("*.py")):
        source = _source_layer(path)
        for lineno, target in _imports(path):
            target_layer = _layer(target)
            if target_layer not in ALLOWED[source]:
                violations.append(f"{path}:{lineno}: {source} -> {target_layer}")
    assert not violations, "\n".join(violations)


def test_business_layers_never_import_ui():
    violations = []
    for path in sorted(PACKAGE.rglob("*.py")):
        source = _source_layer(path)
        if source not in {"core", "models", "infrastructure", "engines", "services"}:
            continue
        for lineno, target in _imports(path):
            if target and target[0] == "ui":
                violations.append(f"{path}:{lineno}: {source} -> ui")
    assert not violations, "\n".join(violations)


def test_core_uses_only_stdlib_and_core():
    violations = []
    for path in sorted((PACKAGE / "core").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            modules = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                modules = [node.module]
            for module in modules:
                root = module.split(".", 1)[0]
                if root == "dynamic_island":
                    target = tuple(module.split(".")[1:])
                    if target and target[0] != "core":
                        violations.append(f"{path}:{node.lineno}: {module}")
                elif root not in sys.stdlib_module_names and root != "babel":
                    violations.append(f"{path}:{node.lineno}: {module}")
    assert not violations, "\n".join(violations)
