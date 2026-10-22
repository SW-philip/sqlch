"""Spotify catalog browsing and search with app (client-credentials) access.
Playback is handed to the Spotify desktop app, see sqlch/core/handoff.py."""

import base64
import html
import json
import os
import re
import time
from pathlib import Path
from urllib.error import HTTPError
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
RELOGIN = f"Spotify didn't allow it: {spotify_auth.LOGIN_HINT} again to grant library access"
WEB = "https://open.spotify.com"
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


def _send(method: str, path: str, params: dict) -> None:
    """A user-scoped write; Spotify answers these with an empty body."""
    url = _api() + path + f"?{urlencode(params)}"
    req = Request(url, data=b"", method=method,
                  headers={"Authorization": f"Bearer {_bearer()}"})
    try:
        with urlopen(req, timeout=TIMEOUT):
            pass
    except HTTPError as e:
        if e.code in (401, 403):
            raise RuntimeError(RELOGIN) from e
        if e.code == 404 and path == "/me/player/queue":
            raise RuntimeError("nothing is playing on Spotify to queue after") from e
        raise RuntimeError(f"Spotify said HTTP {e.code}") from e


def _names(artists) -> str | None:
    return ", ".join(a["name"] for a in artists or [] if a.get("name")) or None


def _clock(ms) -> str | None:
    if not isinstance(ms, int) or ms <= 0:
        return None
    m, sec = divmod(ms // 1000, 60)
    return f"{m // 60}:{m % 60:02d}:{sec:02d}" if m >= 60 else f"{m}:{sec:02d}"


def _lines(*lines) -> str | None:
    return "\n".join(x for x in lines if x) or None


def _dot(*parts) -> str:
    return " · ".join(str(p) for p in parts if p)


def _plain(text) -> str | None:
    # Playlist descriptions arrive as escaped HTML.
    if not isinstance(text, str):
        return None
    return html.unescape(re.sub(r"<[^>]+>", "", text)).strip() or None


def _track_info(t: dict, album: dict) -> str | None:
    total = album.get("total_tracks")
    number = t.get("track_number")
    place = (f"Track {number} of {total}" if number and total
             else f"Track {number}" if number else None)
    return _lines(t.get("name"), _names(t.get("artists")),
                  _dot(album.get("name"), (album.get("release_date") or "")[:4]),
                  _dot(place, _clock(t.get("duration_ms")),
                       "Explicit" if t.get("explicit") else None))


def _folder_info(kind: str, o: dict) -> str | None:
    if kind == "album":
        kind_name = (o.get("album_type") or "album").capitalize()
        count = o.get("total_tracks")
        return _lines(o.get("name"), _names(o.get("artists")),
                      _dot(kind_name, o.get("release_date"),
                           f"{count} tracks" if count else None))
    if kind == "artist":
        genres = [g for g in o.get("genres") or [] if isinstance(g, str)]
        return _lines(o.get("name"), "Artist", ", ".join(genres[:4]))
    owner = (o.get("owner") or {}).get("display_name")
    count = (o.get("items") or o.get("tracks") or {}).get("total")
    return _lines(o.get("name"), _dot(f"Playlist by {owner}" if owner else "Playlist",
                                      f"{count} tracks" if count else None),
                  _plain(o.get("description")))


def _track(t: dict, album: dict | None = None, group: str | None = None) -> dict | None:
    if not t or not t.get("id"):
        return None
    album = album or t.get("album") or {}
    return make_item(NAME, t["id"], t.get("name") or t["id"], kind="track",
                     artist=_names(t.get("artists")), album=album.get("name"),
                     duration=(t["duration_ms"] / 1000 if t.get("duration_ms") else None),
                     info=_track_info(t, album), group=group)


def _folder(kind: str, o: dict, group: str | None = None) -> dict | None:
    if not o or not o.get("id"):
        return None
    return make_item(NAME, o["id"], o.get("name") or o["id"], kind="folder",
                     path=f"{kind}:{o['id']}",
                     artist=_names(o.get("artists")) if kind == "album" else None,
                     info=_folder_info(kind, o), group=group)


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
        albums = [a for a in data.get("items") or [] if a]
        # Spotify's order: full albums, then singles and EPs.
        albums.sort(key=lambda a: a.get("album_type") == "single")
        return _compact(_folder("album", a, "SINGLES & EPS" if a.get("album_type") == "single"
                                else "ALBUMS") for a in albums)
    if kind == "album":
        data = _get(f"/albums/{sid}")
        return _compact(_track(t, data) for t in (data.get("tracks") or {}).get("items", []))
    data = _get(f"/playlists/{sid}/tracks", {"limit": LIST_LIMIT})
    return _compact(_track((i or {}).get("track")) for i in data.get("items", []))


def search(query: str) -> list[dict]:
    query = (query or "").strip()
    if not query:
        return []
    data = _get("/search", {"q": query, "type": "track,album,artist,playlist",
                            "limit": SEARCH_LIMIT})
    # Laid out like Spotify's results page.
    out = _compact(_track(t, group="SONGS") for t in (data.get("tracks") or {}).get("items", []))
    out += _compact(_folder("artist", a, "ARTISTS")
                    for a in (data.get("artists") or {}).get("items", []))
    out += _compact(_folder("album", a, "ALBUMS")
                    for a in (data.get("albums") or {}).get("items", []))
    out += _compact(_folder("playlist", p, "PLAYLISTS")
                    for p in (data.get("playlists") or {}).get("items", []))
    return out


def _kind_of(item: dict) -> tuple[str, str]:
    """(kind, id) for a track or folder item, checked before it reaches a url."""
    if item.get("kind") == "track":
        kind, sid = "track", item.get("id") or ""
    else:
        kind, _, sid = (item.get("path") or "").partition(":")
    if kind not in ("track", *KINDS) or not _ID.match(sid):
        raise ValueError("bad spotify item")
    return kind, sid


def _saved(uri: str) -> bool | None:
    try:
        res = _get("/me/library/contains", {"uris": uri})
    except (HTTPError, OSError, ValueError):
        return None
    return bool(res[0]) if isinstance(res, list) and res else None


def _go_to(label: str, kind: str, o: dict) -> dict | None:
    if not o or not o.get("id") or not _ID.match(o["id"]):
        return None
    name = o.get("name") or o["id"]
    return {"label": f"{label}: {name}", "path": f"{kind}:{o['id']}", "title": name}


def menu(item: dict) -> list[dict]:
    """Context menu entries for the gui; see SourcePane._open_menu."""
    kind, sid = _kind_of(item)
    out = []
    if kind == "track":
        t = _get(f"/tracks/{sid}")
        out.append(_go_to("Go to album", "album", t.get("album")))
        out += [_go_to("Go to artist", "artist", a) for a in t.get("artists") or []]
    elif kind == "album":
        out += [_go_to("Go to artist", "artist", a)
                for a in _get(f"/albums/{sid}").get("artists") or []]
    out = _compact(out)
    uri = f"spotify:{kind}:{sid}"
    if spotify_auth.logged_in():
        saved = _saved(uri)
        verb = ("Save to your library", "Remove from your library") \
            if kind in ("track", "album") else ("Follow", "Unfollow")
        if saved is None:
            out.append({"label": RELOGIN, "note": True})
        else:
            out.append({"label": verb[saved], "action": "remove" if saved else "save"})
        if kind == "track":
            out.append({"label": "Add to queue", "action": "queue"})
    else:
        out.append({"label": f"Log in for library actions: {spotify_auth.LOGIN_HINT}",
                    "note": True})
    out.append({"label": "Copy Spotify link", "copy": f"{WEB}/{kind}/{sid}"})
    return out


def act(item: dict, action: str) -> str:
    kind, sid = _kind_of(item)
    _need_login()
    uri = f"spotify:{kind}:{sid}"
    title = item.get("title") or "it"
    if action == "queue" and kind == "track":
        _send("POST", "/me/player/queue", {"uri": uri})
        return f"Queued {title}"
    if action in ("save", "remove"):
        _send("PUT" if action == "save" else "DELETE", "/me/library", {"uris": uri})
        if kind in ("track", "album"):
            return f"{'Saved' if action == 'save' else 'Removed'} {title}"
        return f"{'Following' if action == 'save' else 'Unfollowed'} {title}"
    raise ValueError(f"unknown spotify action: {action}")


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
