"""The play queue: one small JSON file in data_dir().

Same ownership rules as follows.py: the daemon is the only writer and the
only one that quarantines a corrupt file; the gui only reads. Every write
replaces the file atomically. This module is pure state; what plays next is
decided in transport.py."""

import json
import logging
import os
import tempfile
import threading
import time
import uuid

from sqlch.core.paths import data_dir

log = logging.getLogger(__name__)

FILE = "queue.json"
MODES = ("radio", "media")
HISTORY_MAX = 20

# RLock: the mutators nest (add -> _update).
_lock = threading.RLock()


def path():
    return data_dir() / FILE


def _empty() -> dict:
    return {"mode": "radio", "entries": [], "now": None, "context": None,
            "history": [], "resume": None}


def _entry_ok(e) -> bool:
    if not isinstance(e, dict) or not isinstance(e.get("uid"), str):
        return False
    if e.get("kind") == "item":
        it = e.get("item")
        return isinstance(it, dict) and bool(it.get("source")) and bool(it.get("id"))
    if e.get("kind") == "station":
        st = e.get("station")
        return isinstance(st, dict) and bool(st.get("url"))
    return False


def _context_ok(c) -> bool:
    return (isinstance(c, dict) and isinstance(c.get("items"), list)
            and isinstance(c.get("index"), int))


def _resume_ok(r) -> bool:
    return (isinstance(r, dict) and _entry_ok(r.get("entry"))
            and isinstance(r.get("pos"), (int, float)))


def _clean(data) -> dict:
    """Normalize a parsed payload. A non-dict raises ValueError; bad rows
    inside a dict are dropped rather than failing the whole queue."""
    if not isinstance(data, dict):
        raise ValueError(f"{FILE} does not hold an object")
    out = _empty()
    if data.get("mode") in MODES:
        out["mode"] = data["mode"]
    entries = data.get("entries")
    out["entries"] = [e for e in entries if _entry_ok(e)] if isinstance(entries, list) else []
    history = data.get("history")
    out["history"] = [e for e in history if _entry_ok(e)] if isinstance(history, list) else []
    if _entry_ok(data.get("now")):
        out["now"] = data["now"]
    if _context_ok(data.get("context")):
        out["context"] = data["context"]
    if _resume_ok(data.get("resume")):
        r = data["resume"]
        out["resume"] = {"entry": r["entry"], "pos": float(r["pos"]),
                         "dur": r["dur"] if isinstance(r.get("dur"), (int, float)) else None}
        if r.get("head") is True:
            out["resume"]["head"] = True
    return out


def _load() -> dict:
    """FileNotFoundError -> empty; bad content raises ValueError."""
    try:
        data = json.loads(path().read_text())
    except FileNotFoundError:
        return _empty()
    return _clean(data)


def read() -> dict:
    """Read-only view for any process: never renames or writes."""
    try:
        return _load()
    except (OSError, ValueError) as e:
        log.error("can't read %s: %s", path(), e)
        return _empty()


def _read_for_write() -> dict:
    """Daemon-side read under _lock. Corrupt content is moved aside under a
    unique name; other I/O errors raise rather than looking like an empty queue."""
    p = path()
    try:
        return _load()
    except ValueError as e:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        bad = p.with_name(f"{p.name}.{stamp}.bad")
        n = 1
        while bad.exists():
            bad = p.with_name(f"{p.name}.{stamp}-{n}.bad")
            n += 1
        log.error("%s is unreadable (%s); moving it to %s", p, e, bad.name)
        os.replace(p, bad)
        return _empty()


def _write(state: dict) -> None:
    p = path()
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=FILE + ".")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(state, f, indent=2)
        os.replace(tmp, p)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _update(fn):
    with _lock:
        state = _read_for_write()
        out = fn(state)
        _write(state)
        return out


# ---- entries ----

def make_entry(kind: str, payload) -> dict:
    uid = uuid.uuid4().hex[:8]
    if kind == "item":
        if not (isinstance(payload, dict) and payload.get("source") and payload.get("id")):
            raise ValueError("an item entry needs a source and an id")
        return {"uid": uid, "kind": "item", "item": payload}
    if kind == "station":
        if not (isinstance(payload, dict) and payload.get("url")):
            raise ValueError("a station entry needs a url")
        return {"uid": uid, "kind": "station",
                "station": {k: payload.get(k) for k in ("id", "name", "url")}}
    raise ValueError(f"unknown entry kind: {kind}")


