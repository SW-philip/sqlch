"""Polls followed YouTube channels and queues in-app notices for new uploads.

The gui drains the queue over the control socket (`drain_notices`) and shows
each notice as a toast."""

import logging
import threading
import time
from collections import deque
from typing import Callable

from sqlch.core import follows

log = logging.getLogger(__name__)

SUMMARY_OVER = 3     # more new videos than this from one channel -> one summary notice
GIVE_UP_AFTER = 10   # consecutive failures before a single "can't reach" notice
MAX_NOTICES = 20
DEFAULT_INTERVAL = 30 * 60


class Watcher:
    def __init__(self, fetch, store=follows, clock=time.time):
        self._fetch = fetch
        self._store = store
        self._clock = clock
        self._notices: deque[str] = deque(maxlen=MAX_NOTICES)
        self._lock = threading.Lock()
        self._fails: dict[str, int] = {}

    def _push(self, text: str) -> None:
        with self._lock:
            self._notices.append(text)

    def drain(self) -> list[str]:
        with self._lock:
            out = list(self._notices)
            self._notices.clear()
        return out

    def poll_once(self) -> None:
        for ch in self._store.list_follows():
            cid = ch["channel_id"]
            name = ch.get("name") or cid
            try:
                entries = self._fetch(cid)
            except Exception as e:
                n = self._fails.get(cid, 0) + 1
                self._fails[cid] = n
                log.warning("feed for %s failed (%d): %s", name, n, e)
                if n == GIVE_UP_AFTER:
                    self._push(f"Can't reach {name}")
                continue
            self._fails.pop(cid, None)
            if not entries:
                continue
            newest = entries[0]["id"]
            last = ch.get("last_video_id")
            if last is not None and newest != last:
                ids = [e["id"] for e in entries]
                new = entries[:ids.index(last)] if last in ids else entries
                if len(new) > SUMMARY_OVER:
                    self._push(f"{name}: {len(new)} new videos")
                else:
                    for e in reversed(new):
                        self._push(f"{name}: {e['title']}")
            self._store.record_seen(cid, newest, self._clock())

    def run(self, interval: Callable[[], float]) -> None:
        while True:
            try:
                self.poll_once()
            except Exception:
                log.exception("watcher poll failed")
            try:
                wait = interval()
            except Exception:
                log.exception("watcher interval failed; using default")
                wait = DEFAULT_INTERVAL
            time.sleep(wait)


_watcher: Watcher | None = None


def start(fetch, interval: Callable[[], float]) -> None:
    global _watcher
    _watcher = Watcher(fetch)
    threading.Thread(target=_watcher.run, args=(interval,),
                     daemon=True, name="watcher").start()


def drain() -> list[str]:
    return _watcher.drain() if _watcher else []
