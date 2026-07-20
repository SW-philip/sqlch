"""ICY track metadata, enriched cache, cover art, and sqlch enrich bridge."""

import hashlib
import html
import json
import re
import socket
import threading
import urllib.request
from pathlib import Path

from . import COVERS_DIR, ENRICHED_JSON, MPV_SOCK


def _parse_iheart(title: str) -> tuple[str | None, str | None]:
    """iHeart wraps titles in tracking attrs: Artist - text="Song" song_spot="M" ..."""
    spot = re.search(r'song_spot="(\w)"', title)
    if spot and spot.group(1).upper() != "M":
        return None, None  # promo/ad spot, not music
    song_m = re.search(r'text="([^"]*)"', title)
    artist_m = re.match(r'^(.*?)\s*-\s*text=', title)
    song = song_m.group(1).strip() if song_m else ""
    artist = artist_m.group(1).strip() if artist_m else ""
    if not artist and not song:
        return None, None
    return artist or None, song or None


def parse_icy(title: str) -> tuple[str | None, str | None]:
    if not title:
        return None, None
    title = html.unescape(title)
    if "song_spot=" in title:
        return _parse_iheart(title)
    if " - " in title:
        artist, track = title.split(" - ", 1)
    elif "-" in title:
        artist, track = title.split("-", 1)
    else:
        return None, title.strip()
    return artist.strip() or None, track.strip() or None


def download_cover(url: str, dest_path: Path) -> bool:
    try:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(url, headers={"User-Agent": "sqlch-gui/1.0"})
        with urllib.request.urlopen(req, timeout=3) as response:
            dest_path.write_bytes(response.read())
        return True
    except Exception:
        return False


def _strip_live_qualifier(title: str) -> str:
    if not title:
        return ""
    return re.sub(
        r"\s*[\(\[][^\]\)]*live[^\]\)]*[\)\]]", "", title, flags=re.IGNORECASE
    ).strip()


def _norm(s: str) -> str:
    return " ".join(s.lower().strip().split())


def _resolve_cover_entry(artist: str, title: str) -> str | None:
    if not artist or not title:
        return None
    clean_t = _strip_live_qualifier(title)
    h = hashlib.md5(f"{artist.lower()}|{clean_t.lower()}".encode()).hexdigest()
    local_path = COVERS_DIR / f"{h}.jpg"
    if local_path.exists():
        return str(local_path)
    return None


def run_enrich(artist: str, title: str):
    if not artist or not title:
        return
    try:
        from sqlch.core.enrich import enrich_track
        threading.Thread(target=enrich_track, args=(artist, title), daemon=True).start()
    except Exception:
        pass


def _mpv_metadata() -> tuple[str | None, str | None]:
    if not MPV_SOCK.exists():
        return None, None
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(0.3)
            s.connect(str(MPV_SOCK))
            s.sendall(
                (json.dumps({"command": ["get_property", "metadata"]}) + "\n").encode()
            )
            buf = b""
            while not buf.endswith(b"\n"):
                chunk = s.recv(4096)
                if not chunk:
                    break
                buf += chunk
        if buf.strip():
            resp = json.loads(buf.decode())
            if resp.get("error") == "success" and resp.get("data"):
                d = resp["data"]
                icy = d.get("icy-title") or d.get("title")
                if icy:
                    return parse_icy(icy)
    except Exception:
        pass
    return None, None


def _playerctl_track() -> tuple[str | None, str | None]:
    import subprocess
    try:
        r = subprocess.run(
            ["playerctl", "-p", "mpv", "metadata", "--format", "{{title}}"],
            capture_output=True,
            text=True,
            timeout=0.5,
        )
        if r.returncode == 0 and r.stdout.strip():
            return parse_icy(r.stdout.strip())
    except Exception:
        pass
    return None, None


def get_icy_track() -> tuple[str | None, str | None]:
    a, t = _mpv_metadata()
    if a or t:
        return a, t
    return _playerctl_track()


def get_icy_genre() -> str | None:
    if not MPV_SOCK.exists():
        return None
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(0.3)
            s.connect(str(MPV_SOCK))
            s.sendall(
                (
                    json.dumps({"command": ["get_property", "filtered-metadata"]})
                    + "\n"
                ).encode()
            )
            buf = b""
            while not buf.endswith(b"\n"):
                chunk = s.recv(4096)
                if not chunk:
                    break
                buf += chunk
        if buf.strip():
            resp = json.loads(buf.decode())
            if resp.get("error") == "success" and resp.get("data"):
                d = resp["data"]
                for k in ["icy-genre", "genre", "icy-name"]:
                    if d.get(k):
                        return d[k]
    except Exception:
        pass
    return None


def get_enriched_meta(artist: str, title: str) -> dict | None:
    if not artist or not title or not ENRICHED_JSON.exists():
        return None
    try:
        data = json.loads(ENRICHED_JSON.read_text())
        clean_t = _strip_live_qualifier(title)
        key = f"{_norm(artist)}::{_norm(clean_t)}"
        return data.get(key)
    except Exception:
        return None


def get_cover_info(artist: str, title: str) -> tuple[str | None, str | None]:
    local = _resolve_cover_entry(artist, title)
    if local:
        return local, "local"
    meta = get_enriched_meta(artist, title)
    if meta and meta.get("cover"):
        return meta["cover"], "remote"
    return None, None
