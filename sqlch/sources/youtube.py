"""YouTube via yt-dlp: search, configured channel/playlist shortcuts, and
playback through mpv's own ytdl hook (which merges separate video and audio
streams a single URL could not describe)."""

import json
import os
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from urllib.request import urlopen

from sqlch.core import follows
from sqlch.core.paths import cache_dir
from sqlch.sources import source_config
from sqlch.sources.base import Target, make_item

NAME = "youtube"
TITLE = "YOUTUBE"
LABEL = "YouTube"
HAS_DATES = True
HINT = ("Install yt-dlp. Add channels or playlists to browse under "
        'sources.youtube.shortcuts: [{"name": "...", "url": "https://..."}]')

SEARCH_LIMIT = 25
LIST_LIMIT = 100
TIMEOUT = 40
THUMB = "https://i.ytimg.com/vi/{}/hqdefault.jpg"
WATCH = "https://www.youtube.com/watch?v={}"
CHANNEL_VIDEOS = "https://www.youtube.com/channel/{}/videos"
FEED = "https://www.youtube.com/feeds/videos.xml?channel_id={}"
DEFAULT_POLL_MINUTES = 30
_CHANNEL_ID = re.compile(r"^UC[\w-]{22}$")
_ATOM = "{http://www.w3.org/2005/Atom}"
_YT = "{http://www.youtube.com/xml/schemas/2015}"


def ytdlp_path() -> str | None:
    return os.environ.get("SQLCH_YTDLP") or shutil.which("yt-dlp")


def available() -> bool:
    return ytdlp_path() is not None


def _shortcuts() -> list[dict]:
    raw = source_config(NAME).get("shortcuts")
    return [s for s in raw if isinstance(s, dict) and s.get("name") and s.get("url")] \
        if isinstance(raw, list) else []


def _extract(target: str, limit: int) -> list[dict]:
    exe = ytdlp_path()
    if exe is None:
        raise RuntimeError("yt-dlp not found")
    proc = subprocess.run(
        [exe, "--flat-playlist", "--no-warnings", "--playlist-end", str(limit),
         "--extractor-args", "youtubetab:approximate_date", "-J", "--", target],
        capture_output=True, text=True, timeout=TIMEOUT)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip().splitlines()[-1] if proc.stderr.strip()
                           else "yt-dlp failed")
    return json.loads(proc.stdout).get("entries") or []


def _is_folder(e: dict) -> bool:
    return e.get("_type") == "playlist" or e.get("ie_key") in ("YoutubeTab", "YoutubePlaylist")


def _to_item(e: dict) -> dict | None:
    if not e.get("id"):
        return None
    title = e.get("title") or e["id"]
    if _is_folder(e):
        url = e.get("url") or e.get("webpage_url")
        if not url:
            return None
        return make_item(NAME, e["id"], title, kind="folder", path=url,
                         artist=e.get("channel") or e.get("uploader"))
    return make_item(NAME, e["id"], title, kind="video",
                     artist=e.get("channel") or e.get("uploader"),
                     duration=e.get("duration"), channel_id=e.get("channel_id"),
                     date=e.get("timestamp"))


def _items(entries: list[dict]) -> list[dict]:
    return [i for i in map(_to_item, entries) if i]


def sections() -> list[dict]:
    return [{"id": "channels", "title": "CHANNELS"}]


def _channels() -> list[dict]:
    items = [make_item(NAME, f["channel_id"], f.get("name") or f["channel_id"],
                       kind="folder", path=CHANNEL_VIDEOS.format(f["channel_id"]),
                       channel_id=f["channel_id"])
             for f in follows.list_follows()]
    items += [make_item(NAME, s["url"], s["name"], kind="folder", path=s["url"])
              for s in _shortcuts()]
    return items


def browse(path: str | None = None) -> list[dict]:
    if not path or path == "section:channels":
        return _channels()
    if not path.startswith("https://"):
        raise ValueError("bad youtube path")
    return _items(_extract(path, LIST_LIMIT))


def valid_channel_id(channel_id: str) -> bool:
    return bool(_CHANNEL_ID.match(channel_id or ""))


def parse_feed(xml: bytes) -> list[dict]:
    # A real feed never declares a DTD; refusing one rules out entity-expansion
    # tricks without adding a dependency.
    if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:
        raise ValueError("feed declares a DTD")
    out = []
    for entry in ET.fromstring(xml).iter(_ATOM + "entry"):
        vid = entry.findtext(_YT + "videoId")
        if vid:
            out.append({"id": vid, "title": entry.findtext(_ATOM + "title") or vid})
    return out


def fetch_feed(channel_id: str) -> list[dict]:
    if not valid_channel_id(channel_id):
        raise ValueError("bad channel id")
    with urlopen(FEED.format(channel_id), timeout=8) as r:
        return parse_feed(r.read())


def poll_seconds() -> float:
    try:
        cfg = source_config(NAME)
    except Exception:
        cfg = {}
    minutes = cfg.get("poll_minutes") if isinstance(cfg, dict) else None
    if isinstance(minutes, bool) or not isinstance(minutes, (int, float)):
        minutes = DEFAULT_POLL_MINUTES
    return max(1, minutes) * 60


def search(query: str) -> list[dict]:
    query = (query or "").strip()
    if not query:
        return []
    return _items(_extract(f"ytsearch{SEARCH_LIMIT}:{query}", SEARCH_LIMIT))


def _cover(vid: str) -> str | None:
    dest = cache_dir() / "youtube" / f"{vid}.jpg"
    if dest.is_file():
        return str(dest)
    try:
        with urlopen(THUMB.format(vid), timeout=8) as r:
            data = r.read()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    except OSError:
        return None
    return str(dest)


def thumbnail(item: dict) -> str | None:
    """Cached cover for a listing row; blocking, so call it off the main thread."""
    vid = item.get("id")
    if not vid or not all(c.isalnum() or c in "_-" for c in vid):
        return None
    return _cover(vid)


def resolve(item: dict) -> Target:
    vid = item["id"]
    if not vid or not all(c.isalnum() or c in "_-" for c in vid):
        raise ValueError("bad youtube id")
    meta = {"title": item.get("title"), "artist": item.get("artist"),
            "album": None, "art": _cover(vid)}
    return Target(WATCH.format(vid), True, meta)
