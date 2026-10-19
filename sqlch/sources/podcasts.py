"""Podcasts from several directories (Apple Podcasts, Podcast Index) merged on
their feed URL. Episodes come from the show's RSS feed and play in mpv."""

import hashlib
import os
import tempfile
import threading
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from sqlch.core import follows
from sqlch.core.paths import cache_dir
from sqlch.sources import _podcast_dirs as dirs
from sqlch.sources import source_config
from sqlch.sources.base import Target, make_item

NAME = "podcasts"
TITLE = "PODCASTS"
LABEL = "Podcasts"
HINT = ("Searches Apple Podcasts. Put PODCASTINDEX_API_KEY and "
        "PODCASTINDEX_API_SECRET in /run/secrets/podcastindex_env to search "
        "Podcast Index too.")
HAS_DATES = True
GROUPINGS = ("source", "genre", "az")
# Directory id -> header title and the short tag shown on merged rows, in display order.
PROVIDERS = {"apple": {"title": "APPLE PODCASTS", "short": "apple", "label": "Apple Podcasts"},
             "podcastindex": {"title": "PODCAST INDEX", "short": "pi", "label": "Podcast Index"}}

_state = threading.local()


def available() -> bool:
    return True


def sections() -> list[dict]:
    return [{"id": "following", "title": "FOLLOWING"}]


def last_warning() -> str | None:
    """A note about directories that failed during this thread's last search."""
    return getattr(_state, "warning", None)


def norm_feed(url: str) -> str:
    p = urlsplit(url.strip())
    host = p.netloc.lower().removeprefix("www.")
    return host + p.path.rstrip("/") + (f"?{p.query}" if p.query else "")


def _directories() -> list[tuple]:
    out = [("apple", dirs.apple_search)]
    cfg = source_config(NAME)
    creds = dirs.pi_credentials(cfg.get("env_file") if isinstance(cfg, dict) else None)
    if creds:
        out.append(("podcastindex", lambda q: dirs.pi_search(q, creds)))
    return out


def show_item(s: dict, providers: list[str]) -> dict:
    item = make_item(NAME, s["feed_url"], s["title"], kind="folder",
                     path=f"feed:{s['feed_url']}", artist=s.get("artist"),
                     genre=s.get("genre"), providers=list(providers),
                     feed_url=s["feed_url"])
    item["image"] = s.get("image")
    return item


def _merge(batches: list[tuple]) -> list[dict]:
    merged: dict[str, dict] = {}
    for provider, shows in batches:
        for s in shows:
            key = norm_feed(s["feed_url"])
            m = merged.get(key)
            if m is None:
                merged[key] = show_item(s, [provider])
                continue
            if provider not in m["providers"]:
                m["providers"].append(provider)
            for f in ("genre", "artist", "image"):
                m[f] = m[f] or s.get(f)
    return list(merged.values())


def search(query: str) -> list[dict]:
    _state.warning = None
    query = (query or "").strip()
    if not query:
        return []
    directories = _directories()
    with ThreadPoolExecutor(max_workers=len(directories)) as ex:
        futures = [(name, ex.submit(fn, query)) for name, fn in directories]
    batches, failed = [], []
    for name, fut in futures:
        try:
            batches.append((name, fut.result()))
        except Exception as e:
            failed.append((name, e))
    if not batches:
        raise RuntimeError(f"no podcast directory answered: {failed[0][1]}")
    if failed:
        _state.warning = " and ".join(PROVIDERS[n]["label"] for n, _ in failed) + " unavailable"
    return _merge(batches)


FEED_LIMIT = 100
MAX_FEED_BYTES = 10 * 1024 * 1024
TIMEOUT = 8
MAX_ART_BYTES = 2 * 1024 * 1024
ART_TIMEOUT = 3
_ITUNES = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"


def _is_http(url) -> bool:
    return isinstance(url, str) and url.startswith(("http://", "https://"))


def _download(url: str, limit: int, timeout: float = TIMEOUT) -> bytes:
    req = Request(url, headers={"User-Agent": dirs.UA})
    with urlopen(req, timeout=timeout) as r:
        return r.read(limit)


def _fetch_feed(url: str) -> bytes:
    data = _download(url, MAX_FEED_BYTES + 1)
    if len(data) > MAX_FEED_BYTES:
        raise ValueError("feed too large")
    return data


def parse_duration(text) -> int | None:
    text = (text or "").strip()
    if not text:
        return None
    parts = text.split(":")
    if len(parts) > 3:
        return None
    try:
        nums = [int(float(p)) for p in parts]
    except (ValueError, OverflowError):
        return None
    if any(n < 0 for n in nums):
        return None
    secs = 0
    for n in nums:
        secs = secs * 60 + n
    return secs if secs > 0 else None


def _date(text) -> int | None:
    try:
        dt = parsedate_to_datetime(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except (TypeError, ValueError, IndexError, OverflowError):
        return None


def _image(node) -> str | None:
    el = node.find(f"{_ITUNES}image")
    href = el.get("href") if el is not None else None
    return href or (node.findtext("image/url") or "").strip() or None


def parse_feed(data: bytes, feed_url: str) -> list[dict]:
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        raise ValueError("feed is not valid XML") from None
    channel = root.find("channel")
    if channel is None:
        raise ValueError("not an RSS feed")
    show = (channel.findtext("title") or "").strip() or feed_url
    show_image = _image(channel)
    episodes = []
    for it in channel.findall("item"):
        enc = it.find("enclosure")
        url = (enc.get("url") or "").strip() if enc is not None else None
        if not url:
            continue
        guid = (it.findtext("guid") or "").strip() or url
        ep = make_item(NAME, guid, (it.findtext("title") or "").strip() or "Untitled",
                       artist=show, date=_date(it.findtext("pubDate")),
                       duration=parse_duration(it.findtext(f"{_ITUNES}duration")), url=url)
        ep["image"] = _image(it) or show_image
        episodes.append(ep)
    episodes.sort(key=lambda e: e["date"] or 0, reverse=True)
    return episodes[:FEED_LIMIT]


def _cached_art(url) -> str | None:
    if not _is_http(url):
        return None
    dest = cache_dir() / "podcasts" / (hashlib.sha1(url.encode()).hexdigest()[:20] + ".img")
    if dest.is_file():
        return str(dest)
    try:
        data = _download(url, MAX_ART_BYTES, timeout=ART_TIMEOUT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=dest.parent, suffix=".part")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.replace(tmp, dest)
        except BaseException:
            os.unlink(tmp)
            raise
    except Exception:
        return None
    return str(dest)


def resolve(item: dict) -> Target:
    url = item.get("url")
    if not _is_http(url):
        raise ValueError("episode has no audio url")
    show = item.get("artist")
    meta = {"title": item.get("title"), "artist": show, "album": show,
            "art": _cached_art(item.get("image"))}
    return Target(url, False, meta)


def browse(path: str | None = None) -> list[dict]:
    _state.warning = None
    if not path or path == "section:following":
        return [show_item(r, r.get("providers") or []) for r in follows.list_podcasts()]
    kind, _, url = path.partition(":")
    if kind != "feed" or not _is_http(url):
        raise ValueError("bad podcasts path")
    return parse_feed(_fetch_feed(url), url)
