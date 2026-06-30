"""ICY track metadata, enriched cache, cover art, and sqlch enrich bridge."""

import hashlib
import json
import os
import re
import socket
import subprocess
import urllib.request
from pathlib import Path

from . import COVERS_DIR, ENRICHED_JSON, MPV_SOCK


def _find_sqlch_python() -> dict[str, str]:
    env = os.environ.copy()
    try:
        r = subprocess.run(["which", "sqlch-enrich"], capture_output=True, text=True)
        if r.returncode == 0:
            return env
    except Exception:
        pass

    for p in [
        "~/.config/nixos",
        "~/nixos",
        "~/dotfiles",
        "~/.config/home-manager",
    ]:
        expanded = Path(p).expanduser()
        if expanded.exists():
            for script in expanded.glob("**/sqlch-enrich"):
                if script.is_file():
                    try:
                        text = script.read_text()
                        m = re.search(r"exec\s+([^\s]+python[^\s]*)\s+", text)
                        if m:
                            env["SQLCH_ENRICH_PYTHON"] = m.group(1)
                            return env
                    except Exception:
                        pass
    return env


_SQLCH_PY_ENV = _find_sqlch_python()


def download_cover(url: str, dest_path: Path) -> bool:
    """Download cover art image payload with the current package agent identification."""
    try:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(
            url, headers={"User-Agent": "sqlch-gui/1.0"}
        )
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
    """Trigger the enrichment engine subprocess to harvest artwork metadata links asynchronously."""
    if not artist or not title:
        return
    try:
        cmd = ["sqlch-enrich", artist, title]
        subprocess.Popen(
            cmd,
            env=_SQLCH_PY_ENV,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
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
                return d.get("artist"), d.get("title")
    except Exception:
        pass
    return None, None


def _playerctl_track() -> tuple[str | None, str | None]:
    try:
        r = subprocess.run(
            ["playerctl", "-p", "mpv", "metadata", "--format", "{{artist}}||{{title}}"],
            capture_output=True,
            text=True,
            timeout=0.5,
        )
        if r.returncode == 0 and "||" in r.stdout:
            parts = r.stdout.strip().split("||", 1)
            a = parts[0].strip() if parts[0].strip() else None
            t = parts[1].strip() if parts[1].strip() else None
            return a, t
    except Exception:
        pass
    return None, None


def get_icy_track() -> tuple[str | None, str | None]:
    """Retrieve raw streaming metadata using direct socket checking or shell playerctl tools."""
    a, t = _mpv_metadata()
    if a or t:
        return a, t
    return _playerctl_track()


def get_icy_genre() -> str | None:
    """Retrieve station genre info field strings from current live audio streams."""
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
    """Check storage layers for enriched details matched to active tracks."""
    if not artist or not title or not ENRICHED_JSON.exists():
        return None
    try:
        data = json.loads(ENRICHED_JSON.read_text())
        clean_t = _strip_live_qualifier(title)
        key = f"{artist.lower()}|{clean_t.lower()}"
        return data.get(key)
    except Exception:
        return None


def get_cover_info(artist: str, title: str) -> tuple[str | None, str | None]:
    """Resolve full asset location pointers for local or external media graphic thumbnails."""
    local = _resolve_cover_entry(artist, title)
    if local:
        return local, "local"
    meta = get_enriched_meta(artist, title)
    if meta and meta.get("cover_url"):
        return meta["cover_url"], "remote"
    return None, None