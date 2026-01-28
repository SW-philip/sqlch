#!/usr/bin/env python3
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "sqlch"

# Internal top-level modules that must NEVER be imported directly
BANNED_TOPLEVEL = {
    "cli",
    "core",
    "tui",
    "tools",
}

BANNED_TOKENS = (
    "sys.path",
    "__file__",
)

def check_file(path: Path) -> list[str]:
    errors = []

    try:
        tree = ast.parse(path.read_text())
    except SyntaxError as e:
        return [f"{path}: syntax error ({e})"]

    for node in ast.walk(tree):
        # ---- ban relative imports ----
        if isinstance(node, ast.ImportFrom):
            if node.level > 0:
                errors.append(
                    f"{path}:{node.lineno} relative import (level={node.level})"
                )
                continue

            if node.module:
                root = node.module.split(".")[0]

                if root in BANNED_TOPLEVEL:
                    errors.append(
                        f"{path}:{node.lineno} illegal import '{node.module}' "
                        f"(must be '{PACKAGE}.{node.module}')"
                    )

        # ---- ban bare internal imports ----
        elif isinstance(node, ast.Import):
            for name in node.names:
                root = name.name.split(".")[0]
                if root in BANNED_TOPLEVEL:
                    errors.append(
                        f"{path}:{node.lineno} illegal import '{name.name}' "
                        f"(must be '{PACKAGE}.{name.name}')"
                    )

    text = path.read_text()
    for token in BANNED_TOKENS:
        if token in text:
            errors.append(f"{path}: banned token '{token}'")

    return errors

def main() -> None:
    failures: list[str] = []

    for path in ROOT.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        if "tools" in path.parts:
            continue

        failures.extend(check_file(path))

    if failures:
        print("❌ Import policy violated:\n")
        for f in failures:
            print(" ", f)
        sys.exit(1)

    print("✅ Import policy clean")

if __name__ == "__main__":
    main()
