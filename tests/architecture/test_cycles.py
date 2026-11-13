"""The package import graph must not contain cycles."""
import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[2] / "src" / "dynamic_island"


def _module_name(path):
    rel = path.relative_to(PACKAGE).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _graph():
    modules = {_module_name(path) for path in PACKAGE.rglob("*.py")}
    graph = {name: set() for name in modules}
    for path in PACKAGE.rglob("*.py"):
        source = _module_name(path)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            targets = []
            if isinstance(node, ast.Import):
                targets = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                targets = [node.module]
            for target in targets:
                if target in modules and target != source:
                    graph[source].add(target)
    return graph


def test_no_import_cycles():
    graph = _graph()
    state = {}
    stack = []

    def visit(node):
        state[node] = "visiting"
        stack.append(node)
        for child in sorted(graph[node]):
            if state.get(child) == "visiting":
                cycle = " -> ".join(stack + [child])
                raise AssertionError(f"cycle d'imports : {cycle}")
            if child not in state:
                visit(child)
        stack.pop()
        state[node] = "done"

    for node in sorted(graph):
        if node not in state:
            visit(node)
