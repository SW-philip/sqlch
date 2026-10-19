"""Spotify catalog browsing and search with app (client-credentials) access.
Playback is handed to the Spotify desktop app, see sqlch/core/handoff.py."""

import base64
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from sqlch.core.paths import cache_dir
from sqlch.core import spotify_auth
from sqlch.sources import source_config
from sqlch.sources.base import Target, make_item

NAME = "spotify"
TITLE = "SPOTIFY"
LABEL = "Spotify"
HINT = ("Needs SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET in "
        "/run/secrets/spotify_env, and the Spotify desktop app to play. "
        "Run `sqlch spotify-login` to see your playlists and followed artists.")

DEFAULT_ENV_FILE = "/run/secrets/spotify_env"
TIMEOUT = 8
SEARCH_LIMIT = 10
LIST_LIMIT = 50
MAX_ITEMS = 200
PAGE = 50
LOGIN_NEEDED = f"Not logged in to Spotify: {spotify_auth.LOGIN_HINT}"
KINDS = ("artist", "album", "playlist")
_ID = re.compile(r"^[A-Za-z0-9]+$")


def _api() -> str:
    return os.environ.get("SQLCH_SPOTIFY_BASE", "https://api.spotify.com/v1")


def _auth_base() -> str:
    return os.environ.get("SQLCH_SPOTIFY_AUTH_BASE", "https://accounts.spotify.com")


def _credentials() -> tuple[str, str] | None:
    cid, sec = os.environ.get("SPOTIFY_CLIENT_ID"), os.environ.get("SPOTIFY_CLIENT_SECRET")
    if not (cid and sec):
        cfg = source_config(NAME)
        path = Path((cfg.get("env_file") if isinstance(cfg, dict) else None)
                    or DEFAULT_ENV_FILE).expanduser()
        try:
            vals = dict(line.split("=", 1) for line in path.read_text().splitlines()
                        if "=" in line and not line.lstrip().startswith("#"))
        except OSError:
            return None
        cid = vals.get("SPOTIFY_CLIENT_ID", "").strip().strip("\"'")
        sec = vals.get("SPOTIFY_CLIENT_SECRET", "").strip().strip("\"'")
    return (cid, sec) if cid and sec else None


def available() -> bool:
    return _credentials() is not None


def client_id() -> str | None:
    creds = _credentials()
    return creds[0] if creds else None


def redirect_port() -> int:
    cfg = source_config(NAME)
    port = cfg.get("redirect_port") if isinstance(cfg, dict) else None
    return port if isinstance(port, int) and not isinstance(port, bool) else spotify_auth.DEFAULT_PORT


def _token() -> str:
    cache = cache_dir() / "spotify_token.json"
    try:
        tok = json.loads(cache.read_text())
        if tok.get("expires_at", 0) > time.time():
            return tok["access_token"]
    except (OSError, ValueError, KeyError):
        pass
    creds = _credentials()
    if creds is None:
        raise RuntimeError("spotify credentials missing")
    basic = base64.b64encode(f"{creds[0]}:{creds[1]}".encode()).decode()
    req = Request(f"{_auth_base()}/api/token", data=b"grant_type=client_credentials",
                  headers={"Authorization": f"Basic {basic}"})
    with urlopen(req, timeout=TIMEOUT) as r:
        tok = json.loads(r.read())
    tok["expires_at"] = time.time() + tok["expires_in"] - 30
    cache.write_text(json.dumps(tok))
    return tok["access_token"]


def _bearer() -> str:
    """The user's token when logged in (reads private playlists), else the app token."""
    if spotify_auth.logged_in():
        cid = client_id()
        if cid is None:
            raise RuntimeError("spotify credentials missing")
        return spotify_auth.access_token(cid)
    return _token()


def _get(path: str, params: dict | None = None) -> dict:
    url = _api() + path + (f"?{urlencode(params)}" if params else "")
    req = Request(url, headers={"Authorization": f"Bearer {_bearer()}"})
    with urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read())


def _names(artists) -> str | None:
    return ", ".join(a["name"] for a in artists or [] if a.get("name")) or None


