"""RadioBrowser station search, discovery, and logo download."""

import json
import urllib.parse
import urllib.request

from . import LOGOS_DIR

_RB_API = "de1.api.radio-browser.info"

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


def _with_params(url: str, **params: object) -> str:
    """Append query params to a URL, respecting any it already carries."""
    sep = "&" if "?" in url else "?"
    return url + sep + urllib.parse.urlencode(params)


def _fetch_stations(url: str, limit: int, offset: int = 0) -> list[dict]:
    """Fetch and normalize a RadioBrowser station listing from a query URL."""
    url = _with_params(url, limit=limit, offset=offset)
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "sqlch-gui/1.0"}
        )
        with urllib.request.urlopen(req, timeout=4) as resp:
            raw = json.loads(resp.read().decode("utf-8", errors="replace"))
        return [
            {
                "name": item.get("name", "Unknown").strip(),
                "url": item.get("url_resolved", item.get("url", "")),
                "favicon": item.get("favicon", ""),
                "tags": item.get("tags", ""),
                "country": item.get("countrycode", ""),
                "bitrate": item.get("bitrate"),
            }
            for item in raw[:limit]
        ]
    except Exception:
        return []


def search(query: str, limit: int = 25, offset: int = 0) -> list[dict]:
    """Look a station up by name in the RadioBrowser directory."""
    if not query.strip():
        return []
    url = (
        f"https://{_RB_API}/json/stations/byname/"
        f"{urllib.parse.quote(query, safe='')}?hidebroken=true&order=name"
    )
    return _fetch_stations(url, limit, offset)


def search_by_tag(tag: str, limit: int = 25, offset: int = 0) -> list[dict]:
    """Look stations up by genre/tag, most-voted first."""
    tag = tag.strip().lower()
    if not tag:
        return []
    # bytag matching is case-sensitive server-side and RadioBrowser tags are
    # normalized lowercase, so lowercasing here is what makes "Rock" match.
    url = (
        f"https://{_RB_API}/json/stations/bytag/{urllib.parse.quote(tag, safe='')}"
        "?order=votes&reverse=true&hidebroken=true"
    )
    return _fetch_stations(url, limit, offset)
