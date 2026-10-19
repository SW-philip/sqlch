"""Podcasts from several directories (Apple Podcasts, Podcast Index) merged on
their feed URL. Episodes come from the show's RSS feed and play in mpv."""

import threading
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

from sqlch.sources import _podcast_dirs as dirs
from sqlch.sources import source_config
from sqlch.sources.base import make_item

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


def browse(path: str | None = None) -> list[dict]:
    _state.warning = None
    if not path or path == "section:following":
        return []
    raise ValueError("bad podcasts path")