def _track(t: dict, album: str | None = None) -> dict | None:
    if not t or not t.get("id"):
        return None
    return make_item(NAME, t["id"], t.get("name") or t["id"], kind="track",
                     artist=_names(t.get("artists")),
                     album=album or (t.get("album") or {}).get("name"),
                     duration=(t["duration_ms"] / 1000 if t.get("duration_ms") else None))


def _folder(kind: str, o: dict) -> dict | None:
    if not o or not o.get("id"):
        return None
    return make_item(NAME, o["id"], o.get("name") or o["id"], kind="folder",
                     path=f"{kind}:{o['id']}",
                     artist=_names(o.get("artists")) if kind == "album" else None)


def _compact(items) -> list[dict]:
    return [i for i in items if i]


def sections() -> list[dict]:
    return [{"id": "playlists", "title": "PLAYLISTS"},
            {"id": "artists", "title": "ARTISTS"}]


def _need_login() -> None:
    if not spotify_auth.logged_in():
        raise RuntimeError(LOGIN_NEEDED)


def _my_playlists() -> list[dict]:
    out, offset = [], 0
    while len(out) < MAX_ITEMS:
        data = _get("/me/playlists", {"limit": PAGE, "offset": offset})
        items = data.get("items") or []
        out += items
        if not data.get("next") or not items:
            break
        offset += PAGE
    return out[:MAX_ITEMS]


def _followed_artists() -> list[dict]:
    out, after = [], None
    while len(out) < MAX_ITEMS:
        params = {"type": "artist", "limit": PAGE}
        if after:
            params["after"] = after
        data = _get("/me/following", params).get("artists") or {}
        items = data.get("items") or []
        out += items
        after = (data.get("cursors") or {}).get("after")
        if not after or not items:
            break
    return out[:MAX_ITEMS]


def browse(path: str | None = None) -> list[dict]:
    if not path or path == "section:playlists":
        _need_login()
        return _compact(_folder("playlist", p) for p in _my_playlists())
    if path == "section:artists":
        _need_login()
        return _compact(_folder("artist", a) for a in _followed_artists())
    kind, _, sid = path.partition(":")
    if kind not in KINDS or not _ID.match(sid):
        raise ValueError("bad spotify path")
    if kind == "artist":
        data = _get(f"/artists/{sid}/albums",
                    {"include_groups": "album,single", "limit": LIST_LIMIT})
        return _compact(_folder("album", a) for a in data.get("items", []))
    if kind == "album":
        data = _get(f"/albums/{sid}")
        name = data.get("name")
        return _compact(_track(t, name) for t in (data.get("tracks") or {}).get("items", []))
    data = _get(f"/playlists/{sid}/tracks", {"limit": LIST_LIMIT})
    return _compact(_track((i or {}).get("track")) for i in data.get("items", []))


def search(query: str) -> list[dict]:
    query = (query or "").strip()
    if not query:
        return []
    data = _get("/search", {"q": query, "type": "track,album,artist,playlist",
                            "limit": SEARCH_LIMIT})
    out = _compact(_folder("artist", a) for a in (data.get("artists") or {}).get("items", []))
    out += _compact(_folder("album", a) for a in (data.get("albums") or {}).get("items", []))
    out += _compact(_folder("playlist", p) for p in (data.get("playlists") or {}).get("items", []))
    out += _compact(_track(t) for t in (data.get("tracks") or {}).get("items", []))
    return out


def _cover(t: dict) -> str | None:
    images = (t.get("album") or {}).get("images") or []
    if not images:
        return None
    dest = cache_dir() / "spotify" / f"{(t.get('album') or {}).get('id') or t['id']}.jpg"
    if dest.is_file():
        return str(dest)
    try:
        with urlopen(images[0]["url"], timeout=TIMEOUT) as r:
            data = r.read()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    except (OSError, KeyError):
        return None
    return str(dest)


def resolve(item: dict) -> Target:
    tid = item.get("id") or ""
    if not _ID.match(tid):
        raise ValueError("bad spotify id")
    t = _get(f"/tracks/{tid}")
    meta = {"title": t.get("name"), "artist": _names(t.get("artists")),
            "album": (t.get("album") or {}).get("name"), "art": _cover(t)}
    return Target(f"spotify:track:{tid}", False, meta, handoff="spotify")
