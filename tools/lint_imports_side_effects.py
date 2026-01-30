#!/usr/bin/env python3
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Calls that should never happen at import time
BANNED_CALLS = {
    ("Path", "mkdir"),
    ("os", "mkdir"),
    ("os", "makedirs"),
    ("shutil", "rmtree"),
    ("builtins", "open"),
    ("subprocess", "run"),
    ("subprocess", "Popen"),
    ("requests", "get"),
    ("requests", "post"),
    ("socket", "socket"),
}

BANNED_NAMES = {
    "open",
}

def call_name(node: ast.Call) -> tuple[str | None, str | None]:
    """
    Return (module_or_class, function) if we can resolve it.
    Examples:
      Path(...).mkdir -> ("Path", "mkdir")
      os.mkdir       -> ("os", "mkdir")
      open(...)      -> ("builtins", "open")
    """
    fn = node.func

    if isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name):
        return fn.value.id, fn.attr

    if isinstance(fn, ast.Name):
        return "builtins", fn.id

    return None, None


class ImportSideEffectVisitor(ast.NodeVisitor):
    def __init__(self, path: Path):
        self.path = path
        self.errors: list[str] = []
        self.depth = 0  # function / class nesting

    def visit_FunctionDef(self, node):
        self.depth += 1
        self.generic_visit(node)
        self.depth -= 1

    def visit_AsyncFunctionDef(self, node):
        self.depth += 1
        self.generic_visit(node)
        self.depth -= 1

    def visit_ClassDef(self, node):
        self.depth += 1
        self.generic_visit(node)
        self.depth -= 1

    def visit_Call(self, node: ast.Call):
        if self.depth == 0:
            mod, fn = call_name(node)
            if (mod, fn) in BANNED_CALLS or fn in BANNED_NAMES:
                self.errors.append(
                    f"{self.path}:{node.lineno} import-time side effect: {mod}.{fn}()"
                )
        self.generic_visit(node)


def check_file(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text())
    except SyntaxError as e:
        return [f"{path}: syntax error ({e})"]

    visitor = ImportSideEffectVisitor(path)
    visitor.visit(tree)
    return visitor.errors


def main():
    failures: list[str] = []

    for path in ROOT.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        if "tools" in path.parts:
            continue

        failures.extend(check_file(path))

    if failures:
        print("❌ Import side-effect lint failed:\n")
        for f in failures:
            print(" ", f)
        sys.exit(1)

    print("✅ Import side-effect lint passed")


if __name__ == "__main__":
    main()
