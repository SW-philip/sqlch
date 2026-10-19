"""Podcast directory clients: Apple Podcasts search and Podcast Index.
urllib only, the gui env has no requests. Each search returns plain show
dicts {feed_url, title, artist, genre, image}; podcasts.py merges them."""

import hashlib
import json
import os
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

TIMEOUT = 6
LIMIT = 25
UA = "sqlch/1.0"
DEFAULT_ENV_FILE = "/run/secrets/podcastindex_env"


def _apple_base() -> str:
    return os.environ.get("SQLCH_APPLE_PODCASTS_BASE", "https://itunes.apple.com")


def _pi_base() -> str:
    return os.environ.get("SQLCH_PODCASTINDEX_BASE", "https://api.podcastindex.org/api/1.0")


def _fetch_json(url: str, headers: dict | None = None) -> dict:
    req = Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read())


def _show(feed_url, title, artist, genre, image) -> dict:
    return {"feed_url": feed_url, "title": title, "artist": artist or None,
            "genre": genre or None, "image": image or None}


def apple_search(term: str) -> list[dict]:
    q = urlencode({"media": "podcast", "entity": "podcast", "term": term, "limit": LIMIT})
    data = _fetch_json(f"{_apple_base()}/search?{q}")
    return [_show(r["feedUrl"], r["collectionName"], r.get("artistName"),
                  r.get("primaryGenreName"), r.get("artworkUrl600") or r.get("artworkUrl100"))
            for r in data.get("results") or []
            if isinstance(r, dict) and r.get("feedUrl") and r.get("collectionName")]


def pi_credentials(env_file: str | None = None) -> tuple[str, str] | None:
    key = os.environ.get("PODCASTINDEX_API_KEY")
    sec = os.environ.get("PODCASTINDEX_API_SECRET")
    if not (key and sec):
        try:
            text = Path(env_file or DEFAULT_ENV_FILE).expanduser().read_text()
        except OSError:
            return None
        vals = dict(line.split("=", 1) for line in text.splitlines()
                    if "=" in line and not line.lstrip().startswith("#"))
        key = vals.get("PODCASTINDEX_API_KEY", "").strip().strip("\"'")
        sec = vals.get("PODCASTINDEX_API_SECRET", "").strip().strip("\"'")
    return (key, sec) if key and sec else None


def pi_headers(key: str, secret: str, now: float) -> dict:
    date = str(int(now))
    return {"X-Auth-Key": key, "X-Auth-Date": date,
            "Authorization": hashlib.sha1((key + secret + date).encode()).hexdigest()}


def _first_category(cats) -> str | None:
    if isinstance(cats, dict) and cats:
        return next(iter(cats.values()))
    return None


def pi_search(term: str, creds: tuple[str, str], now=time.time) -> list[dict]:
    q = urlencode({"q": term, "max": LIMIT})
    data = _fetch_json(f"{_pi_base()}/search/byterm?{q}", pi_headers(*creds, now()))
    return [_show(f["url"], f["title"], f.get("author"),
                  _first_category(f.get("categories")), f.get("artwork") or f.get("image"))
            for f in data.get("feeds") or []
            if isinstance(f, dict) and f.get("url") and f.get("title")]
