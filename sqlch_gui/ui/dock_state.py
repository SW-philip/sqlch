"""Persisted open/placement state for the docked Radio and source windows,
plus Now Playing's position ("np": None = default top-right, else {"x","y"}
in overlay coordinates), whether it is collapsed, and the docked windows'
height ("pane_h"), which stays at NP's expanded height while it is collapsed."""

import json
from pathlib import Path

from .. import XDG_STATE

STATE_PATH = XDG_STATE / "sqlch-gui" / "windows.json"
NAMES = ("radio",)


def default_state(names=NAMES) -> dict:
    state = {n: {"open": False, "placed": None} for n in names}
    state["np"] = None
    state["np_collapsed"] = False
    state["pane_h"] = None
    return state


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


def _np(p):
    if isinstance(p, dict) and _int(p.get("x")) and _int(p.get("y")):
        return {"x": p["x"], "y": p["y"]}
    return None


def load(path: Path = STATE_PATH, names=NAMES) -> dict:
    state = default_state(names)
    try:
        raw = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return state
    if not isinstance(raw, dict):
        return state
    for name in names:
        entry = raw.get(name)
        if isinstance(entry, dict):
            state[name] = {"open": entry.get("open") is True,
                           "placed": _placed(entry.get("placed"))}
    if "radio" in names and "radio" not in raw:
        # Library and Discover used to be separate windows; Radio inherits
        # whichever was open, placed where Library was.
        old = [raw.get(n) for n in ("library", "discover") if isinstance(raw.get(n), dict)]
        if old:
            state["radio"] = {"open": any(o.get("open") is True for o in old),
                              "placed": _placed(old[0].get("placed"))}
    state["np"] = _np(raw.get("np"))
    state["np_collapsed"] = raw.get("np_collapsed") is True
    pane_h = raw.get("pane_h")
    state["pane_h"] = pane_h if _int(pane_h) and pane_h > 0 else None
    return state


def save(state: dict, path: Path = STATE_PATH) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state))
    tmp.replace(path)
