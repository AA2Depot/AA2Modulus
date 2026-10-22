"""Check the layering of the aa2modulus package.

Each module belongs to one layer and may import only from its own layer or the
layers below it. Imports of aa2modulus modules must sit at module level (a
`TYPE_CHECKING` block counts), must not name another module's `_private`
members, and must not form a cycle at import time. Findings listed in
ALLOWED are tolerated until the restructure removes them; an entry that no
longer matches a finding is an error, so the list only shrinks.
"""

from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "aa2modulus"
LINE_LIMIT = 600

# Module prefix -> layer. The longest matching prefix wins; every module must match.
LAYERS: dict[str, int] = {
    # L0 core
    "aa2modulus.version": 0,
    "aa2modulus.core": 0,
    # L1 model
    "aa2modulus.model": 1,
    # L2 binary and registry metadata
    "aa2modulus.binary": 2,
    "aa2modulus.metadata": 2,
    # L3 language policy
    "aa2modulus.language": 3,
    # L4 validation
    "aa2modulus.validation": 4,
    # L5 context
    "aa2modulus.context": 5,
    # L6 syntax
    "aa2modulus.syntax": 6,
    # L7 HIR
    "aa2modulus.hir": 7,
    # L8 lowering
    "aa2modulus.lowering": 8,
    # L9 semantics and decompile
    "aa2modulus.semantics": 9,
    "aa2modulus.decompile": 9,
    # L10 pipeline
    "aa2modulus.pipeline": 10,
    # L11 app
    "aa2modulus.app": 11,
    # L12 front ends
    "aa2modulus.__main__": 12,
    "aa2modulus.cli": 12,
    "aa2modulus.lsp": 12,
    # The package root holds only its docstring and sits above everything.
    "aa2modulus": 13,
}

# Tolerated findings, keyed as printed. The final list is only the CLI's lazy
# import of the language server, which keeps pygls out of CLI startup.
ALLOWED: frozenset[str] = frozenset(
    {
        "function-level cli.main -> lsp.server.run",
    }
)


@dataclass(frozen=True, slots=True)
class Import:
    source: str
    target: str
    names: tuple[str, ...]
    line: int
    module_level: bool
    type_checking: bool


def module_name(path: Path) -> str:
    parts = path.relative_to(ROOT).with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def collect_modules() -> dict[str, Path]:
    return {module_name(path): path for path in sorted((ROOT / PACKAGE).rglob("*.py"))}


def layer(module: str) -> int | None:
    if module == PACKAGE:
        return LAYERS[PACKAGE]
    parts = module.split(".")
    # The root entry covers only the root module, so new modules must be assigned.
    for end in range(len(parts), 1, -1):
        found = LAYERS.get(".".join(parts[:end]))
        if found is not None:
            return found
    return None


def _is_type_checking(test: ast.expr) -> bool:
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
    )


def _resolve(
    source: str, is_package: bool, node: ast.ImportFrom, modules: dict[str, Path]
) -> list[tuple[str, tuple[str, ...]]]:
    """(target module, imported names) pairs; a submodule import is its own target."""

    if node.level:
        base = source.split(".") if is_package else source.split(".")[:-1]
        base = base[: len(base) - node.level + 1]
        anchor = ".".join([*base, node.module] if node.module else base)
    else:
        anchor = node.module or ""
    if anchor != PACKAGE and not anchor.startswith(PACKAGE + "."):
        return []
    result: list[tuple[str, tuple[str, ...]]] = []
    names: list[str] = []
    for alias in node.names:
        submodule = f"{anchor}.{alias.name}"
        if submodule in modules:
            result.append((submodule, ()))
        else:
            names.append(alias.name)
    if names or not result:
        result.append((anchor, tuple(names)))
    return result


