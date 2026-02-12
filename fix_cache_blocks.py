#!/usr/bin/env python3

import ast
from pathlib import Path

LAZY_BLOCK = """
# ------------------------------------------------------------
# Lazy cache resolution (Nix-safe)
# ------------------------------------------------------------

_CACHE_DIR = None

def _cache_dir():
    global _CACHE_DIR
    if _CACHE_DIR is None:
        import os
        from pathlib import Path
        base = os.environ.get("XDG_CACHE_HOME")
        if not base:
            base = str(Path.home() / ".cache")
        p = Path(base) / "sqlch"
        p.mkdir(parents=True, exist_ok=True)
        _CACHE_DIR = p
    return _CACHE_DIR
""".strip()


def is_cache_assignment(node):
    return (
        isinstance(node, ast.Assign)
        and any(
            isinstance(t, ast.Name) and t.id == "CACHE_DIR"
            for t in node.targets
        )
    )


def is_mkdir_call(node):
    if not isinstance(node, ast.Expr):
        return False
    call = node.value
    if not isinstance(call, ast.Call):
        return False
    if isinstance(call.func, ast.Attribute):
        return call.func.attr == "mkdir"
    return False


def fix_file(path: Path):
    source = path.read_text()
    tree = ast.parse(source)

    new_body = []
    for node in tree.body:
        if is_cache_assignment(node):
            continue
        if is_mkdir_call(node):
            continue
        new_body.append(node)

    tree.body = new_body

    fixed = ast.unparse(tree)

    if "_cache_dir" not in fixed:
        fixed = LAZY_BLOCK + "\n\n" + fixed

    path.write_text(fixed)
    print(f"✔ fixed {path}")


def main():
    for path in Path("sqlch").rglob("*.py"):
        fix_file(path)


if __name__ == "__main__":
    main()
