"""What plays next: queue advance, the radio/media mode, and parking media.

playqueue.py holds the state and knows nothing about playback; this module
drives player with it. Public functions take one lock because the daemon's
request thread and its end-of-playback tick both call in."""

import functools
import logging
import threading

from sqlch import sources
from sqlch.core import library, notify, player, playqueue, progress

log = logging.getLogger(__name__)

RESTART_AFTER = 3.0   # prev restarts the playing item when it is further in than this
NEAR_END = 10.0       # a parked item this close to its end starts over
MAX_FAILS = 3         # consecutive unplayable entries before advance gives up

_lock = threading.RLock()
_fails = 0


class PlayError(Exception):
    """An item could not be resolved or started; the message is user-facing."""


def _locked(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        with _lock:
            return fn(*args, **kwargs)
    return wrapper


def _resume_start(pos, dur) -> float | None:
    """Where a parked item restarts, or None to start it from the top."""
    if not isinstance(pos, (int, float)) or pos < progress.MIN_RESUME_SECS:
        return None
    if isinstance(dur, (int, float)) and dur > 0 and pos >= dur - NEAR_END:
        return None
    return float(pos)


def _play_item(item: dict, start: float | None = None, mode: str | None = None) -> None:
    src = sources.REGISTRY.get(item.get("source"))
    if src is None:
        raise PlayError(f"unknown source: {item.get('source')}")
    try:
        target = src.resolve(item, mode=mode) if mode else src.resolve(item)
    except Exception as e:
        raise PlayError(f"resolve failed: {e}") from e
    player.play_target(target, item, start=start)


def _park_head() -> None:
    """A radio entry never ends, so the next queued item is what media picks up."""
    waiting = [e for e in playqueue.read()["entries"] if e["kind"] == "item"]
    if waiting:
        playqueue.set_resume(waiting[0], 0.0, None)
    else:
        playqueue.clear_resume()


def _start_entry(entry: dict, start: float | None = None) -> bool:
    """Play one queue entry and record it as now playing. A failure is
    counted, announced and reported as False."""
    global _fails
    try:
        if entry["kind"] == "station":
            player.play_station(entry["station"])
            if player.current() is None:
                raise PlayError("station would not start")
            mode = "radio"
        else:
            _play_item(entry["item"], start)
            mode = "media"
    except Exception as e:
        _fails += 1
        notify.notify("sqlch error", f"Skipped {playqueue.entry_title(entry)}: {e}")
        return False
    _fails = 0
    playqueue.set_mode(mode)
    playqueue.set_now(entry)
    if mode == "radio":
        _park_head()
    return True


# ---- starting things ----

@_locked
def start_item(item: dict, *, context: list | None = None, resume: bool = False,
               mode: str | None = None) -> None:
    start = None
    if resume:
        start = progress.resume_point(progress.get(item.get("source"), item.get("id")))
    _play_item(item, start, mode)
    global _fails
    _fails = 0
    playqueue.set_mode("media")
    if item.get("id"):
        playqueue.set_now(playqueue.make_entry("item", item))
        playqueue.set_context(context, item["id"])


@_locked
def start_station(station: dict) -> None:
    park()
    player.play_station(station)
    if player.current() is None:
        return  # play_station refused (missing or bad url); it already said so
    playqueue.set_mode("radio")
    try:
        playqueue.set_now(playqueue.make_entry("station", station))
    except ValueError:
        playqueue.set_now(None)


@_locked
def play_entry(entry: dict) -> bool:
    """Play an entry the user picked (a drop on an idle player, a jump in the
    playlist). It starts a fresh run, so the old context no longer applies."""
    park()
    if not _start_entry(entry):
        return False
    playqueue.set_context(None, None)
    return True


@_locked
def stop() -> None:
    park()
    player.stop()
    playqueue.set_now(None)


# ---- parking ----

@_locked
def park() -> None:
    """Save where the playing item is, so flipping back to media (or a
    restart) can pick it up. Cheap enough to call every few seconds."""
    cur = player.current()
    if not cur or cur.get("type") != "item":
        return
    pos, dur = player.item_progress()
    # mpv reports nothing or 0 until the file is loaded
    if not isinstance(pos, (int, float)) or pos < 1:
        return
    try:
        entry = playqueue.make_entry("item", cur["item"])
    except ValueError:
        return
    playqueue.set_resume(entry, pos, dur)


# ---- moving on ----

@_locked
def advance() -> bool:
    """Play the next queue entry, else the next item of the list the playing
    item came from. False when nothing is left or too many entries failed."""
    global _fails
    finished = playqueue.read()["now"]
    while _fails < MAX_FAILS:
        entry = playqueue.pop_head()
        if entry is None:
            item = playqueue.next_in_context()
            if item is None:
                return False
            entry = playqueue.make_entry("item", item)
        if _start_entry(entry):
            if finished:
                playqueue.push_history(finished)
            return True
    _fails = 0
    notify.notify("sqlch", "Queue stopped: too many entries failed to play")
    return False


def _cycle_station(forward: bool) -> None:
    cur = player.current()
    if cur:
        sid = (cur.get("item") or {}).get("id")
        st = (library.next_station if forward else library.prev_station)(sid)
    else:
        stations = library.list_stations()
        st = (stations[0] if forward else stations[-1]) if stations else None
    if st:
        start_station(st)


@_locked
def next_cmd() -> None:
    if playqueue.read()["mode"] == "radio":
        _cycle_station(True)
    else:
        advance()


@_locked
def prev_cmd() -> None:
    state = playqueue.read()
    if state["mode"] == "radio":
        _cycle_station(False)
        return
    if player.current() is None:
        return
    pos, _ = player.item_progress()
    if (isinstance(pos, (int, float)) and pos > RESTART_AFTER) or not state["history"]:
        player.seek(0.0)
        return
    entry = playqueue.pop_history()
    if _start_entry(entry):
        if state["now"]:
            playqueue.add(state["now"], play_next=True)  # next goes forward again
        if entry["kind"] == "station":
            _park_head()
    else:
        playqueue.push_history(entry)


@_locked
def set_mode(mode: str) -> None:
    if mode not in playqueue.MODES:
        raise ValueError(f"unknown mode: {mode}")
    state = playqueue.read()
    if mode == state["mode"]:
        return
    if mode == "radio":
        st = library.last_played_station()
        if st:
            start_station(st)
        else:
            park()
            playqueue.set_mode("radio")
        return
    playqueue.set_mode("media")  # even if nothing starts, next/prev now follow the queue
    resume = state["resume"]
    if resume:
        entry = resume["entry"]
        playqueue.remove(entry["uid"])  # it may also sit at the head of the queue
        playqueue.clear_resume()
        if _start_entry(entry, start=_resume_start(resume["pos"], resume["dur"])):
            return
    advance()


@_locked
def tick() -> None:
    """About once a second: move on when the playing item has ended."""
    cur = player.current()
    if not cur or cur.get("type") != "item" or not player.playback_ended():
        return
    if advance():
        return
    if cur.get("handoff"):
        return  # the external player may carry on by itself (autoplay)
    player.stop(notify_user=False)
    playqueue.set_now(None)
    playqueue.clear_resume()


# ---- for MPRIS ----

def can_go_next() -> bool:
    s = playqueue.read()
    if s["mode"] == "radio":
        return bool(library.list_stations())
    ctx = s["context"]
    return bool(s["entries"]) or bool(ctx and ctx["index"] + 1 < len(ctx["items"]))


def can_go_previous() -> bool:
    s = playqueue.read()
    if s["mode"] == "radio":
        return bool(library.list_stations())
    return bool(s["history"]) or s["now"] is not None