def collect_imports(module: str, path: Path, modules: dict[str, Path]) -> list[Import]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    is_package = path.name == "__init__.py"
    found: list[Import] = []

    def visit(node: ast.AST, module_level: bool, type_checking: bool) -> None:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == PACKAGE or alias.name.startswith(PACKAGE + "."):
                    found.append(
                        Import(module, alias.name, (), node.lineno, module_level, type_checking)
                    )
            return
        if isinstance(node, ast.ImportFrom):
            for target, names in _resolve(module, is_package, node, modules):
                found.append(
                    Import(module, target, names, node.lineno, module_level, type_checking)
                )
            return
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            module_level = False
        if isinstance(node, ast.If) and _is_type_checking(node.test):
            for statement in node.body:
                visit(statement, module_level, True)
            for statement in node.orelse:
                visit(statement, module_level, type_checking)
            return
        for child in ast.iter_child_nodes(node):
            visit(child, module_level, type_checking)

    visit(tree, True, False)
    return found


def _cycles(edges: dict[str, set[str]]) -> list[list[str]]:
    """Strongly connected components with more than one module (Tarjan)."""

    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[list[str]] = []

    def connect(node: str) -> None:
        index[node] = low[node] = len(index)
        stack.append(node)
        on_stack.add(node)
        for target in sorted(edges.get(node, ())):
            if target not in index:
                connect(target)
                low[node] = min(low[node], low[target])
            elif target in on_stack:
                low[node] = min(low[node], index[target])
        if low[node] == index[node]:
            component: list[str] = []
            while True:
                item = stack.pop()
                on_stack.discard(item)
                component.append(item)
                if item == node:
                    break
            if len(component) > 1:
                components.append(sorted(component))

    for node in sorted(edges):
        if node not in index:
            connect(node)
    return sorted(components)


def _short(module: str) -> str:
    return module.removeprefix(PACKAGE + ".")


def findings(modules: dict[str, Path]) -> tuple[dict[str, str], list[str]]:
    """Violations keyed for ALLOWED (with a location for display), and errors."""

    violations: dict[str, str] = {}
    errors: list[str] = []
    runtime_edges: dict[str, set[str]] = {}
    for module, path in modules.items():
        own = layer(module)
        if own is None:
            errors.append(f"{module}: no layer assigned in LAYERS")
            continue
        where = path.relative_to(ROOT)
        for item in collect_imports(module, path, modules):
            if item.target == module:
                continue
            target = layer(item.target)
            if target is None:
                errors.append(f"{where}:{item.line}: unknown import target {item.target}")
                continue
            if target > own:
                key = f"upward {_short(module)} -> {_short(item.target)}"
                violations.setdefault(key, f"{where}:{item.line}")
            if not item.module_level:
                key = f"function-level {_short(module)} -> {_short(item.target)}"
                violations.setdefault(key, f"{where}:{item.line}")
            for name in item.names:
                if name.startswith("_") and not name.startswith("__"):
                    key = f"private {_short(module)} -> {_short(item.target)}.{name}"
                    violations.setdefault(key, f"{where}:{item.line}")
            if item.module_level and not item.type_checking:
                runtime_edges.setdefault(module, set()).add(item.target)
    for component in _cycles(runtime_edges):
        violations.setdefault(f"cycle {' '.join(map(_short, component))}", "import time")
    return violations, errors


def main() -> None:
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args()
    modules = collect_modules()
    violations, errors = findings(modules)
    failed = False
    for message in errors:
        print(f"error: {message}")
        failed = True
    for key in sorted(violations.keys() - ALLOWED):
        print(f"error: {violations[key]}: {key}")
        failed = True
    for key in sorted(ALLOWED - violations.keys()):
        print(f"error: allowlist entry no longer needed: {key}")
        failed = True
    for path in modules.values():
        lines = len(path.read_text(encoding="utf-8").splitlines())
        if lines > LINE_LIMIT:
            print(f"note: {path.relative_to(ROOT)}: {lines} lines (limit {LINE_LIMIT})")
    tolerated = len(violations.keys() & ALLOWED)
    print(f"{len(modules)} modules, {tolerated} allowlisted findings")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
