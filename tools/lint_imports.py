#!/usr/bin/env python3
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

BANNED_TOKENS = (
    "sys.path",
    "__file__",
)

def check_file(path: Path) -> list[str]:
    errors = []

    try:
        tree = ast.parse(path.read_text())
    except SyntaxError as e:
        errors.append(f"{path}: syntax error ({e})")
        return errors

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level > 0:
                errors.append(
                    f"{path}:{node.lineno} relative import (level={node.level})"
                )

    text = path.read_text()
    for token in BANNED_TOKENS:
        if token in text:
            errors.append(f"{path}: banned token '{token}'")

    return errors

def main():
    failures = []

    py_files = ROOT.rglob("*.py")

    for path in py_files:
        if "__pycache__" in path.parts:
            continue
        if "tools" in path.parts:
            continue
        failures.extend(check_file(path))

    if failures:
        print("❌ Import lint failed:\n")
        for f in failures:
            print(" ", f)
        sys.exit(1)

    print("✅ Import lint passed")

if __name__ == "__main__":
    main()
