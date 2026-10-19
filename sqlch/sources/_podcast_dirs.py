"""Podcast directory clients: Apple Podcasts search and Podcast Index.
urllib only, the gui env has no requests. Each search returns plain show
dicts {feed_url, title, artist, genre, image}; podcasts.py merges them."""

import json
import os
from urllib.parse import urlencode
from urllib.request import Request, urlopen

TIMEOUT = 6
LIMIT = 25
UA = "sqlch/1.0"


def _apple_base() -> str:
    return os.environ.get("SQLCH_APPLE_PODCASTS_BASE", "https://itunes.apple.com")


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
