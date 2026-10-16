"""Persisted open/placement state for the docked Library/Discover windows."""

import json
from pathlib import Path

from .. import XDG_STATE

STATE_PATH = XDG_STATE / "sqlch-gui" / "windows.json"
NAMES = ("library", "discover")


def default_state() -> dict:
    return {n: {"open": False, "placed": None} for n in NAMES}


def _int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _placed(p):
    if not isinstance(p, dict):
        return None
    if p.get("mode") == "np" and _int(p.get("dx")) and _int(p.get("dy")):
        return {"mode": "np", "dx": p["dx"], "dy": p["dy"]}
    if p.get("mode") == "free" and _int(p.get("x")) and _int(p.get("y")):
        return {"mode": "free", "x": p["x"], "y": p["y"]}
    return None


def load(path: Path = STATE_PATH) -> dict:
    state = default_state()
    try:
        raw = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return state
    if not isinstance(raw, dict):
        return state
    for name in NAMES:
        entry = raw.get(name)
        if isinstance(entry, dict):
            state[name] = {"open": entry.get("open") is True,
                           "placed": _placed(entry.get("placed"))}
    return state


def save(state: dict, path: Path = STATE_PATH) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state))
    tmp.replace(path)
