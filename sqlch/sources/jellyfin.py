"""Jellyfin: browse and search the server's libraries, play by direct file URL."""

import json
from pathlib import Path
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from sqlch.core.paths import cache_dir
from sqlch.sources import source_config
from sqlch.sources.base import Target, make_item

NAME = "jellyfin"
TITLE = "JELLYFIN"
LABEL = "Jellyfin"
HINT = ("Create an API key in Jellyfin (Dashboard > API Keys) and put it in "
        "/run/secrets/jellyfin_api_key, or set sources.jellyfin.token_file")

DEFAULT_SERVER = "http://desktop:8096"
DEFAULT_TOKEN_FILE = "/run/secrets/jellyfin_api_key"
TIMEOUT = 8
SEARCH_LIMIT = 50

AUDIO = {"Audio"}
VIDEO = {"Movie", "Episode", "Video", "MusicVideo"}
SEARCH_TYPES = "Audio,Movie,Episode,MusicAlbum,MusicArtist,Series"

_user_ids: dict = {}


def _cfg() -> dict:
    cfg = source_config(NAME)
    return cfg if isinstance(cfg, dict) else {}


def _server() -> str:
    return (_cfg().get("server") or DEFAULT_SERVER).rstrip("/")


def _token() -> str | None:
    path = Path(_cfg().get("token_file") or DEFAULT_TOKEN_FILE).expanduser()
    try:
        return path.read_text().strip() or None
    except OSError:
        return None


def _auth() -> str:
    return f'MediaBrowser Token="{_token() or ""}"'


def available() -> bool:
    return _token() is not None


# stdlib urllib: the gui's python env has no requests, and panes call
# browse/search in the gui process.
def _open(path: str, params: dict | None = None) -> bytes:
    url = _server() + path + (f"?{urlencode(params)}" if params else "")
    req = Request(url, headers={"Authorization": _auth()})
    with urlopen(req, timeout=TIMEOUT) as r:
        return r.read()


def _get(path: str, params: dict | None = None):
    return json.loads(_open(path, params))


def _user_id() -> str:
    cfg_id = _cfg().get("user_id")
    if cfg_id:
        return cfg_id
    server = _server()
    if server not in _user_ids:
        users = _get("/Users")
        if not users:
            raise RuntimeError("jellyfin has no users")
        _user_ids[server] = users[0]["Id"]
    return _user_ids[server]


def _kind(jf: dict) -> str:
    t = jf.get("Type")
    if t in AUDIO:
        return "track"
    if t in VIDEO:
        return "video"
    return "folder"


def _duration(jf: dict):
    ticks = jf.get("RunTimeTicks")
    return ticks / 10_000_000 if ticks else None


def _to_item(jf: dict) -> dict:
    kind = _kind(jf)
    t = jf.get("Type")
    if t == "Episode":
        artist, album = jf.get("SeriesName"), jf.get("SeasonName")
    else:
        artists = jf.get("Artists") or []
        artist = jf.get("AlbumArtist") or (artists[0] if artists else None)
        album = jf.get("Album")
    title = jf.get("Name") or "?"
    return make_item(
        NAME, jf["Id"], title, kind=kind, artist=artist, album=album,
        duration=_duration(jf),
        path=f"{t}:{jf['Id']}" if kind == "folder" else None)


def _items(params: dict) -> list[dict]:
    data = _get("/Items", {"userId": _user_id(), **params})
    return [_to_item(jf) for jf in data.get("Items", [])]


def sections() -> list[dict]:
    return [{"id": "libraries", "title": "LIBRARIES"},
            {"id": "playlists", "title": "PLAYLISTS"}]


def browse(path: str | None = None) -> list[dict]:
    if path == "section:playlists":
        return _items({"IncludeItemTypes": "Playlist", "Recursive": "true",
                       "SortBy": "SortName"})
    if not path or path == "section:libraries":
        data = _get("/UserViews", {"userId": _user_id()})
        return [_to_item({**jf, "Type": jf.get("Type") or "CollectionFolder"})
                for jf in data.get("Items", [])]
    kind, _, jid = path.partition(":")
    if not jid:
        raise ValueError("bad jellyfin path")
    if kind == "Playlist":
        return _items({"parentId": jid})
    if kind == "MusicArtist":
        return _items({"AlbumArtistIds": jid, "IncludeItemTypes": "MusicAlbum",
                       "Recursive": "true", "SortBy": "ProductionYear,SortName"})
    return _items({"parentId": jid,
                   "SortBy": "ParentIndexNumber,IndexNumber,SortName"})


def search(query: str) -> list[dict]:
    query = (query or "").strip()
    if not query:
        return []
    return _items({"searchTerm": query, "Recursive": "true",
                   "IncludeItemTypes": SEARCH_TYPES, "Limit": SEARCH_LIMIT})


def _cover(jf: dict) -> str | None:
    if (jf.get("ImageTags") or {}).get("Primary"):
        img = jf["Id"]
    elif jf.get("AlbumId") and jf.get("AlbumPrimaryImageTag"):
        img = jf["AlbumId"]
    else:
        return None
    dest = cache_dir() / "jellyfin" / f"{img}.jpg"
    if dest.is_file():
        return str(dest)
    try:
        data = _open(f"/Items/{img}/Images/Primary", {"maxHeight": 400})
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    except OSError:  # URLError and HTTPError are OSErrors
        return None
    return str(dest)


def resolve(item: dict) -> Target:
    jid = item["id"]
    jf = _get(f"/Items/{quote(jid, safe='')}", {"userId": _user_id()})
    kind = _kind(jf)
    if kind == "folder":
        raise ValueError("not a playable item")
    it = _to_item(jf)
    meta = {k: it[k] for k in ("title", "artist", "album")}
    meta["art"] = _cover(jf)
    url = f"{_server()}/Items/{quote(jid, safe='')}/Download"
    return Target(url, kind == "video", meta, (f"Authorization: {_auth()}",))
