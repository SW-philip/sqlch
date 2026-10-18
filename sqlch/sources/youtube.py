"""YouTube via yt-dlp: search, configured channel/playlist shortcuts, and
playback through mpv's own ytdl hook (which merges separate video and audio
streams a single URL could not describe)."""

import json
import os
import shutil
import subprocess
from urllib.request import urlopen

from sqlch.core.paths import cache_dir
from sqlch.sources import source_config
from sqlch.sources.base import Target, make_item

NAME = "youtube"
TITLE = "YOUTUBE"
LABEL = "YouTube"
HINT = ("Install yt-dlp. Add channels or playlists to browse under "
        'sources.youtube.shortcuts: [{"name": "...", "url": "https://..."}]')

SEARCH_LIMIT = 25
LIST_LIMIT = 100
TIMEOUT = 40
THUMB = "https://i.ytimg.com/vi/{}/hqdefault.jpg"
WATCH = "https://www.youtube.com/watch?v={}"


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
         "-J", "--", target],
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
                     duration=e.get("duration"))


def _items(entries: list[dict]) -> list[dict]:
    return [i for i in map(_to_item, entries) if i]


def browse(path: str | None = None) -> list[dict]:
    if not path:
        return [make_item(NAME, s["url"], s["name"], kind="folder", path=s["url"])
                for s in _shortcuts()]
    if not path.startswith("https://"):
        raise ValueError("bad youtube path")
    return _items(_extract(path, LIST_LIMIT))


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


def resolve(item: dict) -> Target:
    vid = item["id"]
    if not vid or not all(c.isalnum() or c in "_-" for c in vid):
        raise ValueError("bad youtube id")
    meta = {"title": item.get("title"), "artist": item.get("artist"),
            "album": None, "art": _cover(vid)}
    return Target(WATCH.format(vid), True, meta)
