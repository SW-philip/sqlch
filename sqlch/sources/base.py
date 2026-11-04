from typing import NamedTuple

KINDS = ("track", "video", "folder")


class Target(NamedTuple):
    url: str
    video: bool = False
    meta: dict | None = None
    headers: tuple = ()  # HTTP header lines for mpv, e.g. auth
    handoff: str | None = None  # play in an external app (see core/handoff.py)
    context: str | None = None  # handoff: album/playlist uri to play url within


def make_item(source, id, title, *, kind="track", artist=None, album=None,
              art=None, duration=None, path=None, channel_id=None, date=None,
              genre=None, providers=None, feed_url=None, url=None, description=None,
              info=None, group=None) -> dict:
    """info is hover text for the row; group is the heading it is listed under."""
    if kind not in KINDS:
        raise ValueError(f"unknown item kind: {kind}")
    if kind == "folder" and path is None:
        raise ValueError("folder items need a path")
    return {"source": source, "id": id, "title": title, "artist": artist,
            "album": album, "art": art, "duration": duration, "kind": kind,
            "path": path, "channel_id": channel_id, "date": date,
            "genre": genre, "providers": providers, "feed_url": feed_url,
            "url": url, "description": description, "info": info, "group": group}
