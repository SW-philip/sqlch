from typing import NamedTuple

KINDS = ("track", "video", "folder")


class Target(NamedTuple):
    url: str
    video: bool = False
    meta: dict | None = None


def make_item(source, id, title, *, kind="track", artist=None, album=None,
              art=None, duration=None, path=None) -> dict:
    if kind not in KINDS:
        raise ValueError(f"unknown item kind: {kind}")
    if kind == "folder" and path is None:
        raise ValueError("folder items need a path")
    return {"source": source, "id": id, "title": title, "artist": artist,
            "album": album, "art": art, "duration": duration, "kind": kind,
            "path": path}
