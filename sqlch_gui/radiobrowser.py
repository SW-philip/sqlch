"""RadioBrowser station search, discovery, and logo download."""

import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

from . import LOGOS_DIR

_RB_API = "de1.api.radio-browser.info"
_RB_MIRRORS = [
    "de1.api.radio-browser.info",
    "fr1.api.radio-browser.info",
    "nl1.api.radio-browser.info",
    "at1.api.radio-browser.info",
]

_search_cache: list[dict] = []


def _fetch_logo_url(url: str) -> bytes | None:
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "sqlch-gui/1.0"}
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.read()
    except Exception:
        return None


def download_logo(station_id: str, logo_url: str) -> str | None:
    """Download a station graphic icon from an external address provider. Returns local path."""
    if not logo_url or not logo_url.startswith("http"):
        return None
    ext = "png"
    if ".jpg" in logo_url.lower() or ".jpeg" in logo_url.lower():
        ext = "jpg"
    elif ".gif" in logo_url.lower():
        ext = "gif"

    dest = LOGOS_DIR / f"{station_id}.{ext}"
    if dest.exists():
        return str(dest)

    LOGOS_DIR.mkdir(parents=True, exist_ok=True)
    payload = _fetch_logo_url(logo_url)
    if payload:
        try:
            dest.write_bytes(payload)
            return str(dest)
        except Exception:
            pass
    return None


def search(query: str, limit: int = 20) -> list[dict]:
    """Execute generic title metadata directory lookup inside open streaming databases."""
    if not query.strip():
        return []
    url = f"https://{_RB_API}/json/stations/byname/{urllib.parse.quote(query)}"
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "sqlch-gui/1.0"}
        )
        with urllib.request.urlopen(req, timeout=4) as resp:
            raw = json.loads(resp.read().decode("utf-8", errors="replace"))
            results = []
            for item in raw[:limit]:
                results.append(
                    {
                        "name": item.get("name", "Unknown").strip(),
                        "url": item.get("url_resolved", item.get("url", "")),
                        "favicon": item.get("favicon", ""),
                        "tags": item.get("tags", ""),
                        "country": item.get("countrycode", ""),
                    }
                )
            return results
    except Exception:
        return []


def run_search(query: str) -> list[dict]:
    """Execute structure scans across the tracking registry array and load them index-mapped."""
    global _search_cache
    _search_cache.clear()
    items = search(query, limit=25)
    for i, item in enumerate(items, start=1):
        item["index"] = i
        _search_cache.append(item)
    return _search_cache


def add_from_search(number: int) -> str | None:
    """Add station #number from last run_search() result. Returns error string or None."""
    entry = next((r for r in _search_cache if r["index"] == number), None)
    if entry is None:
        return f"Result #{number} not found"
    from . import library

    return library.add_url(entry["name"], entry["url"])