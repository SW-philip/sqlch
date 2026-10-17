import os
import re
from pathlib import Path, PurePosixPath

from sqlch.sources import source_config
from sqlch.sources.base import Target, make_item

NAME = "local"
TITLE = "LOCAL"
LABEL = "Local Library"
HINT = ('Set "sources": {"local": {"library_root": "/path/to/music"}} '
        "in ~/.config/sqlch/sqlch.json")

AUDIO_EXT = {".mp3", ".flac", ".ogg", ".opus", ".m4a", ".aac", ".wav", ".wma"}
COVER_STEMS = ("cover", "folder", "front", "album")
COVER_EXT = (".jpg", ".jpeg", ".png")
SEARCH_LIMIT = 200


def _root() -> Path:
    cfg = source_config(NAME)
    root = cfg.get("library_root") if isinstance(cfg, dict) else None
    return Path(root if isinstance(root, str) and root else "~/Music").expanduser()


# No resolve(): symlinked album folders must keep working.
def _safe(root: Path, rel: str | None) -> Path:
    if not rel:
        return root
    p = PurePosixPath(rel)
    if p.is_absolute() or ".." in p.parts:
        raise ValueError("path outside library")
    return root / rel


def _title_from(stem: str) -> str:
    return re.sub(r"^\d+\s*[-._)]*\s*", "", stem) or stem


def _cover(directory: Path, cache: dict) -> str | None:
    if directory not in cache:
        names = {c.name.lower(): c for c in directory.iterdir() if c.is_file()}
        cache[directory] = next(
            (str(names[s + e]) for s in COVER_STEMS for e in COVER_EXT
             if s + e in names), None)
    return cache[directory]


def _track(root: Path, f: Path, covers: dict) -> dict:
    rel = f.relative_to(root)
    parts = rel.parts[:-1]
    return make_item(
        NAME, rel.as_posix(), _title_from(f.stem),
        artist=parts[-2] if len(parts) >= 2 else None,
        album=parts[-1] if parts else None,
        art=_cover(f.parent, covers))


def _is_audio(f: Path) -> bool:
    return f.suffix.lower() in AUDIO_EXT


def available() -> bool:
    return _root().is_dir()


def browse(path: str | None = None) -> list[dict]:
    root = _root()
    base = _safe(root, path)
    entries = [e for e in base.iterdir() if not e.name.startswith(".")]
    key = lambda e: e.name.lower()  # noqa: E731
    dirs = sorted((e for e in entries if e.is_dir()), key=key)
    files = sorted((e for e in entries if e.is_file() and _is_audio(e)), key=key)
    covers: dict = {}
    items = []
    for d in dirs:
        rel = d.relative_to(root).as_posix()
        items.append(make_item(NAME, rel, d.name, kind="folder", path=rel))
    items.extend(_track(root, f, covers) for f in files)
    return items


def search(query: str) -> list[dict]:
    words = (query or "").lower().split()
    if not words:
        return []
    root = _root()
    covers: dict = {}
    hits: list[dict] = []
    seen: set = set()
    try:
        st = os.stat(root)
        seen.add((st.st_dev, st.st_ino))
    except OSError:
        return hits
    for dirpath, dirs, files in os.walk(root, followlinks=True):
        keep = []
        for d in sorted(d for d in dirs if not d.startswith(".")):
            try:
                st = os.stat(os.path.join(dirpath, d))
            except OSError:
                continue
            ident = (st.st_dev, st.st_ino)
            if ident not in seen:
                seen.add(ident)
                keep.append(d)
        dirs[:] = keep
        for name in sorted(files):
            f = Path(dirpath) / name
            if name.startswith(".") or not _is_audio(f):
                continue
            rel = f.relative_to(root).as_posix().lower()
            if all(w in rel for w in words):
                hits.append(_track(root, f, covers))
                if len(hits) >= SEARCH_LIMIT:
                    return hits
    return hits


def resolve(item: dict) -> Target:
    root = _root()
    f = _safe(root, item["id"])
    if not f.is_file():
        raise FileNotFoundError(str(f))
    if not _is_audio(f):
        raise ValueError("not an audio file")
    it = _track(root, f, {})
    meta = {k: it[k] for k in ("title", "artist", "album", "art")}
    return Target(str(f), False, meta)