def entry_title(entry: dict) -> str:
    if entry["kind"] == "station":
        st = entry["station"]
        return st.get("name") or st.get("url") or ""
    return entry["item"].get("title") or entry["item"].get("id") or ""


def entry_subtitle(entry: dict) -> str:
    if entry["kind"] == "station":
        return "radio"
    it = entry["item"]
    return " · ".join(x for x in (it.get("artist"), it.get("album")) if x)


def entry_label(entry: dict) -> str:
    artist = entry["item"].get("artist") if entry["kind"] == "item" else None
    title = entry_title(entry)
    return f"{title} — {artist}" if artist else title


# ---- queue edits ----

def add(entry: dict, at: int | None = None, play_next: bool = False) -> int:
    def go(state):
        entries = state["entries"]
        if play_next:
            i = 0
        elif at is None:
            i = len(entries)
        else:
            i = max(0, min(int(at), len(entries)))
        entries.insert(i, entry)
        return i
    return _update(go)


def remove(uid: str) -> bool:
    def go(state):
        before = len(state["entries"])
        state["entries"] = [e for e in state["entries"] if e["uid"] != uid]
        return len(state["entries"]) != before
    return _update(go)


def move(uid: str, to: int) -> bool:
    """`to` is the index in the list after the entry has been taken out."""
    def go(state):
        entries = state["entries"]
        for i, e in enumerate(entries):
            if e["uid"] == uid:
                entries.pop(i)
                entries.insert(max(0, min(int(to), len(entries))), e)
                return True
        return False
    return _update(go)


def take(uid: str) -> dict | None:
    """Remove an entry and everything queued before it; return the entry."""
    def go(state):
        for i, e in enumerate(state["entries"]):
            if e["uid"] == uid:
                del state["entries"][:i + 1]
                return e
        return None
    return _update(go)


def pop_head() -> dict | None:
    if not read()["entries"]:
        return None  # advance polls this; don't rewrite the file for nothing

    def go(state):
        return state["entries"].pop(0) if state["entries"] else None
    return _update(go)


def clear() -> None:
    _update(lambda state: state.update(entries=[]))


# ---- mode, now, context, history, resume ----

def set_mode(mode: str) -> None:
    if mode not in MODES:
        raise ValueError(f"unknown mode: {mode}")
    _update(lambda state: state.update(mode=mode))


def set_now(entry: dict | None) -> None:
    _update(lambda state: state.update(now=entry))


def set_context(items: list | None, current_id: str | None) -> None:
    """The list the playing item came from. Folders are dropped; no match for
    current_id means there is no list to walk."""
    def go(state):
        state["context"] = None
        if not items:
            return
        playable = [i for i in items if isinstance(i, dict) and i.get("kind") != "folder"]
        for n, i in enumerate(playable):
            if i.get("id") == current_id:
                state["context"] = {"items": playable, "index": n}
                return
    _update(go)


def next_in_context() -> dict | None:
    ctx = read()["context"]
    if not ctx or ctx["index"] + 1 >= len(ctx["items"]):
        return None

    def go(state):
        c = state["context"]
        if not c or c["index"] + 1 >= len(c["items"]):
            return None
        c["index"] += 1
        return c["items"][c["index"]]
    return _update(go)


def push_history(entry: dict) -> None:
    def go(state):
        state["history"].append(entry)
        del state["history"][:-HISTORY_MAX]
    _update(go)


def pop_history() -> dict | None:
    def go(state):
        return state["history"].pop() if state["history"] else None
    return _update(go)


def set_resume(entry: dict, pos: float, dur: float | None, head: bool = False) -> None:
    """head=True marks a placeholder for "whatever heads the queue", not a
    position in a real item; the queue may change under it."""
    def go(state):
        state["resume"] = {"entry": entry, "pos": float(pos), "dur": dur}
        if head:
            state["resume"]["head"] = True
    _update(go)


def clear_resume() -> None:
    _update(lambda state: state.update(resume=None))
