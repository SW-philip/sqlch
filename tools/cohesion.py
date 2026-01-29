#!/usr/bin/env python3
import ast
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
ANCHOR = ROOT / "sqlch" / "tui" / "app.py"

class FuncMetrics:
    def __init__(self, name, loc, max_depth, returns, raises, blanks, comments):
        self.name = name
        self.loc = loc
        self.max_depth = max_depth
        self.returns = returns
        self.raises = raises
        self.blanks = blanks
        self.comments = comments

def max_nesting(node, depth=0):
    depths = [depth]
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.If, ast.For, ast.While, ast.Try, ast.With)):
            depths.append(max_nesting(child, depth + 1))
        else:
            depths.append(max_nesting(child, depth))
    return max(depths)

def analyze_file(path: Path):
    src = path.read_text()
    lines = src.splitlines()
    tree = ast.parse(src)

    metrics = []

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            start = node.lineno - 1
            end = node.end_lineno
            block = lines[start:end]

            loc = len(block)
            blanks = sum(1 for l in block if not l.strip())
            comments = sum(1 for l in block if l.strip().startswith("#"))

            returns = sum(isinstance(n, ast.Return) for n in ast.walk(node))
            raises = sum(isinstance(n, ast.Raise) for n in ast.walk(node))
            depth = max_nesting(node)

            metrics.append(
                FuncMetrics(
                    node.name, loc, depth, returns, raises, blanks, comments
                )
            )

    return metrics

def summarize(metrics):
    return {
        "functions": len(metrics),
        "loc_avg": mean(m.loc for m in metrics),
        "loc_max": max(m.loc for m in metrics),
        "nesting_max": max(m.max_depth for m in metrics),
        "returns_avg": mean(m.returns for m in metrics),
        "raises_total": sum(m.raises for m in metrics),
        "blank_ratio": mean(m.blanks / m.loc for m in metrics),
        "comment_ratio": mean(m.comments / m.loc for m in metrics),
    }

def main():
    metrics = analyze_file(ANCHOR)
    summary = summarize(metrics)

    print("\nCOHESION ANCHOR METRICS\n")
    for k, v in summary.items():
        print(f"{k:15}: {v}")

    print("\nFUNCTION DETAILS\n")
    for m in metrics:
        print(
            f"{m.name:20} "
            f"loc={m.loc:3} "
            f"depth={m.max_depth} "
            f"returns={m.returns} "
            f"raises={m.raises}"
        )

    audit_repo(summary)

def audit_repo(anchor_summary):
    print("\nCOHESION AUDIT\n")

    for path in Path(".").rglob("*.py"):
        if any(p in path.parts for p in ("tools", "__pycache__")):
            continue
        if path == ANCHOR:
            continue

        metrics = analyze_file(path)
        for m in metrics:
            warnings = []

            if m.loc > anchor_summary["loc_max"]:
                warnings.append(f"loc {m.loc} > anchor max {anchor_summary['loc_max']}")

            if m.max_depth > anchor_summary["nesting_max"]:
                warnings.append(f"nesting {m.max_depth} > anchor max {anchor_summary['nesting_max']}")

            if "tui" in path.parts and m.raises > 0:
                warnings.append("raises in tui layer")

            if warnings:
                print(f"{path}:{m.name}")
                for w in warnings:
                    print(f"  - {w}")

if __name__ == "__main__":
    main()
