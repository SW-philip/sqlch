#!/usr/bin/env python3
from pathlib import Path
import re
import sys

ROOT = Path(".")
SKIP_DIRS = {"__pycache__", ".git", ".direnv"}
SKIP_PATHS = {"tools"}  # tools may print, debug, etc.

BAD_FILENAMES = {
    ".env",
    ".env.local",
    "secrets.json",
}

BAD_EXTENSIONS = {
    ".pyc",
}

CONTENT_PATTERNS = {
    "print() usage": re.compile(r"\bprint\s*\("),
    "TODO / FIXME / HACK": re.compile(r"\b(TODO|FIXME|HACK)\b"),
    "absolute home path": re.compile(r"/home/|/Users/"),
    "possible API key": re.compile(r"(?i)(api[_-]?key|secret|token)\s*=\s*[\"']"),
}

def should_skip(path: Path) -> bool:
    return any(part in SKIP_DIRS for part in path.parts)

def scan():
    findings = []

    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if should_skip(path):
            continue

        if path.name in BAD_FILENAMES:
            findings.append((path, "forbidden filename"))
            continue

        if path.suffix in BAD_EXTENSIONS:
            findings.append((path, "forbidden file extension"))
            continue

        if path.parts and path.parts[0] in SKIP_PATHS:
            continue

        try:
            text = path.read_text(errors="ignore")
        except Exception:
            continue

        for label, pattern in CONTENT_PATTERNS.items():
            if pattern.search(text):
                findings.append((path, label))

    return findings

def main():
    findings = scan()

    if not findings:
        print("✅ repo sanity check passed")
        return 0

    print("⚠️  repo sanity warnings:\n")
    for path, reason in findings:
        print(f"{path}: {reason}")

    if "--strict" in sys.argv:
        print("\n❌ strict mode enabled — failing")
        return 1

    print("\nℹ️  warnings only (use --strict to fail)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
